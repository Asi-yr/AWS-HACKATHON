"""
features.py
-----------
New features for SafeRoute, all exposed as pure functions only.
Nothing runs on import.

Features included:
  1. Three-Mode Route Display  — rank_routes(), label_route_modes()
  2. Safety Score Color Coding — get_score_color(), get_score_label()
  3. Estimated Fare Display    — estimate_fare()
  4. Typhoon Signal Banner     — get_typhoon_signal(), get_banner_html()
  5. Night Safety Risk         — is_nighttime(), apply_night_safety(),
                                 get_night_banner_html(), get_night_warning()

Integration points:
  - navigation.py : call rank_routes(), enrich_routes_with_scores(),
                    attach_fares(), apply_night_safety() before returning routes
  - main.py       : call get_typhoon_signal(), get_night_banner_html(),
                    pass results to render_template
  - index.html    : render {{ typhoon_banner | safe }} and {{ night_banner | safe }}
                    after <body>; show route['night_warning'] in route cards
"""

import math
import requests
from datetime import datetime, timezone, timedelta

# ═════════════════════════════════════════════════════════════════════════════
# 1. THREE-MODE ROUTE DISPLAY
# ═════════════════════════════════════════════════════════════════════════════

def rank_routes(routes: list, commuter_type: str = "") -> list:
    """
    Takes up to 3 OSRM road routes and ranks/labels them as:
      - Fastest    (shortest duration)
      - Balanced   (middle ground — best score of time + distance combined)
      - Alternate  (the remaining option)

    Also attaches a rough safety_score based on distance vs duration ratio
    (slower routes on shorter roads = calmer roads = higher score).

    Args:
        routes: list of route dicts as returned by navigation.py
        commuter_type: used to adjust scoring thresholds

    Returns:
        Same list, reordered and with 'mode_label' added to each route.
    """
    if not routes:
        return routes

    if len(routes) == 1:
        routes[0]['mode_label']       = 'Only Route'
        routes[0]['mode_label_color'] = '#27ae60'
        routes[0]['safety_score']     = _compute_safety_score(routes[0], commuter_type)
        return routes

    # Parse numeric duration/distance back out for scoring
    for r in routes:
        r['_dur']  = _parse_mins(r.get('time', '0 mins'))
        r['_dist'] = _parse_km(r.get('distance', '0 km'))

    # Fastest = lowest duration
    fastest = min(routes, key=lambda r: r['_dur'])

    # Balanced = lowest combined normalised score (time + distance)
    max_dur  = max(r['_dur']  for r in routes) or 1
    max_dist = max(r['_dist'] for r in routes) or 1
    for r in routes:
        r['_balance_score'] = (r['_dur'] / max_dur) + (r['_dist'] / max_dist)

    remaining = [r for r in routes if r is not fastest]
    balanced  = min(remaining, key=lambda r: r['_balance_score'])
    alternates = [r for r in remaining if r is not balanced]

    fastest['mode_label']        = 'Fastest'
    fastest['mode_label_color']  = '#2980b9'
    balanced['mode_label']       = 'Balanced'
    balanced['mode_label_color'] = '#27ae60'
    for r in alternates:
        r['mode_label']       = 'Alternate'
        r['mode_label_color'] = '#7f8c8d'

    # ── Assign IDs BEFORE scoring so position bonus in _compute_safety_score works ──
    ordered = [fastest, balanced] + alternates
    for i, r in enumerate(ordered):
        r['id'] = i

    # Attach safety scores (route id is now set, position bonus applies correctly)
    for r in ordered:
        r['safety_score'] = _compute_safety_score(r, commuter_type)

    # Clean up temp keys
    for r in ordered:
        r.pop('_dur', None)
        r.pop('_dist', None)
        r.pop('_balance_score', None)

    return ordered


def _parse_mins(time_str: str) -> float:
    """Parse '23 mins' or '1 hr 10 mins' -> total minutes as float"""
    try:
        s = str(time_str).lower().strip()
        total = 0.0
        if 'hr' in s or 'hour' in s:
            parts = s.replace('hours', 'hr').replace('hour', 'hr').split('hr')
            total += float(''.join(c for c in parts[0] if c.isdigit() or c == '.') or 0) * 60
            if len(parts) > 1:
                total += float(''.join(c for c in parts[1] if c.isdigit() or c == '.') or 0)
        else:
            total = float(''.join(c for c in s if c.isdigit() or c == '.') or 0)
        return total
    except Exception:
        return 0.0


def _parse_km(dist_str: str) -> float:
    """Parse '4.2 km' -> 4.2"""
    try:
        return float(str(dist_str).replace('km', '').strip())
    except ValueError:
        return 0.0


