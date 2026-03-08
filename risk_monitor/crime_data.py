"""
crime_data.py
-------------
Feature: Real-Time Crime Risk for SafeRoute.

Scrapes recent crime news for a given Philippine area using DuckDuckGo
(already installed via ddgs in llm.py), then uses Gemini to extract a
structured crime risk level. Result is cached to disk for 6 hours so
it does not fire on every single route request.

Nothing runs on import. All logic is in pure functions.

Integration in main.py (add 3 lines — see bottom of this file):
    from risk_monitor.crime_data import get_crime_risk_for_area, apply_crime_to_routes, get_crime_warning_html

    Inside get_routes(), after apply_reports_to_routes(...):
        crime = get_crime_risk_for_area(orig_lat, orig_lon, origin_text or "")
        apply_crime_to_routes(routes, crime, commuter_type)

    Inside home(), pass to render_template:
        crime_banner=get_crime_warning_html(crime)   # optional top banner

No new pip packages needed — uses ddgs, requests, BeautifulSoup, and
google-genai, all of which are already in requirements.txt via llm.py.
"""

import os
import json
import re
import time
from datetime import datetime, timezone, timedelta

# ── Cache config ──────────────────────────────────────────────────────────────
_CACHE_DIR      = "transit_data"          # same folder llm.py uses
_CACHE_PREFIX   = "crime_"
_CACHE_TTL_SEC  = 6 * 3600               # 6 hours — crime news doesn't refresh faster

# ── Risk config ───────────────────────────────────────────────────────────────
_CRIME_COLORS = {
    "none":     "#27ae60",
    "low":      "#f39c12",
    "moderate": "#e67e22",
    "high":     "#e74c3c",
    "error":    "#7f8c8d",
}

_CRIME_PENALTY = {
    "none":     0,
    "low":      8,
    "moderate": 18,
    "high":     28,
}

# Per-risk, per-commuter-group warnings
_CRIME_WARNINGS = {
    "high": {
        "walk":       "🚨 High crime risk in this area — avoid walking alone, stay on busy lit streets.",
        "bike":       "🚨 High crime risk — snatching incidents reported. Lock bike, stay alert.",
        "motorcycle": "🚨 High crime risk — holdups reported. Avoid stopping in dark spots.",
        "commute":    "🚨 High crime risk near this route — keep bags close, stay aware.",
        "car":        "🚨 High crime risk — keep doors locked, avoid isolated roads.",
        "train":      "🚨 High crime risk near stations — watch your belongings at platforms.",
    },
    "moderate": {
        "walk":       "⚠️ Moderate crime risk — stay on main roads and well-lit paths.",
        "bike":       "⚠️ Moderate crime risk — lock your bike, don't leave it unattended.",
        "motorcycle": "⚠️ Moderate crime risk — be alert at intersections and traffic stops.",
        "commute":    "⚠️ Moderate crime risk — keep valuables out of sight on public transport.",
        "car":        "⚠️ Moderate crime risk — avoid leaving valuables visible in your car.",
        "train":      "⚠️ Moderate crime risk — hold your bag in front of you on crowded trains.",
    },
    "low": {
        "walk":       "🟡 Low crime risk — general caution advised, especially at night.",
        "bike":       "🟡 Low crime risk — standard precautions apply.",
        "motorcycle": "🟡 Low crime risk — stay alert at slow traffic.",
        "commute":    "🟡 Low crime risk — routine travel precautions.",
        "car":        "🟡 Low crime risk — no specific alerts for this area.",
        "train":      "🟡 Low crime risk — normal platform vigilance.",
    },
}

_PHT = timezone(timedelta(hours=8))


# ═════════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def _clean_filename(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9]', '_', name).strip('_')


def _cache_path(area_key: str) -> str:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    return os.path.join(_CACHE_DIR, f"{_CACHE_PREFIX}{_clean_filename(area_key)}.json")


