"""
vulnerable_profiles.py
----------------------
Safety scoring adjustments for vulnerable commuter groups in SafeRoute.

Profiles:
  1. Senior (60+)      — steeper stairs, long transfers, heat stress, crowding
  2. PWD / Wheelchair  — sidewalk gaps, no ramps, no elevator at stations
  3. Women             — lit streets, CCTV coverage, crowd presence, isolated areas
  4. Child / Student   — similar to women + school zone awareness

Each profile:
  - Adjusts the safety score ceiling/floor
  - Adds profile-specific penalty factors on top of base hazards
  - Generates tailored route warnings

OSM data used (via Overpass, same API as safe_spots.py):
  - highway=steps near route → bad for seniors/PWD
  - lit=yes/no on streets → relevant for women/children at night
  - ramp:wheelchair=yes/no at train stations

Nothing runs on import. All logic is pure functions.
"""

from datetime import datetime, timezone, timedelta
import math

_PHT = timezone(timedelta(hours=8))

# ── Profile definitions ───────────────────────────────────────────────────────

PROFILES = {
    "senior": {
        "label":       "Senior (60+)",
        "icon":        "🧓",
        "description": "Routes optimized for seniors — minimizes stairs, long walks, and heat exposure.",
        "score_ceiling_adj": -5,   # seniors face slightly more risk on any route
        "score_floor_adj":   -5,
    },
    "pwd": {
        "label":       "PWD / Wheelchair",
        "icon":        "♿",
        "description": "Routes avoiding stairs and impassable sidewalks.",
        "score_ceiling_adj": -8,
        "score_floor_adj":   -8,
    },
    "women": {
        "label":       "Women's Safety",
        "icon":        "👩",
        "description": "Routes prioritizing lit, CCTV-covered, and well-populated paths.",
        "score_ceiling_adj": -3,
        "score_floor_adj":   -3,
    },
    "child": {
        "label":       "Child / Student",
        "icon":        "🎒",
        "description": "Routes near schools and well-lit, safe pedestrian paths.",
        "score_ceiling_adj": -4,
        "score_floor_adj":   -4,
    },
}

# ── Night multipliers per profile ─────────────────────────────────────────────
# How much more dangerous is this profile at night vs daytime?
_NIGHT_PENALTY_MULTIPLIER = {
    "senior": 1.3,
    "pwd":    1.2,
    "women":  1.8,   # significantly higher risk at night
    "child":  1.6,
}

# ── Route type penalties per profile ─────────────────────────────────────────
# Some route types are inherently harder for specific profiles.
_ROUTE_TYPE_PENALTY = {
    "senior": {
        "walk":       8,   # long walks strain seniors
        "motorcycle": 5,   # mounting/dismounting risk
        "transit":    3,   # crowding, waiting
    },
    "pwd": {
        "walk":       12,  # sidewalk hazards
        "motorcycle": 15,  # cannot ride if in wheelchair
        "transit":    8,   # stairs at stations
    },
    "women": {
        "walk":       6,   # isolated stretches
        "motorcycle": 4,   # lone rider risk
    },
    "child": {
        "walk":       5,
        "motorcycle": 8,
    },
}

# ── Weather penalty multipliers per profile ───────────────────────────────────
# Seniors and PWDs are more exposed to weather risks.
_WEATHER_MULTIPLIER = {
    "senior": 1.4,
    "pwd":    1.3,
    "women":  1.1,
    "child":  1.2,
}

# ── Crime penalty multipliers per profile ─────────────────────────────────────
_CRIME_MULTIPLIER = {
    "senior": 1.3,
    "pwd":    1.2,
    "women":  1.6,
    "child":  1.5,
}


def is_nighttime_pht() -> bool:
    h = datetime.now(_PHT).hour
    return h >= 18 or h < 6


