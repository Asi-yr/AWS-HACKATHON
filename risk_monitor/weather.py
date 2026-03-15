"""
weather.py
----------
Feature: Live Weather Risk for SafeRoute.

Uses Open-Meteo (https://open-meteo.com/) — completely free, no API key needed.
Fetches current weather at any lat/lon and returns a risk assessment
relevant to Philippine commuters (rain, wind, visibility, heat index).

Nothing runs on import. All logic is in pure functions.

Integration points:
  - main.py  : call get_weather_risk(lat, lon) and pass result to render_template
               as weather_banner=get_weather_banner_html(risk)
  - index.html : add {{ weather_banner | safe }} after {{ night_banner | safe }}
  - navigation.py (optional): pass weather risk into route safety scoring via
               apply_weather_to_routes(routes, risk)

New modules needed (add to requirements.txt):
  # new modules to add
  # (none — open-meteo uses plain requests which is already installed)
"""

import requests
from datetime import datetime, timezone, timedelta

# ── Open-Meteo endpoint ───────────────────────────────────────────────────────

_OM_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather interpretation codes → human label + severity
# Full table: https://open-meteo.com/en/docs#weathervariables
_WMO_CODES = {
    0:  ("Clear sky",              "clear"),
    1:  ("Mainly clear",           "clear"),
    2:  ("Partly cloudy",          "cloudy"),
    3:  ("Overcast",               "cloudy"),
    45: ("Foggy",                  "fog"),
    48: ("Icy fog",                "fog"),
    51: ("Light drizzle",          "light_rain"),
    53: ("Moderate drizzle",       "light_rain"),
    55: ("Dense drizzle",          "rain"),
    61: ("Slight rain",            "light_rain"),
    63: ("Moderate rain",          "rain"),
    65: ("Heavy rain",             "heavy_rain"),
    71: ("Slight snow",            "rain"),       # unlikely in PH but handled
    73: ("Moderate snow",          "rain"),
    75: ("Heavy snow",             "heavy_rain"),
    80: ("Slight showers",         "light_rain"),
    81: ("Moderate showers",       "rain"),
    82: ("Violent showers",        "heavy_rain"),
    95: ("Thunderstorm",           "storm"),
    96: ("Thunderstorm w/ hail",   "storm"),
    99: ("Thunderstorm w/ hail",   "storm"),
}

# Risk levels in ascending severity
_RISK_LEVELS = ["clear", "cloudy", "fog", "light_rain", "rain", "heavy_rain", "storm"]

# Per-risk banner colors
_RISK_COLORS = {
    "clear":      "#27ae60",
    "cloudy":     "#7f8c8d",
    "fog":        "#95a5a6",
    "light_rain": "#2980b9",
    "rain":       "#1a5276",
    "heavy_rain": "#c0392b",
    "storm":      "#6c3483",
}

# Per-risk commuter warnings — keyed by (risk_level, commuter_type_group)
# commuter_type_group: "walk", "bike", "motorcycle", "commute", "car", "train"
_RISK_WARNINGS = {
    "storm": {
        "walk":       "⛈️ Thunderstorm active — do NOT walk outdoors. Seek shelter.",
        "bike":       "⛈️ Thunderstorm — cycling is extremely dangerous. Stay indoors.",
        "motorcycle": "⛈️ Thunderstorm — riding a motorcycle now is life-threatening.",
        "commute":    "⛈️ Thunderstorm — expect cancelled routes and flooding. Delay trip.",
        "car":        "⛈️ Thunderstorm — zero visibility possible. Pull over if needed.",
        "train":      "⛈️ Thunderstorm — trains may be delayed. Check schedules.",
    },
    "heavy_rain": {
        "walk":       "🌧️ Heavy rain — bring umbrella, expect flooded sidewalks.",
        "bike":       "🌧️ Heavy rain — slippery roads, reduced braking. Ride slowly.",
        "motorcycle": "🌧️ Heavy rain — poor visibility and slick roads. Extra caution.",
        "commute":    "🌧️ Heavy rain — expect flooded underpasses and rerouted jeepneys.",
        "car":        "🌧️ Heavy rain — slow down, headlights on, watch for floods.",
        "train":      "🌧️ Heavy rain — trains likely running but check for delays.",
    },
    "rain": {
        "walk":       "🌦️ Rain ongoing — bring umbrella or raincoat.",
        "bike":       "🌦️ Rain — reduce speed on wet roads.",
        "motorcycle": "🌦️ Rain — wear rain gear, avoid painted road markings (slippery).",
        "commute":    "🌦️ Rain — allow extra travel time for traffic and flooding.",
        "car":        "🌦️ Rain — headlights on, increase following distance.",
        "train":      "🌦️ Rain — minor delays possible.",
    },
    "light_rain": {
        "walk":       "🌂 Light rain — bring a small umbrella just in case.",
        "bike":       "🌂 Light drizzle — roads getting wet, take care on corners.",
        "motorcycle": "🌂 Light rain — roads are slippery. Ride defensively.",
        "commute":    "🌂 Light rain — minor delays expected.",
        "car":        "🌂 Light rain — wipers on, stay alert.",
        "train":      "🌂 Light rain — no significant impact expected.",
    },
    "fog": {
        "walk":       "🌫️ Foggy — stay visible, use lit paths.",
        "bike":       "🌫️ Fog — use front and rear lights.",
        "motorcycle": "🌫️ Fog — reduce speed significantly, use low beam.",
        "commute":    "🌫️ Fog — traffic slowdowns likely, expect delays.",
        "car":        "🌫️ Fog — use fog lights if available, reduce speed.",
        "train":      "🌫️ Fog — trains usually unaffected.",
    },
}