def _route_exposure_multiplier(route_idx: int) -> float:
    """
    Penalty multiplier by route position.
    Fastest routes (id=0) tend to use main roads → more exposed.
    Alternate routes (id=2) use side streets → slightly less exposed.
    """
    return {0: 1.10, 1: 1.00, 2: 0.92}.get(route_idx, 1.00)


# ═════════════════════════════════════════════════════════════════════════════
# SAFETY SCORE ENGINE — complete rewrite
# ═════════════════════════════════════════════════════════════════════════════
#
# DESIGN PHILOSOPHY
# ─────────────────
# The score is built in two clearly separated stages:
#
#   Stage 1 — BASE SCORE  (_compute_safety_score)
#     Reflects road/trip characteristics only: speed, distance, route type.
#     Returns a FLOAT in [0, 100]. No floors applied here.
#     Walk on a calm side street, daytime, no hazards → ~68–72.
#     Walk on a fast road, long trip → ~55–62.
#
#   Stage 2 — HAZARD DEDUCTIONS  (apply_penalty_to_route)
#     Each hazard source (night, crime, weather, flood) subtracts a FLAT
#     number of points from the float score. Flat subtraction is honest:
#     12 crime zones MUST score lower than 6 crime zones.
#     The score can go below the "comfort floor" if there are enough hazards
#     — that is the point. A walker at night through 19 crime zones SHOULD
#     score in the 25–38 range. That is accurate, not a bug.
#
#   Differentiation guarantee:
#     Routes are ranked before scoring, so Route 1 always starts −4 pts
#     vs Route 2. With flat deductions, the hazard penalties then directly
#     separate the routes: more crime zones = lower score. Simple and honest.
#
# COMMUTER PROFILES
# ─────────────────
# Each mode has a BASE that reflects inherent vulnerability.
# No floor is applied in Stage 1 — floors only exist as absolute UI minimums
# (never show below 10) to prevent "0/100" shock for truly extreme cases.
#
#   walk      base=70  — physically exposed, slow, no protection
#   bike      base=74  — faster, can use paths
#   motorcycle base=76 — enclosed less, speed risk
#   transit   base=80  — inside vehicle, crowd risk
#   car       base=85  — most protection

_COMMUTER_BASE = {
    # Base score for each mode — reflects inherent physical protection and control.
    # These are the MAXIMUM scores achievable on a calm, short, hazard-free trip.
    # Hazard deductions (night, crime, weather, flood) subtract from this.
    #
    #   All modes start at 100. A hazard-free trip scores 100/100.
    #   Differentiation is entirely through the penalty tables — walk and bike
    #   take larger hits from night/crime/weather than car, reflecting real
    #   exposure differences without baking in a starting disadvantage.
    "walk":       100.0,
    "bike":       100.0,
    "motorcycle": 100.0,
    "transit":    100.0,
    "car":        100.0,
}

# Per-mode speed threshold: avg trip speed above this starts incurring a penalty.
# Reflects the road type each mode is comfortable on.
_SPEED_THRESHOLD = {
    "walk":       5.0,    # normal walking pace — above this = faster/busier road
    "bike":       15.0,   # comfortable urban cycling pace
    "motorcycle": 30.0,   # urban riding baseline
    "transit":    25.0,   # typical urban bus/jeepney speed
    "car":        35.0,   # comfortable urban driving speed
}

# Points deducted per kph above the threshold (not multiplied by 10 — linear, capped at 12).
# Walk is most sensitive: a pedestrian on a high-speed road is dangerous.
# Car is least sensitive: highways are designed for cars.
_SPEED_SENSITIVITY = {
    "walk":       1.0,    # 1 pt per kph above 5 kph → capped at 12
    "bike":       0.8,
    "motorcycle": 0.5,
    "transit":    0.3,
    "car":        0.2,
}

# Route position adjustments — small, so hazard counts dominate
_ROUTE_POSITION_ADJ = {0: -4.0, 1: 0.0, 2: +4.0}


def _get_commuter_key(ct: str) -> str:
    """Map any commuter_type string to a profile key."""
    ct = ct.lower().strip()
    if any(x in ct for x in ["walk", "foot"]):
        return "walk"
    if any(x in ct for x in ["bike", "bicycle", "cycling"]):
        return "bike"
    if any(x in ct for x in ["motor", "motorcycle", "motorbike"]):
        return "motorcycle"
    if any(x in ct for x in ["commute", "jeepney", "bus", "tricycle", "puj",
                               "lrt", "mrt", "pnr", "rail", "train"]):
        return "transit"
    return "car"