def _load_cache(area_key: str):
    path = _cache_path(area_key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        if time.time() - data.get("_cached_at", 0) < _CACHE_TTL_SEC:
            return data
    except (json.JSONDecodeError, KeyError):
        pass
    return None


def _save_cache(area_key: str, data: dict):
    data["_cached_at"] = time.time()
    try:
        with open(_cache_path(area_key), 'w') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def _group_commuter(commuter_type: str) -> str:
    ct = commuter_type.lower().strip()
    if any(x in ct for x in ["walk", "foot"]):        return "walk"
    if any(x in ct for x in ["bike", "bicycle"]):     return "bike"
    if any(x in ct for x in ["motor", "motorcycle"]): return "motorcycle"
    if any(x in ct for x in ["commute", "jeepney", "bus", "tricycle"]): return "commute"
    if any(x in ct for x in ["lrt", "mrt", "pnr", "train", "rail"]):   return "train"
    return "car"


def _area_from_coords(lat: float, lon: float) -> str:
    """
    Rough label for a Metro Manila coordinate so the cache key and
    search query are meaningful without a live reverse-geocode call.
    """
    # Bounding boxes for major Metro Manila cities (lat_min, lat_max, lon_min, lon_max)
    _CITIES = [
        ("Manila",          14.56, 14.62, 120.96, 121.01),
        ("Quezon City",     14.62, 14.76, 121.00, 121.12),
        ("Caloocan",        14.64, 14.76, 120.95, 121.00),
        ("Marikina",        14.61, 14.68, 121.08, 121.14),
        ("Pasig",           14.55, 14.61, 121.05, 121.10),
        ("Taguig",          14.50, 14.56, 121.03, 121.07),
        ("Makati",          14.54, 14.58, 121.00, 121.05),
        ("Mandaluyong",     14.57, 14.60, 121.02, 121.05),
        ("San Juan",        14.59, 14.62, 121.02, 121.05),
        ("Paranaque",       14.47, 14.52, 120.99, 121.04),
        ("Las Pinas",       14.43, 14.48, 120.97, 121.02),
        ("Pasay",           14.53, 14.57, 120.99, 121.02),
        ("Malabon",         14.65, 14.69, 120.95, 120.98),
        ("Navotas",         14.65, 14.67, 120.94, 120.96),
        ("Valenzuela",      14.68, 14.74, 120.95, 120.99),
        ("Muntinlupa",      14.39, 14.45, 121.01, 121.06),
        ("Pateros",         14.54, 14.56, 121.06, 121.08),
    ]
    for city, lat_min, lat_max, lon_min, lon_max in _CITIES:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return city
    return "Metro Manila"


def _crime_result(risk: str, summary: str, area: str) -> dict:
    labels = {
        "none":     "No recent crime alerts",
        "low":      "Low crime activity reported",
        "moderate": "Moderate crime incidents reported",
        "high":     "High crime risk — recent incidents in area",
    }
    return {
        "ok":         True,
        "risk_level": risk,
        "summary":    summary or labels.get(risk, ""),
        "area":       area,
        "label":      labels.get(risk, ""),
        "color":      _CRIME_COLORS.get(risk, "#7f8c8d"),
        "penalty":    _CRIME_PENALTY.get(risk, 0),
        "fetched_at": datetime.now(_PHT).strftime("%Y-%m-%d %H:%M PHT"),
        "error":      None,
    }


def _crime_error(msg: str, area: str = "") -> dict:
    return {
        "ok":         False,
        "risk_level": "none",
        "summary":    "",
        "area":       area,
        "label":      "Crime data unavailable",
        "color":      _CRIME_COLORS["error"],
        "penalty":    0,
        "fetched_at": "",
        "error":      msg,
    }


# ── Static crime zone fallback (used when Gemini API key is not configured) ───
# Based on PNP public crime statistics and known high-incident areas in Metro Manila.
# ── Static crime zones — loaded from crime_zones.json ────────────────────────
# Edit crime_zones.json directly to update areas without touching this file.

import pathlib as _pathlib

_ZONES_JSON_PATH = _pathlib.Path(__file__).parent.parent / "crime_zones.json"
# Falls back to same directory if not found one level up
if not _ZONES_JSON_PATH.exists():
    _ZONES_JSON_PATH = _pathlib.Path(__file__).parent / "crime_zones.json"


def _load_crime_zones() -> list:
    """Load zones list from crime_zones.json. Returns [] on any error."""
    try:
        with open(_ZONES_JSON_PATH, 'r', encoding='utf-8') as _f:
            data = json.load(_f)
        return data.get("zones", [])
    except Exception:
        return []


def _static_crime_lookup(area: str):
    """
    Returns a crime result by matching area against crime_zones.json.
    Uses whole-word matching and picks the most specific (longest) match.
    Returns None if no match.
    """
    import re as _re
    area_lower  = area.lower().strip()
    zones       = _load_crime_zones()

    best_name    = None
    best_risk    = None
    best_summary = None

    for zone in zones:
        key = zone.get("name", "").lower().strip()
        if not key:
            continue
        # Whole-word/phrase boundary match
        pattern = r'(?<![a-z])' + _re.escape(key) + r'(?![a-z])'
        if _re.search(pattern, area_lower):
            if best_name is None or len(key) > len(best_name):
                best_name    = key
                best_risk    = zone.get("risk", "none")
                best_summary = zone.get("summary", "")

    if best_name:
        return _crime_result(best_risk, best_summary, area)
    return None


# ═════════════════════════════════════════════════════════════════════════════
# MAIN PUBLIC FUNCTIONS
# ═════════════════════════════════════════════════════════════════════════════

def get_crime_risk_for_area(lat: float, lon: float, area_hint: str = "") -> dict:
    """
    Returns a structured crime risk assessment for the given coordinates.

    Uses disk cache (6 hrs). On cache miss, scrapes DuckDuckGo news and
    runs Gemini to classify the risk level.

    Args:
        lat:        latitude of origin
        lon:        longitude of origin
        area_hint:  optional text label (e.g. the origin text the user typed).
                    Falls back to a coordinate-based city label if blank.

    Returns:
        {
          "ok":         bool,
          "risk_level": str,   # "none", "low", "moderate", "high"
          "summary":    str,
          "area":       str,
          "label":      str,
          "color":      str,
          "penalty":    int,
          "fetched_at": str,
          "error":      str or None,
        }
    """
    # Resolve area name
    area_hint_clean = area_hint.strip() if area_hint else ""
    # If hint looks like raw coordinates (no letters), ignore it
    import re as _re
    area = area_hint_clean if area_hint_clean and _re.search(r'[a-zA-Z]', area_hint_clean) else _area_from_coords(lat, lon)
    cache_key = area.lower()

    # 1. Cache hit?
    cached = _load_cache(cache_key)
    if cached:
        return cached

    # 2. Web scrape — fall back to static table if API key missing
    try:
        from llm import search_transport_info, scrape_url, context_model
    except (ImportError, ValueError):
        # Gemini API key not configured — use static crime zone table instead
        static = _static_crime_lookup(area)
        if static:
            _save_cache(cache_key, static)
            return static
        # Area not in static table — return safe default
        return _crime_result("none", "No static crime data for this area.", area)

    query = f"crime snatching holdup robbery {area} Philippines 2025"
    try:
        results = search_transport_info(query)
    except Exception as e:
        return _crime_error(f"Search failed: {e}", area)

    web_data = ""
    for r in results[:4]:
        url = r.get('href', '')
        if url:
            web_data += scrape_url(url) + "\n"

    web_data = web_data[:6000]   # keep token usage sane

    # 3. LLM classification
    sysinstruct = (
        "You are a crime risk analyst for Philippine commuter safety. "
        "Given recent news snippets about a specific area, output ONLY raw JSON with no "
        "markdown, no backticks, no preamble. "
        'Schema: {"risk_level": "none|low|moderate|high", "summary": "one sentence max 20 words", "penalty": 0}. '
        "Penalty mapping: none=0, low=8, moderate=18, high=28. "
        "Use 'none' only if there are zero crime-related news hits. "
        "Use 'low' for isolated older incidents. "
        "Use 'moderate' for recent but not widespread crime. "
        "Use 'high' for multiple recent incidents or active crime advisories."
    )
    context = f"Area: {area}, Philippines\n\nNews snippets:\n{web_data if web_data.strip() else 'No results found.'}"

    try:
        raw = context_model(
            context,
            sysinstruct,
            rthoughts=False,
            thinking_budget=512,
            model="gemini-2.5-flash-lite",
        )
        clean = re.sub(r'```json|```', '', raw).strip()
        parsed = json.loads(clean)

        risk    = parsed.get("risk_level", "none")
        summary = parsed.get("summary", "")

        # Sanity-check the risk_level value
        if risk not in ("none", "low", "moderate", "high"):
            risk = "none"

        result = _crime_result(risk, summary, area)
        _save_cache(cache_key, result)
        return result

    except (json.JSONDecodeError, KeyError) as e:
        # LLM returned garbage — default to none so we don't block routing
        result = _crime_result("none", "", area)
        _save_cache(cache_key, result)
        return result
    except Exception as e:
        return _crime_error(str(e), area)


def get_crime_warning(crime: dict, commuter_type: str) -> str:
    """
    Returns a tailored warning string for the crime risk level + commuter type.
    Returns empty string if no risk.
    """
    if not crime.get("ok"):
        return ""
    risk  = crime.get("risk_level", "none")
    if risk == "none":
        return ""
    group = _group_commuter(commuter_type)
    return _CRIME_WARNINGS.get(risk, {}).get(group, crime.get("label", ""))


def get_crime_warning_html(crime: dict, commuter_type: str = "") -> str:
    """
    Returns an HTML banner for crime risk.
    Returns empty string if risk is none or data unavailable.

    Inject into index.html via Jinja: {{ crime_banner | safe }}
    Place alongside weather/night/typhoon banners.
    """
    if not crime.get("ok") or crime.get("risk_level") == "none":
        return ""

    risk    = crime["risk_level"]
    color   = crime["color"]
    area    = crime.get("area", "")
    summary = crime.get("summary", crime.get("label", ""))
    warning = get_crime_warning(crime, commuter_type) if commuter_type else ""

    icons = {"low": "🟡", "moderate": "🟠", "high": "🚨"}
    icon  = icons.get(risk, "⚠️")

    body = f"{area}: {summary}" if area else summary
    if warning:
        body += f" — {warning}"

    return (
        f'<div class="crime-banner" style="background:{color};color:#fff;'
        f'padding:8px 16px;font-size:13px;font-weight:bold;text-align:center;'
        f'position:fixed;top:0;left:0;right:0;z-index:99996;'
        f'box-shadow:0 2px 6px rgba(0,0,0,0.3);">'
        f'{icon} Crime Alert: {body}'
        f'</div>'
    )


def apply_crime_to_routes(routes: list, crime: dict, commuter_type: str) -> list:
    """
    Applies crime-zone safety penalty to all routes in-place.
    Mirrors the exact same pattern as apply_weather_to_routes() and
    apply_flood_to_routes() — safe to call right after them.

    Args:
        routes:        list of route dicts from navigation.py
        crime:         result dict from get_crime_risk_for_area()
        commuter_type: e.g. 'walk', 'motorcycle', 'commute'

    Returns:
        Same list with updated safety_score, score_color, score_label,
        and a new 'crime_warning' key on each route.
    """
    from risk_monitor.features import get_score_color, get_score_label

    penalty = crime.get("penalty", 0)
    warning = get_crime_warning(crime, commuter_type)

    for r in routes:
        if penalty > 0:
            r["safety_score"] = max(0, r.get("safety_score", 75) - penalty)
            r["score_color"]  = get_score_color(r["safety_score"])
            r["score_label"]  = get_score_label(r["safety_score"])
        r["crime_warning"] = warning if penalty > 0 else ""

    return routes


# ═════════════════════════════════════════════════════════════════════════════
# HOW TO WIRE INTO main.py  (3 lines, no changes to navigation/map code)
# ═════════════════════════════════════════════════════════════════════════════
#
# 1. At the top of main.py, add to existing imports:
#
#       from risk_monitor.crime_data import get_crime_risk_for_area, apply_crime_to_routes
#
# 2. Inside get_routes(), right after the apply_reports_to_routes(...) call
#    (around line 699), add:
#
#       crime = get_crime_risk_for_area(orig_lat, orig_lon, origin_text or "")
#       apply_crime_to_routes(routes, crime, commuter_type)
#
#    That's it. No changes to navigation.py, index.html, or any map code.
#
# 3. (Optional) To show a crime banner on the main page, in home() add:
#
#       crime_banner = get_crime_warning_html(
#           get_crime_risk_for_area(14.5995, 120.9842), ""
#       )
#    and pass   crime_banner=crime_banner   to render_template, then add
#       {{ crime_banner | safe }}
#    in index.html alongside the other banners.