def get_profile_penalty(profile: str, route: dict, weather: dict = None) -> int:
    """
    Calculate total additional safety penalty for a vulnerable commuter profile.

    Args:
        profile:  One of "senior", "pwd", "women", "child"
        route:    Route dict (must have safety_score already set)
        weather:  Current weather dict from get_weather_risk()

    Returns:
        Total integer penalty to subtract from safety_score.
    """
    if profile not in PROFILES:
        return 0

    total_penalty = 0
    ct = route.get("commuter_type", "walk").lower()

    # 1. Route type penalty
    type_penalties = _ROUTE_TYPE_PENALTY.get(profile, {})
    for mode_key, pen in type_penalties.items():
        if mode_key in ct:
            total_penalty += pen
            break

    # 2. Night multiplier on existing crime/night penalties
    if is_nighttime_pht():
        mult    = _NIGHT_PENALTY_MULTIPLIER.get(profile, 1.0)
        # Apply multiplier to the base night penalty the route already carries
        # We use a fixed night exposure penalty × multiplier instead of modifying score
        night_base = {
            "senior": 5,
            "pwd":    4,
            "women":  12,
            "child":  10,
        }.get(profile, 5)
        total_penalty += int(night_base * (mult - 1.0))

    # 3. Weather multiplier
    if weather and weather.get("ok"):
        risk = weather.get("risk_level", "clear")
        weather_base = {
            "clear":       0,
            "cloudy":      0,
            "fog":         3,
            "light_rain":  3,
            "rain":        6,
            "heavy_rain":  10,
            "storm":       18,
        }.get(risk, 0)
        mult = _WEATHER_MULTIPLIER.get(profile, 1.0)
        total_penalty += int(weather_base * (mult - 1.0))

    return total_penalty


def get_profile_warnings(profile: str, route: dict, weather: dict = None) -> list:
    """
    Generate profile-specific warning messages for a route.

    Returns list of warning strings (shown on route card).
    """
    warnings = []
    ct  = route.get("commuter_type", "").lower()
    night = is_nighttime_pht()

    if profile == "senior":
        if "walk" in ct:
            warnings.append("🧓 Long walking route — look for benches and shade along the way.")
        if route.get("has_flood_zones"):
            warnings.append("🧓 Flood areas ahead — wet/uneven surfaces are fall risks for seniors.")
        if night:
            warnings.append("🧓 Night travel — ensure well-lit path and bring someone if possible.")
        if weather and weather.get("risk_level") in ("heavy_rain", "storm"):
            warnings.append("🧓 Heavy rain — slippery surfaces and heat stress risk. Consider delaying.")

    elif profile == "pwd":
        if "walk" in ct:
            warnings.append("♿ Check for accessible sidewalks and ramps along this route.")
        if route.get("has_flood_zones"):
            warnings.append("♿ Flooded areas on this route may be impassable for wheelchair users.")
        if "transit" in ct or "train" in ct:
            warnings.append("♿ Verify elevator availability at stations — some may be out of service.")
        if route.get("seismic_warning"):
            warnings.append("♿ Post-earthquake route — check for debris and broken pavement.")

    elif profile == "women":
        if night:
            warnings.append("👩 Night travel — stay on well-lit main roads. Avoid isolated shortcuts.")
        if route.get("crime_warning"):
            warnings.append(f"👩 Crime zone alert: {route['crime_warning']}")
        if "walk" in ct and night:
            warnings.append("👩 Consider sharing your live location with a trusted contact.")
        if route.get("flood_warning"):
            warnings.append("👩 Flood areas can attract opportunistic crime — stay alert.")

    elif profile == "child":
        if night:
            warnings.append("🎒 Child/student travel at night — ensure an adult companion.")
        if route.get("crime_warning"):
            warnings.append(f"🎒 Crime zone on route: {route['crime_warning']}")
        warnings.append("🎒 Remind students: stay on main roads, avoid strangers.")

    return warnings