def _get_commuter_profile(ct: str) -> tuple:
    """
    Legacy compatibility shim — returns (ceiling, floor, sensitivity) tuple
    for code that still calls this. ceiling=base+15, floor=10 (UI minimum only).
    """
    key = _get_commuter_key(ct)
    base = _COMMUTER_BASE[key]
    return (min(100.0, base + 15.0), 10.0, _SPEED_SENSITIVITY[key])


def _compute_safety_score(route: dict, commuter_type: str = "") -> float:
    """
    Stage 1: compute base safety score from trip characteristics only.

    Returns a float. Hazard deductions (night/crime/weather/flood) are
    applied separately via apply_penalty_to_route().

    Factors:
      1. Commuter mode base score (walk=70, car=85, etc.)
      2. Speed penalty — avg speed above the mode's comfort threshold
         signals exposure to faster/more dangerous roads
      3. Distance penalty — longer trips = more total exposure time
      4. Route position — fastest route gets −4, alternate gets +4

    No congestion penalty for slow-speed modes (walkers move at 4–6 kph
    normally — that is not congestion, that is just walking).
    """
    dur       = _parse_mins(route.get('time', '0'))
    dist      = _parse_km(route.get('distance', '0'))
    route_idx = route.get('id', 0)
    key       = _get_commuter_key(commuter_type)

    base        = _COMMUTER_BASE[key]
    threshold   = _SPEED_THRESHOLD[key]
    sensitivity = _SPEED_SENSITIVITY[key]

    if dur <= 0:
        score = base + _ROUTE_POSITION_ADJ.get(route_idx, 0)
        return round(max(10.0, min(100.0, score)), 2)

    avg_speed_kmh = (dist / (dur / 60.0)) if dur > 0 else 0.0

    # ── 1. Speed penalty ──────────────────────────────────────────────────
    # Points deducted = (kph above threshold) × sensitivity, capped at 12.
    # Formula: speed_penalty = speed_above * sensitivity  (linear, simple)
    # Walk at 4.5 kph → 0 penalty (normal walking). Car at 60 kph → (25×0.2)=5 pts.
    # Cap at 12 to prevent speed alone from dominating — hazards matter more.
    speed_above = max(0.0, avg_speed_kmh - threshold)
    speed_penalty = min(12.0, speed_above * sensitivity)

    # ── 2. Distance penalty ───────────────────────────────────────────────
    # Longer trips = more exposure. Smooth curve, capped at 6 pts.
    if dist <= 5:
        dist_penalty = 0.0
    elif dist <= 10:
        dist_penalty = 1.0
    elif dist <= 15:
        dist_penalty = 2.5
    elif dist <= 25:
        dist_penalty = 4.0
    else:
        dist_penalty = 6.0

    # ── 3. Route position ─────────────────────────────────────────────────
    position_adj = _ROUTE_POSITION_ADJ.get(route_idx, 0.0)

    raw = base - speed_penalty - dist_penalty + position_adj
    return round(max(10.0, min(100.0, raw)), 2)


# ── Flat penalty helper ───────────────────────────────────────────────────────

def apply_penalty_to_route(route: dict, raw_penalty: float, commuter_type: str = "") -> float:
    """
    Stage 2: apply a hazard penalty (night / crime / weather / flood) to
    route['safety_score'] using FLAT subtraction.

    Why flat, not proportional?
      Proportional reduction (×0.8) means every call reduces by a percentage
      of the *remaining* score. After 3 stacked calls the score barely moves.
      A route with 19 crime zones ends up almost identical to one with 12.
      That is wrong — more hazards MUST produce a meaningfully lower score.

    Flat subtraction is honest:
      • Night penalty of 18 pts → score drops by exactly 18 pts
      • Each extra crime zone adds its increment directly
      • Route with 19 zones scores noticeably lower than 12 zones
      • Score can go into "Risky" territory if there really are many hazards
        — that is accurate information, not a UI problem

    Absolute minimum is 10 (prevents "0/100" shock for truly extreme cases).
    There is NO commuter floor clamping here — the score reflects reality.

    Args:
        route:         route dict with 'safety_score' (float or int)
        raw_penalty:   penalty points to subtract (positive number)
        commuter_type: kept for API compatibility, not used for floor

    Returns:
        New safety_score (float rounded to 1dp). Mutates route in-place.
    """
    current   = float(route.get("safety_score", 70.0))
    new_score = max(20.0, current - raw_penalty)   # floor=22: never show below 22/100
    new_score = round(new_score, 1)
    route["safety_score"] = new_score
    return new_score


# ═════════════════════════════════════════════════════════════════════════════
# 2. SAFETY SCORE COLOR CODING
# ═════════════════════════════════════════════════════════════════════════════