_DEFAULT_WARNING = "🌤️ Weather conditions are acceptable for travel."

# Philippine Standard Time
_PHT = timezone(timedelta(hours=8))


def _group_commuter(commuter_type: str) -> str:
    """Map any commuter_type string to a warning group key."""
    ct = commuter_type.lower().strip()
    if any(x in ct for x in ["walk", "foot"]):
        return "walk"
    if any(x in ct for x in ["bike", "bicycle", "cycling"]):
        return "bike"
    if any(x in ct for x in ["motor", "motorcycle"]):
        return "motorcycle"
    if any(x in ct for x in ["commute", "jeepney", "bus", "tricycle", "puj"]):
        return "commute"
    if any(x in ct for x in ["lrt", "mrt", "pnr", "rail", "train", "line"]):
        return "train"
    return "car"


def get_weather_risk(lat: float, lon: float) -> dict:
    """
    Fetch current weather at (lat, lon) via Open-Meteo and return a
    structured risk assessment.

    Args:
        lat: latitude (e.g. 14.5995 for Manila)
        lon: longitude (e.g. 120.9842 for Manila)
    

    Returns:
        {
          "ok":           bool,         # False if fetch failed
          "risk_level":   str,          # one of _RISK_LEVELS
          "wmo_code":     int,
          "description":  str,          # e.g. "Heavy rain"
          "temp_c":       float,
          "feels_like_c": float,
          "humidity_pct": int,
          "wind_kph":     float,
          "rain_mm":      float,        # precipitation in last hour
          "color":        str,          # hex for banner
          "fetched_at":   str,          # ISO timestamp PHT
          "error":        str or None,
        }
    """

    # return {
    #     "ok": True, "risk_level": "storm",
    #     "description": "TEST STORM", "temp_c": 22,
    #     "feels_like_c": 20, "humidity_pct": 95,
    #     "wind_kph": 85, "rain_mm": 40,
    #     "color": "#6c3483", "fetched_at": "TEST", "error": None,
    # }

    params = {
        "latitude":            lat,
        "longitude":           lon,
        "current":             [
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "precipitation",
            "weather_code",
            "wind_speed_10m",
        ],
        "wind_speed_unit":     "kmh",
        "timezone":            "Asia/Manila",
        "forecast_days":       1,
    }

    try:
        resp = requests.get(_OM_URL, params=params,
                            headers={"User-Agent": "SafeRoute/1.0"}, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        cur  = data.get("current", {})

        wmo_code    = int(cur.get("weather_code", 0))
        description, risk_level = _WMO_CODES.get(wmo_code, ("Unknown", "cloudy"))

        temp_c      = float(cur.get("temperature_2m",        0))
        feels_like  = float(cur.get("apparent_temperature",  temp_c))
        humidity    = int(cur.get("relative_humidity_2m",    0))
        wind_kph    = float(cur.get("wind_speed_10m",        0))
        rain_mm     = float(cur.get("precipitation",         0))

        # Bump risk level if wind is very strong (signal-level winds)
        if wind_kph >= 100 and _RISK_LEVELS.index(risk_level) < _RISK_LEVELS.index("storm"):
            risk_level = "storm"
        elif wind_kph >= 60 and _RISK_LEVELS.index(risk_level) < _RISK_LEVELS.index("heavy_rain"):
            risk_level = "heavy_rain"

        return {
            "ok":          True,
            "risk_level":  risk_level,
            "wmo_code":    wmo_code,
            "description": description,
            "temp_c":      temp_c,
            "feels_like_c": feels_like,
            "humidity_pct": humidity,
            "wind_kph":    wind_kph,
            "rain_mm":     rain_mm,
            "color":       _RISK_COLORS.get(risk_level, "#7f8c8d"),
            "fetched_at":  datetime.now(_PHT).strftime("%Y-%m-%d %H:%M PHT"),
            "error":       None,
        }

    except requests.exceptions.Timeout:
        return _weather_error("Open-Meteo timed out.")
    except requests.exceptions.ConnectionError:
        return _weather_error("Could not reach Open-Meteo.")
    except Exception as e:
        return _weather_error(str(e))


def _weather_error(msg: str) -> dict:
    return {
        "ok":          False,
        "risk_level":  "clear",
        "wmo_code":    0,
        "description": "Weather unavailable",
        "temp_c":      0,
        "feels_like_c": 0,
        "humidity_pct": 0,
        "wind_kph":    0,
        "rain_mm":     0,
        "color":       "#7f8c8d",
        "fetched_at":  "",
        "error":       msg,
    }


def get_weather_warning(weather: dict, commuter_type: str) -> str:
    """
    Returns a human-readable warning string for the current weather
    tailored to the commuter type.

    Args:
        weather:       result dict from get_weather_risk()
        commuter_type: e.g. 'walk', 'motorcycle', 'commute'

    Returns:
        Warning string, or a safe/clear message if no risk.
    """
    if not weather.get("ok"):
        return ""
    risk  = weather.get("risk_level", "clear")
    group = _group_commuter(commuter_type)
    warnings = _RISK_WARNINGS.get(risk, {})
    return warnings.get(group, _DEFAULT_WARNING)


def get_weather_banner_html(weather: dict, commuter_type: str = "") -> str:
    """
    Returns an HTML banner string for current weather risk.
    Returns empty string if weather is clear/cloudy and no warning needed.

    Inject into index.html via Jinja: {{ weather_banner | safe }}
    Place after {{ night_banner | safe }} inside <body>.

    Args:
        weather:       result from get_weather_risk()
        commuter_type: optional, to tailor the warning text
    """
    if not weather.get("ok"):
        return ""

    risk = weather.get("risk_level", "clear")
    if risk in ("clear", "cloudy"):
        return ""   # no banner needed for good weather

    color   = weather["color"]
    desc    = weather["description"]
    temp    = weather["temp_c"]
    wind    = weather["wind_kph"]
    rain    = weather["rain_mm"]
    warning = get_weather_warning(weather, commuter_type) if commuter_type else ""

    stats = f"{desc} | {temp:.0f}°C | 💨 {wind:.0f} km/h"
    if rain > 0:
        stats += f" | 🌧️ {rain:.1f} mm/hr"

    body = stats
    if warning:
        body += f" — {warning}"

    return (
        f'<div class="weather-banner" style="background:{color};color:#fff;'
        f'padding:8px 16px;font-size:13px;font-weight:bold;text-align:center;'
        f'position:fixed;top:0;left:0;right:0;z-index:99997;'
        f'box-shadow:0 2px 6px rgba(0,0,0,0.3);">'
        f'🌦️ Live Weather: {body}'
        f'</div>'
    )


def get_weather_risk_penalty(weather: dict, commuter_type: str) -> int:
    """
    Returns a safety score penalty (int) based on current weather,
    commuter type, AND time of day.

    Key design principles:
      • Daytime penalties are moderate — weather is visible and manageable.
      • Night-time penalties are significantly higher — wet/dark roads, poor
        visibility, fewer people around, and slower emergency response.
      • Vulnerability order: walk > bike > motorcycle > commute/transit > car
        Walk is most exposed (no shelter, on foot, slowest to react).
        Motorcycle is more dangerous than transit because the rider is
        physically exposed to rain, wind, and slippery roads.
        Car has the most crash protection and is enclosed.

    Daytime penalty table (6 AM – 6 PM):
        storm      → walk: 18, bike: 16, motorcycle: 14, commute: 8,  train: 4, car: 5
        heavy_rain → walk: 12, bike: 10, motorcycle:  9, commute: 5,  train: 3, car: 3
        rain       → walk:  6, bike:  5, motorcycle:  5, commute: 3,  train: 1, car: 2
        light_rain → walk:  3, bike:  3, motorcycle:  3, commute: 1,  train: 0, car: 1
        fog        → walk:  2, bike:  2, motorcycle:  5, commute: 2,  train: 0, car: 3

    Night-time penalty table (6 PM – 6 AM):
        Multiplies daytime values × a per-mode night multiplier:
          walk:        × 2.0  — unlit paths + wet = very dangerous
          bike:        × 1.8  — reflector loss in rain + slick roads
          motorcycle:  × 1.7  — wet+dark road is a leading crash cause
          commute:     × 1.5  — waiting at stops in rain/dark = high exposure
          train:       × 1.2  — minimal exposure change (sheltered platform)
          car:         × 1.3  — headlights reduce but don't eliminate wet-road risk
    """
    if not weather.get("ok"):
        return 0

    risk  = weather.get("risk_level", "clear")
    group = _group_commuter(commuter_type)

    # ── Daytime base penalties ────────────────────────────────────────────────
    # Calibrated so that even a storm during the day is a warning, not a crisis,
    # unless you're walking. The 3–5 pt range for light rain is informative,
    # not alarming. Night multipliers below bring these up to realistic levels.
    _DAY_PENALTY = {
        "storm": {
            "walk": 18, "bike": 16,
            "motorcycle": 14,
            "commute": 8, "train": 4,
            "car": 5,
        },
        "heavy_rain": {
            "walk": 12, "bike": 10,
            "motorcycle": 9,
            "commute": 5, "train": 3,
            "car": 3,
        },
        "rain": {
            "walk": 6, "bike": 5,
            "motorcycle": 5,
            "commute": 3, "train": 1,
            "car": 2,
        },
        "light_rain": {
            "walk": 3, "bike": 3,
            "motorcycle": 3,
            "commute": 1, "train": 0,
            "car": 1,
        },
        "fog": {
            "walk": 2, "bike": 2,
            "motorcycle": 5,
            "commute": 2, "train": 0,
            "car": 3,
        },
    }

    # ── Night multipliers per mode ────────────────────────────────────────────
    # Applied when current PHT hour is 18–23 or 0–5.
    # Walk and bike get the largest multipliers: rain + darkness + no lights
    # is extremely hazardous for unprotected commuters.
    _NIGHT_MULTIPLIER = {
        "walk":       2.0,
        "bike":       1.8,
        "motorcycle": 1.7,
        "commute":    1.5,
        "train":      1.2,
        "car":        1.3,
    }

    base = _DAY_PENALTY.get(risk, {}).get(group, 0)
    if base == 0:
        return 0

    # Apply night multiplier when it's nighttime (reuse PHT-aware check)
    pht_hour = datetime.now(_PHT).hour
    is_night = (pht_hour >= 18 or pht_hour < 6)

    if is_night:
        multiplier = _NIGHT_MULTIPLIER.get(group, 1.5)
        return round(base * multiplier)

    return base


def apply_weather_to_routes(routes: list, weather: dict, commuter_type: str) -> list:
    """
    Applies weather-based safety score penalty to all routes in-place.
    Also adds 'weather_warning' key to each route.

    Uses proportional reduction (apply_penalty_to_route) so stacking with
    night/crime/flood never crashes the score to 0.

    Faster routes (id=0, highway-biased) still receive a slightly larger
    penalty via the exposure multiplier — highways are more exposed in rain.

    Call this AFTER apply_night_safety() in navigation.py.
    """
    from risk_monitor.features import get_score_color, get_score_label, apply_penalty_to_route, _route_exposure_multiplier

    base_penalty = get_weather_risk_penalty(weather, commuter_type)
    warning      = get_weather_warning(weather, commuter_type)

    for r in routes:
        if base_penalty > 0:
            multiplier = _route_exposure_multiplier(r.get('id', 1))
            apply_penalty_to_route(r, base_penalty * multiplier, commuter_type)
            r["score_color"] = get_score_color(r["safety_score"])
            r["score_label"] = get_score_label(r["safety_score"])
        r["weather_warning"] = warning if base_penalty > 0 else ""

    return routes


# ── 5-day forecast helpers ────────────────────────────────────────────────────

_WEEKDAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

_RISK_FORECAST_LABEL = {
    "clear":      "SAFE",
    "cloudy":     "SAFE",
    "fog":        "LOW",
    "light_rain": "LOW",
    "rain":       "MED",
    "heavy_rain": "HIGH",
    "storm":      "HIGH",
}

_RISK_FORECAST_COLOR = {
    "SAFE": "#27ae60",
    "LOW":  "#f39c12",
    "MED":  "#e67e22",
    "HIGH": "#e74c3c",
}

_WMO_EMOJI = {
    "clear":      "☀️",
    "cloudy":     "⛅",
    "fog":        "🌫️",
    "light_rain": "🌦️",
    "rain":       "🌧️",
    "heavy_rain": "🌧️",
    "storm":      "⛈️",
}


def get_forecast(lat: float, lon: float, days: int = 5) -> list:
    """
    Fetch N-day daily weather forecast for (lat, lon) via Open-Meteo.

    Returns a list of dicts (one per day):
        {
          "day_label":   str,   # "TODAY", "Tue", "Wed", etc.
          "date":        str,   # "2026-03-15"
          "temp_max_c":  float,
          "temp_min_c":  float,
          "precip_pct":  int,   # precipitation probability %
          "risk_level":  str,   # one of _RISK_LEVELS
          "risk_label":  str,   # "SAFE" | "LOW" | "MED" | "HIGH"
          "risk_color":  str,   # hex color
          "description": str,   # "Heavy rain"
          "icon":        str,   # emoji
          "wmo_code":    int,
        }

    Returns empty list on any failure.
    """
    params = {
        "latitude":  lat,
        "longitude": lon,
        "daily": [
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_probability_max",
        ],
        "wind_speed_unit": "kmh",
        "timezone":        "Asia/Manila",
        "forecast_days":   days,
    }

    try:
        resp = requests.get(_OM_URL, params=params,
                            headers={"User-Agent": "SafeRoute/1.0"}, timeout=8)
        resp.raise_for_status()
        data  = resp.json()
        daily = data.get("daily", {})

        times         = daily.get("time", [])
        wmo_codes     = daily.get("weather_code", [])
        temp_max_list = daily.get("temperature_2m_max", [])
        temp_min_list = daily.get("temperature_2m_min", [])
        precip_list   = daily.get("precipitation_probability_max", [])

        today_str = datetime.now(_PHT).strftime("%Y-%m-%d")
        result    = []

        for i, date_str in enumerate(times):
            wmo_code               = int(wmo_codes[i])     if i < len(wmo_codes)     else 0
            description, risk_level = _WMO_CODES.get(wmo_code, ("Partly cloudy", "cloudy"))
            temp_max               = float(temp_max_list[i]) if i < len(temp_max_list) else 0.0
            temp_min               = float(temp_min_list[i]) if i < len(temp_min_list) else 0.0
            precip_pct             = int(precip_list[i])    if i < len(precip_list)   else 0

            if date_str == today_str:
                day_label = "TODAY"
            else:
                try:
                    dt        = datetime.fromisoformat(date_str)
                    day_label = _WEEKDAY_ABBR[dt.weekday()]
                except Exception:
                    day_label = date_str

            risk_label = _RISK_FORECAST_LABEL.get(risk_level, "LOW")
            risk_color = _RISK_FORECAST_COLOR.get(risk_label, "#7f8c8d")
            icon       = _WMO_EMOJI.get(risk_level, "🌤️")

            result.append({
                "day_label":   day_label,
                "date":        date_str,
                "temp_max_c":  temp_max,
                "temp_min_c":  temp_min,
                "precip_pct":  precip_pct,
                "risk_level":  risk_level,
                "risk_label":  risk_label,
                "risk_color":  risk_color,
                "description": description,
                "icon":        icon,
                "wmo_code":    wmo_code,
            })

        return result

    except Exception as e:
        print(f"[weather] get_forecast error: {e}")
        return []