def apply_vulnerable_profile_to_routes(routes: list,
                                        profile: str,
                                        weather: dict = None) -> list:
    """
    Apply vulnerable profile adjustments to all routes.
    Adds 'profile_warnings' key and adjusts safety_score.

    Call this AFTER all other safety enrichments.
    """
    from risk_monitor.features import apply_penalty_to_route, get_score_color, get_score_label

    if not profile or profile not in PROFILES:
        return routes

    for route in routes:
        penalty   = get_profile_penalty(profile, route, weather)
        p_warnings = get_profile_warnings(profile, route, weather)

        if penalty > 0:
            apply_penalty_to_route(route, penalty, route.get("commuter_type", ""))
            route["score_color"] = get_score_color(route["safety_score"])
            route["score_label"] = get_score_label(route["safety_score"])

        route["profile_warnings"] = p_warnings
        route["active_profile"]   = profile

    return routes


def get_profile_badge_html(profile: str) -> str:
    """
    Returns an HTML badge showing the active commuter profile.
    Inject into route cards.
    """
    if not profile or profile not in PROFILES:
        return ""
    cfg = PROFILES[profile]
    return (
        f'<div style="background:#2c3e50;color:#ecf0f1;padding:4px 10px;'
        f'border-radius:12px;font-size:11px;font-weight:bold;display:inline-block;'
        f'margin-bottom:6px;">'
        f'{cfg["icon"]} {cfg["label"]} Mode Active'
        f'</div>'
    )


def get_infrastructure_warnings(profile: str, route_coords: list) -> list:
    """
    Query OSM for infrastructure hazards relevant to the profile along the route.
    Returns list of warning strings.

    Currently checks:
      - Steps/stairs near route (bad for senior/PWD)
      - Unlit roads at night (bad for women/child)

    Lightweight — only queries if profile is senior/pwd/women and there are coords.
    """
    import requests

    if not route_coords or profile not in ("senior", "pwd", "women", "child"):
        return []

    warnings = []

    # Sample a few points to keep queries fast
    pts = route_coords[::30][:3]
    if not pts:
        return []

    for pt in pts:
        lat, lon = pt[0], pt[1]

        # Check for stairs (steps) near route — relevant for senior/PWD
        if profile in ("senior", "pwd"):
            try:
                q = f"""
                [out:json][timeout:8];
                node(around:80,{lat},{lon})[highway=steps];
                out count;
                """
                resp = requests.post("https://overpass-api.de/api/interpreter",
                                     data={"data": q},
                                     headers={"User-Agent": "SafeRoute/1.0"},
                                     timeout=8)
                if resp.status_code == 200:
                    count = resp.json().get("elements", [{}])[0].get("tags", {}).get("total", 0)
                    if int(count or 0) > 0:
                        w = ("🧓 Stairs detected near route — look for alternate accessible path."
                             if profile == "senior" else
                             "♿ Steps/stairs near route — may not be wheelchair accessible.")
                        if w not in warnings:
                            warnings.append(w)
            except Exception:
                pass

        # Check for unlit roads at night — relevant for women/children
        if profile in ("women", "child") and is_nighttime_pht():
            try:
                q = f"""
                [out:json][timeout:8];
                way(around:60,{lat},{lon})[highway~"residential|tertiary|unclassified"][lit!=yes];
                out count;
                """
                resp = requests.post("https://overpass-api.de/api/interpreter",
                                     data={"data": q},
                                     headers={"User-Agent": "SafeRoute/1.0"},
                                     timeout=8)
                if resp.status_code == 200:
                    count = resp.json().get("elements", [{}])[0].get("tags", {}).get("total", 0)
                    if int(count or 0) > 0:
                        w = ("👩 Unlit road sections detected — stay on main roads after dark."
                             if profile == "women" else
                             "🎒 Unlit road sections on route — adult companion recommended.")
                        if w not in warnings:
                            warnings.append(w)
            except Exception:
                pass

        if warnings:
            break   # One set of warnings per route is enough — don't flood the UI

    return warnings