def get_score_color(score: float) -> str:
    """
    Returns a hex color for a safety score (accepts float or int).

      80–100 → deep green  (Very Safe)
      65–79  → green       (Safe)
      50–64  → yellow      (Moderate)
      38–49  → orange      (Caution)
      0–37   → red         (Risky)
    """
    s = float(score)
    if s >= 80:
        return "#1e8449"
    elif s >= 65:
        return "#27ae60"
    elif s >= 50:
        return "#f1c40f"
    elif s >= 38:
        return "#e67e22"
    else:
        return "#e74c3c"


def get_score_label(score: float) -> str:
    """Returns a short human label for a safety score (accepts float or int)."""
    s = float(score)
    if s >= 80:
        return "Very Safe"
    elif s >= 65:
        return "Safe"
    elif s >= 50:
        return "Moderate"
    elif s >= 38:
        return "Caution"
    else:
        return "Risky"


def enrich_routes_with_scores(routes: list, commuter_type: str = "") -> list:
    """
    Adds 'score_color' and 'score_label' to each route dict in-place.
    Preserves float safety_score — do NOT cast to int here, as downstream
    hazard deductions need the decimal precision to differentiate routes.
    """
    for r in routes:
        if 'safety_score' not in r or r.get('safety_score') is None:
            r['safety_score'] = _compute_safety_score(r, commuter_type)
        score = r['safety_score']
        r['score_color'] = get_score_color(score)
        r['score_label'] = get_score_label(score)
    return routes


# ═════════════════════════════════════════════════════════════════════════════
# 3. ESTIMATED FARE DISPLAY
# ═════════════════════════════════════════════════════════════════════════════

# Philippine fare tables (2024 LTFRB base rates)
_FARE_RULES = {
    "jeepney": {
        "base_fare": 13.00,       # PHP, covers first 4 km
        "base_km":   4.0,
        "per_km":    1.80,        # PHP per km beyond base
        "unit":      "PHP",
        "note":      "LTFRB 2024 modernized jeepney rate",
    },
    "bus": {
        "base_fare": 15.00,
        "base_km":   5.0,
        "per_km":    2.20,
        "unit":      "PHP",
        "note":      "Ordinary bus, EDSA/Metro Manila",
    },
    "tricycle": {
        "base_fare": 20.00,       # Typically flat within barangay
        "base_km":   2.0,
        "per_km":    8.00,        # tricycles negotiate, this is a rough estimate
        "unit":      "PHP",
        "note":      "Estimated — tricycles are locally negotiated",
    },
    "lrt1":  {"flat": 15.00, "max": 35.00, "unit": "PHP", "note": "LRT-1 distance-based"},
    "lrt-1": {"flat": 15.00, "max": 35.00, "unit": "PHP", "note": "LRT-1 distance-based"},
    "lrt2":  {"flat": 15.00, "max": 30.00, "unit": "PHP", "note": "LRT-2 distance-based"},
    "lrt-2": {"flat": 15.00, "max": 30.00, "unit": "PHP", "note": "LRT-2 distance-based"},
    "mrt3":  {"flat": 13.00, "max": 28.00, "unit": "PHP", "note": "MRT-3 distance-based"},
    "mrt-3": {"flat": 13.00, "max": 28.00, "unit": "PHP", "note": "MRT-3 distance-based"},
    "pnr":   {"flat": 30.00, "max": 65.00, "unit": "PHP", "note": "PNR distance-based"},
    "car":        None,   # private, no transit fare
    "automobile": None,
    "motorcycle": None,
    "motorbike":  None,
    "commute": {
        "base_fare": 13.00,
        "base_km":   4.0,
        "per_km":    1.80,
        "unit":      "PHP",
        "note":      "Est. jeepney/bus fare (LTFRB 2024). Tricycle extra if needed.",
    },
    "puj": {
        "base_fare": 13.00,
        "base_km":   4.0,
        "per_km":    1.80,
        "unit":      "PHP",
        "note":      "LTFRB 2024 PUJ rate",
    },
    "walk":   {"flat": 0, "unit": "PHP", "note": "Free"},
    "bike":   {"flat": 0, "unit": "PHP", "note": "Free"},
    "bicycle":{"flat": 0, "unit": "PHP", "note": "Free"},
}


