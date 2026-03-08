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

    # Attach safety scores
    for r in routes:
        r['safety_score'] = _compute_safety_score(r, commuter_type)

    # Clean up temp keys
    for r in routes:
        r.pop('_dur', None)
        r.pop('_dist', None)
        r.pop('_balance_score', None)

    # Return in display order: Fastest, Balanced, Alternate
    ordered = [fastest, balanced] + alternates
    for i, r in enumerate(ordered):
        r['id'] = i  # re-index so first route gets thick polyline

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


def _compute_safety_score(route: dict, commuter_type: str = "") -> int:
    """
    Heuristic safety score (0–100) based on:
      - Speed ratio: avg speed = distance / time. Very high avg speed = highway = lower score.
      - Commuter type bonus: walking/biking on slower roads scores higher.
      - Time of day: night travel automatically penalises based on commuter type.
    """
    dur  = _parse_mins(route.get('time', '0'))
    dist = _parse_km(route.get('distance', '0'))

    if dur <= 0:
        return 75  # fallback

    avg_speed_kmh = dist / (dur / 60)  # km/h

    # Base score — penalise high-speed routes (likely expressways)
    if avg_speed_kmh > 80:
        base = 40   # Very fast = likely motorway
    elif avg_speed_kmh > 50:
        base = 60   # Normal urban driving
    elif avg_speed_kmh > 30:
        base = 75   # Slow urban / jeepney pace
    elif avg_speed_kmh > 10:
        base = 88   # Bicycle / tricycle pace
    else:
        base = 95   # Walking pace

    # Commuter type adjustment
    ct = commuter_type.lower()
    if any(x in ct for x in ['walk', 'bike', 'bicycle']):
        base = min(100, base + 5)
    elif any(x in ct for x in ['motorcycle', 'motor']):
        base = max(0, base - 5)
    elif any(x in ct for x in ['commute', 'jeepney', 'tricycle', 'bus']):
        base = max(0, base - 2)

    # Night penalty — automatically reduces score if it's currently nighttime
    night_penalty = get_night_safety_penalty(commuter_type)
    base = max(0, base - night_penalty)

    return base


# ═════════════════════════════════════════════════════════════════════════════
# 2. SAFETY SCORE COLOR CODING
# ═════════════════════════════════════════════════════════════════════════════

def get_score_color(score: int) -> str:
    """
    Returns a hex color for a safety score.
      90–100 → green
      70–89  → yellow-green
      50–69  → orange
      0–49   → red
    """
    if score >= 90:
        return "#27ae60"   # green
    elif score >= 70:
        return "#f1c40f"   # yellow
    elif score >= 50:
        return "#e67e22"   # orange
    else:
        return "#e74c3c"   # red


def get_score_label(score: int) -> str:
    """Returns a short human label for a safety score."""
    if score >= 90:
        return "Safe"
    elif score >= 70:
        return "Moderate"
    elif score >= 50:
        return "Caution"
    else:
        return "Risky"


def enrich_routes_with_scores(routes: list) -> list:
    """
    Adds 'score_color' and 'score_label' to each route dict in-place.
    Call this in navigation.py before returning routes.
    """
    for r in routes:
        score = r.get('safety_score', 75)
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

# PAGASA public RSS — no API key needed
_PAGASA_RSS = "https://pubfiles.pagasa.dost.gov.ph/tamss/weather/bulletin.json"
_BAGYO_WATCH = "https://bagong.pagasa.dost.gov.ph/tropical-cyclone/public-storm-warning-signals"


def get_typhoon_signal() -> dict:
    """
    Fetch the current PAGASA tropical cyclone bulletin and return a summary.
    Falls back gracefully if the endpoint is unreachable.

    Returns dict:
        {
          "active":   bool,
          "signal":   int or None,   # 1–5
          "name":     str or None,   # cyclone name
          "headline": str,
          "color":    str,           # banner background hex
          "source":   str,           # URL for "more info" link
        }
    """
    try:
        resp = requests.get(_PAGASA_RSS, timeout=6,
                            headers={'User-Agent': 'SafeRoute/1.0'})
        resp.raise_for_status()
        data = resp.json()

        # PAGASA bulletin JSON structure varies — try common keys
        cyclones = data.get("cyclones") or data.get("data") or []
        if isinstance(cyclones, dict):
            cyclones = list(cyclones.values())

        if not cyclones:
            return _no_typhoon()

        # Pick the highest signal active cyclone
        active = None
        for c in cyclones:
            if isinstance(c, dict) and c.get("active", True):
                active = c
                break

        if not active:
            return _no_typhoon()

        name   = active.get("name") or active.get("international_name") or "Tropical Cyclone"
        signal = int(active.get("signal") or active.get("max_signal") or 1)

        return {
            "active":   True,
            "signal":   signal,
            "name":     name,
            "headline": f"⚠️ Typhoon {name} — Signal #{signal} in effect",
            "color":    _signal_color(signal),
            "source":   _BAGYO_WATCH,
        }

    except Exception:
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

    - Reduces safety_score by the night penalty for the commuter type
    - Updates score_color and score_label to reflect the new score
    - Adds 'night_warning' string to each route

    Call this AFTER enrich_routes_with_scores() in navigation.py.

    Args:
        routes: list of route dicts
        commuter_type: e.g. 'walk', 'jeepney', 'car'

    Returns:
        Same list with updated safety fields.
    """
    penalty = get_night_safety_penalty(commuter_type)
    warning = get_night_warning(commuter_type)

    for r in routes:
        if penalty > 0:
            original = r.get('safety_score', 75)
            r['safety_score'] = max(0, original - penalty)
            # Recompute color + label with the penalised score
            r['score_color'] = get_score_color(r['safety_score'])
            r['score_label'] = get_score_label(r['safety_score'])
        r['night_warning'] = warning

    return routes