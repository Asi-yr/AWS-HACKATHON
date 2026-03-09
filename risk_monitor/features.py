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
    Returns a penalty multiplier based on route position.
    Fastest routes (id=0) use highways → more exposed to hazards.
    Alternate routes (id=2) use side streets → less exposed.

    Multipliers are kept tighter (1.2 / 1.0 / 0.85) compared to the old
    (1.4 / 1.0 / 0.65) to prevent penalty stacking from crashing scores to 0.
    """
    return {0: 1.20, 1: 1.00, 2: 0.85}.get(route_idx, 1.00)


# ── Per-commuter safety ceiling and floor ─────────────────────────────────────
# These reflect the inherent risk of each travel mode regardless of road type.
#   ceiling  — maximum score achievable (car on side street = 88, walk on highway < 60)
#   floor    — minimum score on a clear day (walk is never "perfectly safe")
#   road_sensitivity — how much road speed affects the score
#
# Design rationale:
#   Walk   : most physically vulnerable, no crash protection, no speed advantage.
#             Realistic day-trip on safe roads ≈ 62–72. Highway walk ≈ 42–52.
#   Bike   : exposed but faster; can use bike lanes / footpaths.
#             Realistic range ≈ 58–78.
#   Motor  : speed protection but falls worse; lane-splitting adds risk.
#             Realistic range ≈ 60–80.
#   Transit: inside a vehicle but no control; crowd / pickpocket risk.
#             Realistic range ≈ 65–82.
#   Car    : most crash protection, controlled environment.
#             Realistic range ≈ 70–88.
#
# Result: even before any hazard penalty is applied, a walker gets a lower
# baseline than a car driver on the same road. Hazard penalties then shrink
# proportionally (see apply_penalty_to_route), so no single source can
# cause a cliff-drop to 0.

_COMMUTER_PROFILE = {
    # key: (ceiling, floor, road_sensitivity)
    #   road_sensitivity: extra deduction per 10 kph above 30 kph avg speed
    #
    # IMPORTANT: floors must be LOW enough that they represent the absolute
    # worst-case scenario, NOT the typical-bad-day outcome. If the floor is
    # close to the realistic base score range, penalty stacking (night +
    # crime + weather) will clamp every route to the same floor value and
    # make all routes show the same score. Floors were previously too high
    # (walk=42, motorcycle=52, car=62) which caused this exact symptom.
    "walk":       (72,  28, 2.5),   # floor=28: "risky walk at night in a crime zone"
    "bike":       (78,  32, 1.8),
    "motorcycle": (80,  36, 1.2),   # floor=36: worst credible motorcycle conditions
    "transit":    (82,  40, 0.8),
    "car":        (88,  45, 0.4),   # floor=45: bad road + crime + storm in a car
}

_ROUTE_POSITION_ADJ = {0: -10, 1: 0, 2: +10}   # fastest / balanced / alternate
# Wider spread (±10 vs old ±6) ensures routes still differ visibly after
# proportional hazard penalties (night/crime/weather) are applied on top.


def _get_commuter_profile(ct: str) -> tuple:
    """Map commuter_type string → (ceiling, floor, road_sensitivity) tuple."""
    ct = ct.lower().strip()
    if any(x in ct for x in ["walk", "foot"]):
        return _COMMUTER_PROFILE["walk"]
    if any(x in ct for x in ["bike", "bicycle", "cycling"]):
        return _COMMUTER_PROFILE["bike"]
    if any(x in ct for x in ["motor", "motorcycle", "motorbike"]):
        return _COMMUTER_PROFILE["motorcycle"]
    if any(x in ct for x in ["commute", "jeepney", "bus", "tricycle", "puj",
                               "lrt", "mrt", "pnr", "rail", "train"]):
        return _COMMUTER_PROFILE["transit"]
    return _COMMUTER_PROFILE["car"]


def _compute_safety_score(route: dict, commuter_type: str = "") -> int:
    """
    Per-commuter safety score (0–100).

    Architecture
    ────────────
    Each commuter type has its own ceiling and floor that reflect its inherent
    physical vulnerability. A car's ceiling (88) is higher than a walker's (72)
    because the car provides crash protection and speed control that walking
    never can.

    Within those bounds, three factors adjust the score:

      1. Road speed proxy  — avg_speed = distance ÷ time.
                             Faster avg speed → likely highway → subtract from
                             ceiling scaled by road_sensitivity for this mode.
                             Cars barely care about speed; pedestrians care a lot.

      2. Distance exposure — longer trips = more total exposure.
                             Small, capped deduction so a 20 km ride doesn't
                             automatically become "risky."

      3. Route position    — id=0 (fastest, highway-biased) → −6
                             id=1 (balanced)                 →  0
                             id=2 (alternate, side streets)  → +6
                             This guarantees a visible spread between route
                             options in the UI even when OSRM returns similar
                             avg speeds.

    Hazard penalties (night / weather / crime / flood) are applied AFTER this
    function by apply_penalty_to_route().  They use proportional reduction
    instead of flat subtraction, so no single source can crash the score to 0.
    """
    dur       = _parse_mins(route.get('time', '0'))
    dist      = _parse_km(route.get('distance', '0'))
    route_idx = route.get('id', 0)

    if dur <= 0:
        # Fallback: use commuter ceiling minus a small buffer
        ceiling, floor, _ = _get_commuter_profile(commuter_type)
        return max(floor, ceiling - 8)

    avg_speed_kmh = (dist / (dur / 60)) if dur > 0 else 0
    ceiling, floor, sensitivity = _get_commuter_profile(commuter_type)

    # ── 1. Road speed deduction ────────────────────────────────────────────
    # No deduction below 30 kph (urban secondary — considered the baseline).
    # Above 30, each extra 10 kph costs (sensitivity) points, capped at 24.
    speed_above_30 = max(0.0, avg_speed_kmh - 30.0)
    speed_deduction = min(24.0, (speed_above_30 / 10.0) * sensitivity)

    # Very slow (<8 kph) = heavy congestion — slight penalty for all modes
    if avg_speed_kmh < 8:
        congestion_penalty = 3
    else:
        congestion_penalty = 0

    # ── 2. Distance exposure deduction ────────────────────────────────────
    if dist > 30:
        dist_deduction = 5
    elif dist > 20:
        dist_deduction = 3
    elif dist > 12:
        dist_deduction = 1
    else:
        dist_deduction = 0

    # ── 3. Route position adjustment ──────────────────────────────────────
    position_adj = _ROUTE_POSITION_ADJ.get(route_idx, 0)

    raw = ceiling - speed_deduction - dist_deduction - congestion_penalty + position_adj
    return int(max(float(floor), min(float(ceiling), raw)))


# ── Proportional penalty helper ───────────────────────────────────────────────

def apply_penalty_to_route(route: dict, raw_penalty: float, commuter_type: str = "") -> int:
    """
    Apply an external hazard penalty (night / weather / crime / flood) to a
    route's safety_score using proportional reduction instead of flat subtraction.

    Why proportional?
      Flat subtraction stacks badly: 4 hazards × 15 pts each = −60 from a 75
      baseline → score of 15, which looks catastrophic for a light rain + night
      commute in a low-crime area.

    Proportional reduction formula:
        new_score = current_score × (1 − reduction_fraction)

    The reduction_fraction is derived from raw_penalty but is capped so that:
      • A single "high" penalty (e.g. raw=20) reduces the score by at most 18%
      • ALL penalties combined can reduce the score by at most 55% from the
        post-base value, so even a walker in a storm at night never falls below
        ~28 (roughly "Caution" rather than "impossible to travel")

    The floor from the commuter profile is always respected as an absolute min.

    Args:
        route:         route dict with 'safety_score' (int, set by _compute_safety_score)
        raw_penalty:   the integer penalty from night/weather/crime/flood tables
        commuter_type: used to retrieve the floor for this mode

    Returns:
        New safety_score (int). Also mutates route['safety_score'] in-place.
    """
    _, floor, _ = _get_commuter_profile(commuter_type)
    current     = float(route.get("safety_score", 75))

    # Map raw_penalty → fraction to reduce.
    # Calibration: raw=5 → 3%, raw=10 → 6%, raw=15 → 9%, raw=20 → 13%, raw=30 → 18%
    # Cap is 18% per penalty source (was 20%) with a higher divisor (160 vs 140)
    # so that stacking 3 penalties still leaves visible spread between routes.
    fraction = min(0.18, raw_penalty / 160.0)

    new_score = current * (1.0 - fraction)
    # Hard floor: commuter floor, and never below 20 (prevents "0/100" UI shock)
    new_score = max(float(max(floor, 20)), new_score)

    route["safety_score"] = int(round(new_score))
    return route["safety_score"]


# ═════════════════════════════════════════════════════════════════════════════
# 2. SAFETY SCORE COLOR CODING
# ═════════════════════════════════════════════════════════════════════════════

def get_score_color(score: int) -> str:
    """
    Returns a hex color for a safety score.

    Thresholds are intentionally mode-agnostic — the score itself already
    encodes the commuter type's vulnerability (a 72 for a walker IS safe
    for a walker; it is not the same as a 72 for a car driver).

      80–100 → deep green  (Very Safe)
      65–79  → green       (Safe)
      50–64  → yellow      (Moderate)
      38–49  → orange      (Caution)
      0–37   → red         (Risky)
    """
    if score >= 80:
        return "#1e8449"   # deep green
    elif score >= 65:
        return "#27ae60"   # green
    elif score >= 50:
        return "#f1c40f"   # yellow
    elif score >= 38:
        return "#e67e22"   # orange
    else:
        return "#e74c3c"   # red


def get_score_label(score: int) -> str:
    """Returns a short human label for a safety score."""
    if score >= 80:
        return "Very Safe"
    elif score >= 65:
        return "Safe"
    elif score >= 50:
        return "Moderate"
    elif score >= 38:
        return "Caution"
    else:
        return "Risky"


def enrich_routes_with_scores(routes: list, commuter_type: str = "") -> list:
    """
    Adds 'score_color' and 'score_label' to each route dict in-place.
    If a route has no 'safety_score' yet (e.g. transit routes that skipped
    rank_routes), computes one via _compute_safety_score rather than
    defaulting everyone to 75 — which caused all routes to show the same score.

    Call this after rank_routes() (for road routes) or directly (for transit).
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
                 or active.get("psws") or 1)

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