def _estimate_transfers(distance_km: float, commuter_type: str) -> int:
    """
    Rough estimate of how many vehicle transfers a trip involves.
    Jeepneys typically cover 3–6 km per route in Metro Manila.
    Tricycles cover 1–2 km per trip (barangay-level only).
    """
    ct = commuter_type.lower()
    if "tricycle" in ct:
        # Tricycles are short-range only — almost always need a jeepney too
        return max(1, int(distance_km / 1.5))
    elif ct in ("commute", "jeepney", "puj"):
        # Average jeepney route ~4 km in Metro Manila
        return max(1, int(distance_km / 4.0))
    elif "bus" in ct:
        # Buses cover longer distances, fewer transfers
        return max(1, int(distance_km / 8.0))
    return 1


def estimate_fare(commuter_type: str, distance_km: float) -> dict:
    """
    Estimate the fare for a given commuter type and route distance.
    For public transit, accounts for typical number of transfers/vehicles.

    Args:
        commuter_type: e.g. 'commute', 'jeepney', 'mrt3', 'walk'
        distance_km:   route distance in km (float)

    Returns:
        dict with keys: min_fare, max_fare, display, note, unit
        Returns None if commuter type has no applicable fare (private vehicle).
    """
    key = commuter_type.lower().strip()
    rule = _FARE_RULES.get(key)

    if rule is None:
        return {"display": "N/A (private)", "min_fare": None, "max_fare": None,
                "note": "Private vehicle — no transit fare", "unit": "PHP"}

    # Free modes
    if rule.get("flat", -1) == 0:
        return {"display": "Free", "min_fare": 0, "max_fare": 0,
                "note": rule.get("note", ""), "unit": "PHP"}

    # Rail — flat range (single ticket, no transfers needed)
    if "flat" in rule and "max" in rule:
        return {
            "display":  f"₱{int(rule['flat'])}–{int(rule['max'])}",
            "min_fare": rule["flat"],
            "max_fare": rule["max"],
            "note":     rule.get("note", ""),
            "unit":     "PHP",
        }

    # Distance-based with transfer estimation (jeepney, bus, tricycle, commute)
    base_fare = rule["base_fare"]
    base_km   = rule["base_km"]
    per_km    = rule["per_km"]

    transfers = _estimate_transfers(distance_km, key)

    # Each transfer = at least one base fare
    # Distribute distance across transfers evenly
    km_per_leg = distance_km / transfers
    fare_per_leg = base_fare if km_per_leg <= base_km else (
        base_fare + (km_per_leg - base_km) * per_km
    )
    fare_min = round(fare_per_leg * transfers, 2)
    # Upper bound: add 1 extra transfer worth of base fare for variance
    fare_max = round(fare_min + base_fare, 2)

    transfer_note = (
        f"~{transfers} vehicle{'s' if transfers > 1 else ''}"
        if transfers > 1 else "single ride"
    )
    note = f"{rule.get('note', '')} | Est. {transfer_note}. Actual fare varies."

    return {
        "display":  f"₱{int(fare_min)}–{int(fare_max)}",
        "min_fare": fare_min,
        "max_fare": fare_max,
        "note":     note,
        "unit":     "PHP",
    }


def attach_fares(routes: list, commuter_type: str) -> list:
    """
    Adds 'fare' dict to each route. Call in navigation.py before returning.
    """
    for r in routes:
        dist_km = _parse_km(r.get('distance', '0'))
        r['fare'] = estimate_fare(commuter_type, dist_km)
    return routes


# ═════════════════════════════════════════════════════════════════════════════
# 4. TYPHOON SIGNAL BANNER
# ═════════════════════════════════════════════════════════════════════════════

# PAGASA endpoints — bulletin.json URL rotates; we try multiple in order
_PAGASA_URLS = [
    # Primary: tamss bulletin JSON
    "https://pubfiles.pagasa.dost.gov.ph/tamss/weather/bulletin.json",
    # Fallback 1: alternative DOST subdomain
    "https://pubfiles.pagasa.dost.gov.ph/climps/tcthreat/summary.json",
    # Fallback 2: raw JSON from the new PAGASA site
    "https://bagong.pagasa.dost.gov.ph/api/tropical-cyclone/active",
    # Fallback 3: pubfiles direct API variant (2026 observed pattern)
    "https://pubfiles.pagasa.dost.gov.ph/tamss/weather/bulletin_en.json",
    # Fallback 4: new PAGASA REST endpoint pattern
    "https://bagong.pagasa.dost.gov.ph/api/v1/tropical-cyclone/active",
]
_BAGYO_WATCH = "https://bagong.pagasa.dost.gov.ph/tropical-cyclone/public-storm-warning-signals"

_PAGASA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://bagong.pagasa.dost.gov.ph/",
    "Origin": "https://bagong.pagasa.dost.gov.ph",
}


def _try_parse_pagasa_response(data: dict) -> dict | None:
    """
    Try to parse a PAGASA JSON response in any known schema.
    Returns a typhoon dict or None if no active cyclone found.
    """
    # Schema A: {"cyclones": [...]}
    cyclones = data.get("cyclones") or data.get("data") or data.get("results") or []
    if isinstance(cyclones, dict):
        cyclones = list(cyclones.values())

    if not cyclones:
        return None

    active = None
    for c in cyclones:
        if isinstance(c, dict) and c.get("active", True):
            active = c
            break

    if not active:
        return None

    name   = (active.get("name") or active.get("international_name")
              or active.get("typhoon_name") or "Tropical Cyclone")
    signal = int(active.get("signal") or active.get("max_signal")
                 or active.get("psws") or 0)
    if signal == 0:
        return None  # Active cyclone but no signal number — treat as inactive

    return {
        "active":   True,
        "signal":   signal,
        "name":     name,
        "headline": f"⚠️ Typhoon {name} — Signal #{signal} in effect",
        "color":    _signal_color(signal),
        "source":   _BAGYO_WATCH,
    }


def get_typhoon_signal() -> dict:
    """
    Fetch the current PAGASA tropical cyclone bulletin and return a summary.
    Tries multiple PAGASA endpoints in order, falls back gracefully if all fail.

    Returns dict:
        {
          "active":   bool,
          "signal":   int or None,   # 1–5
          "name":     str or None,   # cyclone name
          "headline": str,
          "color":    str,           # banner background hex
          "source":   str,           # URL for "more info" link
        }

    NOTE: PAGASA rotates bulletin.json URLs occasionally.
    If this returns inactive when a typhoon is active, check _PAGASA_URLS
    in features.py and update with the current endpoint from DevTools on
    https://bagong.pagasa.dost.gov.ph/
    """
    last_error = None
    for url in _PAGASA_URLS:
        try:
            resp = requests.get(url, timeout=6, headers=_PAGASA_HEADERS)
            if resp.status_code == 404:
                last_error = f"404 at {url}"
                continue   # try next URL
            resp.raise_for_status()

            # Try JSON first
            try:
                data = resp.json()
                result = _try_parse_pagasa_response(data)
                if result is not None:
                    return result
                # Valid JSON but no cyclones = genuinely no active typhoon
                return _no_typhoon()
            except ValueError:
                # Not JSON — might be HTML page; skip this URL
                last_error = f"Non-JSON response from {url}"
                continue

        except requests.exceptions.Timeout:
            last_error = f"Timeout: {url}"
            continue
        except requests.exceptions.ConnectionError:
            last_error = f"Connection error: {url}"
            continue
        except Exception as e:
            last_error = str(e)
            continue

    # All JSON URLs failed — try scraping the public PAGASA advisory page for
    # any mention of active signal numbers (non-critical, best-effort)
    try:
        resp = requests.get(_BAGYO_WATCH, timeout=8, headers=_PAGASA_HEADERS)
        if resp.status_code == 200:
            text = resp.text
            import re as _re
            signal_match = _re.search(
                r'(?:signal\s*(?:no\.?|#)\s*(\d)|psws\s*#?\s*(\d))',
                text, _re.IGNORECASE
            )
            name_match = _re.search(
                r'(?:typhoon|tropical storm|tropical depression)\s+([A-Z][a-z]+)',
                text, _re.IGNORECASE
            )
            if signal_match:
                signal = int(signal_match.group(1) or signal_match.group(2))
                name   = name_match.group(1) if name_match else "Tropical Cyclone"
                return {
                    "active":   True,
                    "signal":   signal,
                    "name":     name,
                    "headline": f"⚠️ Typhoon {name} — Signal #{signal} in effect",
                    "color":    _signal_color(signal),
                    "source":   _BAGYO_WATCH,
                }
    except Exception:
        pass  # HTML scrape failed — fall through to no_typhoon

    import logging
    logging.getLogger("saferoute").warning(
        f"PAGASA typhoon check failed (all URLs exhausted). Last error: {last_error}"
    )
    return _no_typhoon()


def _no_typhoon() -> dict:
    return {
        "active":   False,
        "signal":   None,
        "name":     None,
        "headline": "",
        "color":    "#27ae60",
        "source":   _BAGYO_WATCH,
    }


def _signal_color(signal: int) -> str:
    return {1: "#f1c40f", 2: "#e67e22", 3: "#e74c3c", 4: "#8e44ad", 5: "#2c3e50"}.get(signal, "#e74c3c")