# Score penalty applied to safety score when travelling at night, per type.
# Higher = more dangerous at night.
_NIGHT_PENALTY = {
    "walk":       25,   # Pedestrians very exposed at night
    "walking":    25,
    "bike":       20,
    "bicycle":    20,
    "motorcycle": 15,   # Less visible, road risks higher
    "motorbike":  15,
    "tricycle":   12,   # Open vehicle, poorly lit areas
    "jeepney":    8,    # Some routes stop at night
    "bus":        8,
    "commute":    10,
    "car":        5,    # Most protected, but still some risk
    "automobile": 5,
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
    # Late night (10 PM – 4 AM) is more severe
    severe = (hour >= 22 or hour < 4)

    bg    = "#2c3e50" if severe else "#34495e"
    msg   = get_night_warning(commuter_type)
    label = "🌑 Late Night Advisory" if severe else "🌙 Night Travel Advisory"

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
    Applies night-time safety penalties and warnings to all routes in-place.

    Uses proportional reduction (apply_penalty_to_route) instead of flat
    subtraction, so stacking this on top of crime/weather/flood never crashes
    the score to 0.  Faster routes (id=0) still get a slightly larger penalty
    via _route_exposure_multiplier, but the multiplier range is tighter now.

    Call this AFTER enrich_routes_with_scores() in navigation.py.
    """
    base_penalty = get_night_safety_penalty(commuter_type)
    warning      = get_night_warning(commuter_type)

    for r in routes:
        if base_penalty > 0:
            multiplier = _route_exposure_multiplier(r.get('id', 1))
            scaled     = base_penalty * multiplier
            apply_penalty_to_route(r, scaled, commuter_type)
            r['score_color'] = get_score_color(r['safety_score'])
            r['score_label'] = get_score_label(r['safety_score'])
        r['night_warning'] = warning

    return routes