def get_banner_html(typhoon: dict) -> str:
    """
    Returns an HTML string for the typhoon banner.
    Returns empty string if no active typhoon.

    Inject this into index.html via Jinja: {{ typhoon_banner | safe }}
    Place it right after the <body> tag or above the sidebar.
    """
    if not typhoon.get("active"):
        return ""

    color  = typhoon["color"]
    text   = typhoon["headline"]
    source = typhoon["source"]

    return (
        f'<div class="typhoon-banner" style="background:{color};color:#fff;'
        f'padding:8px 16px;font-size:13px;font-weight:bold;text-align:center;'
        f'position:fixed;top:0;left:0;right:0;z-index:99999;'
        f'box-shadow:0 2px 6px rgba(0,0,0,0.3);">'
        f'{text} &nbsp;'
        f'<a href="{source}" target="_blank" '
        f'style="color:#fff;text-decoration:underline;">PAGASA Advisory</a>'
        f'</div>'
    )


# ═════════════════════════════════════════════════════════════════════════════
# 5. NIGHT SAFETY RISK
# ═════════════════════════════════════════════════════════════════════════════
#
# Night safety is NOT a dark theme. It is a runtime safety adjustment:
#   - Detects if the current Philippine time is nighttime (6 PM – 6 AM)
#   - Penalises safety scores for vulnerable commuter types at night
#   - Returns a warning banner + per-route night hazard labels
#   - Flags routes as higher risk when travelling alone at night
#
# Nothing here changes the UI colours. It changes safety scores and warnings.

# Philippine Standard Time = UTC+8
_PHT = timezone(timedelta(hours=8))
_NIGHT_START = 18   # 6 PM
_NIGHT_END   = 6    # 6 AM

# Flat points deducted from safety score when travelling at night.
#
# Design rationale:
#   Night is genuinely more dangerous: poor visibility, fewer witnesses,
#   reduced law enforcement presence, closed businesses, altered commuter
#   behaviour. Penalties reflect physical vulnerability + exposure level.
#
#   walk      — fully exposed, unlit sidewalks, slowest to react: −14
#   bike      — exposed, front light often absent, slippery roads: −11
#   motorcycle — high-speed + dark roads = leading accident cause at night: −10
#   transit   — on foot between stops, waiting alone, transfers in dark: −12
#               (higher than motorcycle: commuters are physically exposed
#               at stops and walking legs, not just while riding)
#   car       — enclosed, headlights on, minimal added risk: −4
#
# Late night (10 PM – 4 AM) applies an additional +4 to all modes via the
# severity multiplier in apply_night_safety().
#
# These values are intentionally stronger than daytime weather penalties
# to ensure that nighttime travel is clearly flagged as higher risk even
# in clear weather — which is accurate for Metro Manila conditions.
_NIGHT_PENALTY = {
    "walk":       12,   # physically exposed: −12 (was 14, slightly reduced)
    "walking":    12,
    "bike":        9,   # exposed but faster: −9
    "bicycle":     9,
    "motorcycle":  8,   # enclosed more, speed risk: −8
    "motorbike":   8,
    "tricycle":    8,
    "jeepney":    10,   # waiting at stops = on-foot exposure: −10
    "bus":        10,
    "commute":    10,
    "transit":    10,   # generic transit alias
    "car":         3,   # enclosed, minimal extra risk at night: −3
    "automobile":  3,
}

_NIGHT_WARNINGS = {
    "walk":       "⚠️ Walking at night is high risk — stick to lit, busy streets.",
    "walking":    "⚠️ Walking at night is high risk — stick to lit, busy streets.",
    "bike":       "⚠️ Cycling at night — wear reflectors, avoid unlit roads.",
    "bicycle":    "⚠️ Cycling at night — wear reflectors, avoid unlit roads.",
    "motorcycle": "⚠️ Nighttime motorcycle rides have higher accident rates.",
    "motorbike":  "⚠️ Nighttime motorcycle rides have higher accident rates.",
    "tricycle":   "⚠️ Tricycle availability drops at night. Open cabin = higher exposure.",
    "jeepney":    "⚠️ Some jeepney routes stop after 9 PM. Verify before travelling.",
    "bus":        "⚠️ Bus frequency drops at night. Waiting at stops can be unsafe.",
    "commute":    "⚠️ Public transit is limited at night. Plan your return trip.",
    "car":        "🌙 Nighttime driving — watch for poor visibility and road hazards.",
    "automobile": "🌙 Nighttime driving — watch for poor visibility and road hazards.",
    "lrt1":       "🌙 LRT-1 last trip is around 10:00 PM.",
    "lrt2":       "🌙 LRT-2 last trip is around 10:00 PM.",
    "mrt3":       "🌙 MRT-3 last trip is around 10:30 PM. Verify schedule.",
    "pnr":        "🌙 PNR operates limited trips at night.",
}

_DEFAULT_NIGHT_WARNING = "🌙 Travelling at night — exercise extra caution."


def is_nighttime(hour: int = None) -> bool:
    """
    Returns True if current Philippine Standard Time is between 6 PM and 6 AM.

    Args:
        hour: override for testing (0–23 in PHT). If None, uses current time.
    """
    if hour is None:
        hour = datetime.now(_PHT).hour
    return hour >= _NIGHT_START or hour < _NIGHT_END


def get_current_pht_hour() -> int:
    """Returns the current hour in Philippine Standard Time (0–23)."""
    return datetime.now(_PHT).hour


def get_night_safety_penalty(commuter_type: str) -> int:
    """
    Returns the safety score penalty (integer) to subtract at night.
    0 if it is currently daytime.

    Call this inside _compute_safety_score() to apply time-aware scoring.
    """
    if not is_nighttime():
        return 0
    key = commuter_type.lower().strip()
    return _NIGHT_PENALTY.get(key, 10)


def get_night_warning(commuter_type: str) -> str:
    """
    Returns a human-readable night safety warning string for the commuter type.
    Returns empty string if it is currently daytime.

    Attach this to each route as route['night_warning'].
    """
    if not is_nighttime():
        return ""
    key = commuter_type.lower().strip()
    return _NIGHT_WARNINGS.get(key, _DEFAULT_NIGHT_WARNING)


def get_night_banner_html(commuter_type: str) -> str:
    """
    Returns an HTML warning banner string for nighttime travel.
    Returns empty string during the day.

    Inject into index.html via Jinja: {{ night_banner | safe }}
    Place right after {{ typhoon_banner | safe }} inside <body>.
    """
    if not is_nighttime():
        return ""

    hour = get_current_pht_hour()
    # Late night (10 PM – 4 AM) is the most severe window
    late_night  = (hour >= 22 or hour < 4)
    early_morn  = (4 <= hour < 6)

    if late_night:
        bg    = "#1a252f"
        label = "🌑 Late Night Advisory"
    elif early_morn:
        bg    = "#2c3e50"
        label = "🌄 Early Morning Advisory"
    else:
        bg    = "#34495e"
        label = "🌙 Night Travel Advisory"

    msg = get_night_warning(commuter_type)

    return (
        f'<div class="night-banner" style="background:{bg};color:#f0f0f0;'
        f'padding:8px 16px;font-size:13px;font-weight:bold;text-align:center;'
        f'position:fixed;top:0;left:0;right:0;z-index:99998;'
        f'box-shadow:0 2px 6px rgba(0,0,0,0.4);">'
        f'{label}: {msg}'
        f'</div>'
    )


def apply_night_safety(routes: list, commuter_type: str) -> list:
    """
    Applies night-time flat safety penalties and warnings to all routes.

    Time-of-day tiers:
      Daytime  (6 AM – 6 PM):  NO penalty applied. Scores reflect road/crime/weather only.
      Evening  (6 PM – 10 PM): Base night penalty applied (see _NIGHT_PENALTY).
      Late night (10 PM – 4 AM): Base penalty × 1.4 — the most dangerous window.
        Fewer witnesses, most violent incidents occur here, last-trip risk for
        transit, drunk drivers on the road, minimal street activity.
      Early morning (4 AM – 6 AM): Base penalty × 1.15 — slightly easing but still dark.

    Route exposure multiplier is kept tight (1.05/1.0/0.96) so that crime zone
    counts — not route position — drive differentiation between routes at night.
    """
    if not is_nighttime():
        for r in routes:
            r['night_warning'] = ""
        return routes

    base_penalty = get_night_safety_penalty(commuter_type)
    warning      = get_night_warning(commuter_type)
    hour         = get_current_pht_hour()

    # Late night (10 PM – 4 AM) is the most dangerous window
    if hour >= 22 or hour < 4:
        time_multiplier = 1.4
    # Early morning (4 AM – 6 AM) — still dark but slightly safer
    elif hour < 6:
        time_multiplier = 1.15
    # Evening (6 PM – 10 PM) — standard night penalty
    else:
        time_multiplier = 1.0

    for r in routes:
        if base_penalty > 0:
            # Small route-position multiplier — keeps fastest route slightly
            # more penalised (main roads, more traffic, more exposure at night)
            route_multiplier = {0: 1.05, 1: 1.00, 2: 0.96}.get(r.get('id', 1), 1.00)
            final_penalty = base_penalty * time_multiplier * route_multiplier
            apply_penalty_to_route(r, final_penalty, commuter_type)
            r['score_color'] = get_score_color(r['safety_score'])
            r['score_label'] = get_score_label(r['safety_score'])
        r['night_warning'] = warning

    return routes