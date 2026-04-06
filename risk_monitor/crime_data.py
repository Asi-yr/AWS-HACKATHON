"""
crime_data.py
-------------
Feature: Real-Time Crime Risk for SafeRoute.

Scrapes recent crime news for a given Philippine area using DuckDuckGo
(already installed via ddgs in llm.py), then uses Gemini to extract a
structured crime risk level. Result is cached to disk for 6 hours so
it does not fire on every single route request.

Key improvements vs. previous version:
  - Coordinate-based zone detection (bounding boxes in crime_zones.json)
    so routes passing THROUGH high-risk areas are flagged even when the
    user's typed text doesn't mention them.
  - Route-path scanning: samples waypoints along the decoded polyline and
    checks each sample against the coordinate zones. Returns the WORST
    zone hit and the list of unique risk zones crossed.
  - Text matching now uses multi-alias matching (e.g. "sta. cruz" ↔
    "santa cruz") and sub-word boundary detection, so short zone names
    like "paco" no longer match "francisco".
  - Anti-spam guard: only zones whose coordinate box actually overlaps
    the route are flagged — prevents flooding the UI with unrelated
    high-risk alerts.
  - City-level names are still supported as fallbacks, but specific
    barangay/street/zone names always win (unchanged from previous logic).

Integration in main.py (no changes needed if already wired):
    from risk_monitor.crime_data import (
        get_crime_risk_for_area, apply_crime_to_routes,
        get_crime_risk_with_reports, scan_route_crime_zones,
        apply_route_crime_to_routes,
    )

    Inside get_routes(), after apply_reports_to_routes(...):
        crime = get_crime_risk_with_reports(orig_lat, orig_lon, origin_text or "", chDB_perf)
        dest_crime = get_crime_risk_with_reports(dest_lat, dest_lon, dest_text or "", chDB_perf)

        # NEW: scan the actual path for crime zones
        for route in routes:
            waypoints = route.get("waypoints") or route.get("geometry_coords") or []
            route_zones = scan_route_crime_zones(waypoints)
            route["route_crime_zones"] = route_zones

        apply_crime_both_ends(routes, crime, dest_crime, commuter_type)
        apply_route_crime_to_routes(routes, commuter_type)   # uses route_crime_zones

No new pip packages needed — uses ddgs, requests, BeautifulSoup, and
google-genai, all of which are already in requirements.txt via llm.py.
"""

import os
import sys
import json
import re
import time
import functools
from datetime import datetime, timezone, timedelta

# ═════════════════════════════════════════════════════════════════════════════
# DEBUGGING CONFIGURATION
# ═════════════════════════════════════════════════════════════════════════════

# Set to True to enable verbose logging to stderr by default.
DEBUG_MODE = True

def _debug_log(msg, *args):
    """
    Logs debug messages to stderr if DEBUG_MODE is on.
    Usage: _debug_log("Function X called with %s", arg1)
    """
    if DEBUG_MODE:
        try:
            formatted_msg = msg % args if args else msg
            print(f"[risk_monitor.crime_data] {formatted_msg}", file=sys.stderr)
        except Exception:
            print(f"[risk_monitor.crime_data] {msg} {args}", file=sys.stderr)

def timeit(func):
    """
    Decorator to measure and log function execution time.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not DEBUG_MODE:
            return func(*args, **kwargs)
        
        func_name = func.__name__
        # Attempt to log simple args (lat, lon) if present
        arg_summary = ""
        if args:
            # Filter for simple types to avoid dumping huge objects
            simple_args = [a for a in args if isinstance(a, (int, float, str))]
            if simple_args:
                arg_summary = str(simple_args[:3]) # First 3 args
        
        start_t = time.perf_counter()
        _debug_log(f">>> ENTER {func_name} | Args: {arg_summary}")
        
        try:
            result = func(*args, **kwargs)
            end_t = time.perf_counter()
            duration = (end_t - start_t) * 1000
            
            # Log result summary (size or type)
            res_summary = type(result).__name__
            if isinstance(result, list):
                res_summary = f"list({len(result)})"
            elif isinstance(result, dict):
                res_summary = f"dict({len(result)} keys)"
            
            _debug_log(f"<<< EXIT  {func_name} | Time: {duration:.2f}ms | Result: {res_summary}")
            return result
        except Exception as e:
            end_t = time.perf_counter()
            duration = (end_t - start_t) * 1000
            _debug_log(f"!!! ERROR {func_name} | Time: {duration:.2f}ms | Error: {e}")
            raise e
    return wrapper

# ═════════════════════════════════════════════════════════════════════════════
# CACHE CONFIG
# ═════════════════════════════════════════════════════════════════════════════

_CACHE_DIR      = "transit_data"
_CACHE_PREFIX   = "crime_"
_CACHE_TTL_SEC  = 6 * 3600

# ═─ Risk config ───────────────────────────────────────────────────────────────
_CRIME_COLORS = {
    "none":     "#27ae60",
    "low":      "#f39c12",
    "moderate": "#e67e22",
    "high":     "#e74c3c",
    "error":    "#7f8c8d",
}

_CRIME_PENALTY = {
    "none":     0,
    "low":      2,    # endpoint in low-crime area: −2 pts (was 3)
    "moderate": 5,    # endpoint in moderate area: −5 pts (was 6)
    "high":     8,    # endpoint in high-crime area: −8 pts (was 10)
}

# Mode multiplier for crime penalties: car is most protected, walk is most exposed.
# Applied to both endpoint and zone penalties so scores differ meaningfully by mode.
_CRIME_MODE_MULTIPLIER = {
    "walk":       1.20,   # fully exposed on foot
    "bike":       1.10,
    "motorcycle": 1.05,
    "commute":    1.00,   # baseline (inside vehicle, some exposure at stops)
    "transit":    1.00,
    "car":        0.70,   # enclosed, much lower personal crime risk
    "automobile": 0.70,
}

_CRIME_WARNINGS = {
    "high": {
        "walk":       "🚨 High crime risk along this route — avoid walking alone, stay on busy lit streets.",
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

# Community-report bump config
_REPORT_BUMP_RADIUS  = 0.005   # ~550 m in decimal degrees
_REPORT_CRIME_TYPES  = {"crime", "harassment"}

# City-level zone names — specific district/barangay matches always beat these
_CITY_LEVEL_ZONES = {
    "manila", "quezon city", "caloocan", "makati", "pasay", "taguig",
    "mandaluyong", "marikina", "pasig", "paranaque", "las pinas",
    "muntinlupa", "san juan", "navotas", "malabon", "valenzuela",
    "pateros", "metro manila", "rizal", "bulacan", "cavite", "laguna",
}

# Risk level ordering for comparisons
_RISK_ORDER = {"none": 0, "low": 1, "moderate": 2, "high": 3}


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
        # _debug_log(f"Cache miss: {area_key} (no file)") # Optional: too noisy?
        return None
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        if time.time() - data.get("_cached_at", 0) < _CACHE_TTL_SEC:
            _debug_log(f"Cache HIT for key '{area_key}'")
            return data
        else:
            _debug_log(f"Cache STALE for key '{area_key}'")
    except (json.JSONDecodeError, KeyError):
        pass
    return None


def _save_cache(area_key: str, data: dict):
    data["_cached_at"] = time.time()
    try:
        with open(_cache_path(area_key), 'w') as f:
            json.dump(data, f, indent=2)
        _debug_log(f"Saved to cache: '{area_key}'")
    except Exception as e:
        _debug_log(f"Failed to save cache for '{area_key}': {e}")


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
    Rough label for a Metro Manila coordinate without a live reverse-geocode call.
    Returns the most specific matching zone name (prefers barangay over city).
    """
    # First try coordinate zones from JSON (most specific)
    coord_zone = _coord_zone_lookup(lat, lon)
    if coord_zone and coord_zone.get("name"):
        return coord_zone["name"]

    # Fall back to broad city bounding boxes
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


# ── Zone JSON loader ──────────────────────────────────────────────────────────
import pathlib as _pathlib

_ZONES_JSON_PATH = _pathlib.Path(__file__).parent.parent / "crime_zones.json"
if not _ZONES_JSON_PATH.exists():
    _ZONES_JSON_PATH = _pathlib.Path(__file__).parent / "crime_zones.json"

_ZONES_CACHE: list = []
_ZONES_LOAD_TIME: float = 0.0
_ZONES_TTL: float = 300.0   # reload JSON every 5 min in case of edits


def _load_crime_zones() -> list:
    """Load zones list from crime_zones.json, with a short in-memory cache."""
    global _ZONES_CACHE, _ZONES_LOAD_TIME
    now = time.time()
    if _ZONES_CACHE and (now - _ZONES_LOAD_TIME) < _ZONES_TTL:
        return _ZONES_CACHE
    try:
        _debug_log(f"Reloading crime zones from disk: {_ZONES_JSON_PATH}")
        with open(_ZONES_JSON_PATH, 'r', encoding='utf-8') as _f:
            data = json.load(_f)
        _ZONES_CACHE = data.get("zones", [])
        _ZONES_LOAD_TIME = now
        _debug_log(f"Loaded {len(_ZONES_CACHE)} crime zones.")
        return _ZONES_CACHE
    except Exception as e:
        _debug_log(f"Failed to load crime zones: {e}")
        return _ZONES_CACHE or []


# ── City boundary definitions (authoritative bounding boxes) ──────────────────
#
# These are the canonical city boundaries used to prevent zone bleed-over.
# A zone whose name contains a city keyword is ONLY valid inside that city's box.
# This stops e.g. "bagong silang caloocan" from matching a coordinate in Valenzuela.
#
# Format: city_keyword → (lat_min, lat_max, lon_min, lon_max)
_CITY_BOUNDS = {
    "manila":        (14.556, 14.632, 120.956, 121.015),
    "quezon city":   (14.615, 14.768, 120.990, 121.125),
    "caloocan":      (14.630, 14.773, 120.942, 121.010),
    "valenzuela":    (14.676, 14.758, 120.942, 120.999),
    "malabon":       (14.644, 14.695, 120.942, 120.982),
    "navotas":       (14.638, 14.682, 120.930, 120.959),
    "marikina":      (14.605, 14.688, 121.076, 121.145),
    "pasig":         (14.544, 14.614, 121.042, 121.106),
    "taguig":        (14.484, 14.565, 121.020, 121.085),
    "makati":        (14.535, 14.585, 120.993, 121.053),
    "mandaluyong":   (14.566, 14.608, 121.016, 121.055),
    "san juan":      (14.585, 14.622, 121.016, 121.050),
    "paranaque":     (14.463, 14.527, 120.983, 121.048),
    "las pinas":     (14.425, 14.488, 120.963, 121.027),
    "muntinlupa":    (14.385, 14.455, 121.009, 121.068),
    "pasay":         (14.527, 14.573, 120.985, 121.022),
    "pateros":       (14.538, 14.562, 121.058, 121.085),
}

# Keywords in zone names that indicate city membership — checked in order (longest first)
_CITY_KEYWORDS = sorted(_CITY_BOUNDS.keys(), key=len, reverse=True)


def _get_city_for_coords(lat: float, lon: float) -> str | None:
    """Return the canonical city name for (lat, lon), or None if not matched."""
    # Use smallest matching box (most specific city)
    best_city  = None
    best_area  = float("inf")
    for city, (lat_min, lat_max, lon_min, lon_max) in _CITY_BOUNDS.items():
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            area = (lat_max - lat_min) * (lon_max - lon_min)
            if area < best_area:
                best_city = city
                best_area = area
    return best_city


def _zone_city_keyword(zone_name: str) -> str | None:
    """
    Returns the city keyword embedded in a zone name, or None.
    E.g. "bagong silang caloocan" → "caloocan"
         "grace park west"        → None  (no city suffix; zone itself is in caloocan
                                          but name doesn't say so — skip city gate)
    """
    name_lower = zone_name.lower()
    for keyword in _CITY_KEYWORDS:
        # Whole-word boundary match so "manila" doesn't match "mandaluyong"
        if re.search(r'(?<![a-z])' + re.escape(keyword) + r'(?![a-z])', name_lower):
            return keyword
    return None


# ── Coordinate-based zone lookup ──────────────────────────────────────────────

def _coord_zone_lookup(lat: float, lon: float) -> dict | None:
    """
    Returns the most specific crime zone whose bounding box contains (lat, lon).
    Zones with coords defined always beat zones without.
    Among multiple hits, the one with the smallest area (most specific) wins.
    """
    zones    = _load_crime_zones()
    coord_city = _get_city_for_coords(lat, lon)   # which city is this point in?
    
    _debug_log(f"Coord lookup for ({lat:.4f}, {lon:.4f}) -> City: {coord_city or 'Unknown'}")

    best      = None
    best_area = float("inf")

    for zone in zones:
        coords = zone.get("coords")
        if not coords or len(coords) != 4:
            continue
        lat_min, lat_max, lon_min, lon_max = coords
        if not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
            continue

        # ── City-awareness gate ──────────────────────────────────────────────
        zone_city = _zone_city_keyword(zone.get("name", ""))
        if zone_city and coord_city and zone_city != coord_city:
            # The zone belongs to a different city than the coordinate — skip it.
            # _debug_log(f"  Skipping zone '{zone.get('name')}' (City gate mismatch: Zone in {zone_city}, Point in {coord_city})")
            continue
        
        box_area = (lat_max - lat_min) * (lon_max - lon_min)
        if box_area < best_area:
            _debug_log(f"  Found candidate zone: '{zone.get('name')}' (Risk: {zone.get('risk')}, Area: {box_area:.6f})")
            best      = zone
            best_area = box_area

    return best


# ── Text-based zone lookup ────────────────────────────────────────────────────

def _static_crime_lookup(area: str) -> dict | None:
    """
    Returns a crime result by matching area against crime_zones.json zone names.
    """
    area_lower = area.lower().strip()
    zones      = _load_crime_zones()
    
    _debug_log(f"Static text lookup for: '{area}'")

    specific_best = None   # (key, risk, summary, match_len)
    city_best     = None

    for zone in zones:
        # Build all candidate names to match against
        names_to_try = [zone.get("name", "").lower().strip()]
        for alias in zone.get("aliases", []):
            names_to_try.append(alias.lower().strip())

        matched_key = None
        match_len   = 0
        for candidate in names_to_try:
            if not candidate:
                continue
            pattern = r'(?<![a-z0-9])' + re.escape(candidate) + r'(?![a-z0-9])'
            if re.search(pattern, area_lower):
                if len(candidate) > match_len:
                    matched_key = candidate
                    match_len   = len(candidate)

        if not matched_key:
            continue

        risk    = zone.get("risk", "none")
        summary = zone.get("summary", "")
        entry   = (matched_key, risk, summary, match_len)

        primary_name = zone.get("name", "").lower().strip()
        if primary_name in _CITY_LEVEL_ZONES:
            if city_best is None or match_len > city_best[3]:
                city_best = entry
        else:
            if specific_best is None or match_len > specific_best[3]:
                specific_best = entry

    winner = specific_best or city_best
    if winner:
        _debug_log(f"  Text match found: Zone '{winner[0]}' (Risk: {winner[1]})")
        return _crime_result(winner[1], winner[2], area)
    
    _debug_log(f"  No static text match found.")
    return None


# ═════════════════════════════════════════════════════════════════════════════
# ROUTE PATH SCANNING  (the main new feature)
# ═════════════════════════════════════════════════════════════════════════════

def _decode_polyline(encoded: str) -> list[tuple[float, float]]:
    """Google Encoded Polyline decoder → list of (lat, lon) tuples."""
    coords = []
    index = 0
    lat = lon = 0
    while index < len(encoded):
        for is_lon in (False, True):
            result = shift = 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if is_lon:
                lon += delta
            else:
                lat += delta
        coords.append((lat / 1e5, lon / 1e5))
    return coords


def _sample_waypoints(waypoints: list, max_samples: int = 60) -> list[tuple[float, float]]:
    """
    Normalise route geometry to a list of (lat, lon) tuples, then thin it to
    at most max_samples evenly spaced points.
    """
    if not waypoints:
        return []

    # Decode encoded polyline string
    if isinstance(waypoints, str):
        points = _decode_polyline(waypoints)
    else:
        points = []
        for wp in waypoints:
            if isinstance(wp, (list, tuple)) and len(wp) >= 2:
                points.append((float(wp[0]), float(wp[1])))
            elif isinstance(wp, dict):
                lat = wp.get("lat") or wp.get("latitude") or wp.get("y")
                lon = wp.get("lon") or wp.get("lng") or wp.get("longitude") or wp.get("x")
                if lat is not None and lon is not None:
                    points.append((float(lat), float(lon)))

    if len(points) <= max_samples:
        return points

    step = len(points) / max_samples
    return [points[int(i * step)] for i in range(max_samples)]


def _is_contained_within(inner_coords: list, outer_coords: list) -> bool:
    """
    Returns True if inner_coords bounding box is fully contained within
    outer_coords bounding box.
    """
    i_lat_min, i_lat_max, i_lon_min, i_lon_max = inner_coords
    o_lat_min, o_lat_max, o_lon_min, o_lon_max = outer_coords
    return (
        i_lat_min >= o_lat_min and i_lat_max <= o_lat_max and
        i_lon_min >= o_lon_min and i_lon_max <= o_lon_max
    )


def _deduplicate_zones(zones: list) -> list:
    """
    Remove zones whose bounding box is fully contained within another zone
    in the list that has equal or higher risk.
    """
    if len(zones) <= 1:
        return zones

    keep = []
    for candidate in zones:
        c_coords = candidate.get("coords")
        c_risk   = _RISK_ORDER.get(candidate.get("risk", "none"), 0)

        if not c_coords:
            keep.append(candidate)
            continue

        absorbed = False
        for other in zones:
            if other is candidate:
                continue
            o_coords = other.get("coords")
            o_risk   = _RISK_ORDER.get(other.get("risk", "none"), 0)
            if not o_coords:
                continue
            # Drop candidate if it lives inside `other` at same/higher risk
            if o_risk >= c_risk and _is_contained_within(c_coords, o_coords):
                absorbed = True
                break

        if not absorbed:
            keep.append(candidate)

    return keep


@timeit
def scan_route_crime_zones(waypoints) -> list:
    """
    Scans waypoints along a route and returns a deduplicated list of crime zone
    dicts for every distinct zone the route passes through.
    """
    if not waypoints:
        _debug_log("Scan route: No waypoints provided.")
        return []

    samples = _sample_waypoints(waypoints, max_samples=80)
    if not samples:
        return []
    
    _debug_log(f"Scan route: Processing {len(samples)} sample points.")

    zones       = _load_crime_zones()
    coord_zones = [z for z in zones if z.get("coords") and len(z["coords"]) == 4]

    seen_names = set()
    found      = []

    for lat, lon in samples:
        best       = None
        best_area  = float("inf")
        coord_city = _get_city_for_coords(lat, lon)

        for zone in coord_zones:
            lat_min, lat_max, lon_min, lon_max = zone["coords"]
            if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
                # City-awareness gate
                zone_city = _zone_city_keyword(zone.get("name", ""))
                if zone_city and coord_city and zone_city != coord_city:
                    continue

                box_area = (lat_max - lat_min) * (lon_max - lon_min)
                if box_area < best_area:
                    best      = zone
                    best_area = box_area

        if best is None:
            continue

        risk = best.get("risk", "none")
        if risk == "none":
            continue

        name = best.get("name", "")
        if name in seen_names:
            continue

        seen_names.add(name)
        found.append({
            "name":    name,
            "risk":    risk,
            "summary": best.get("summary", ""),
            "color":   _CRIME_COLORS.get(risk, "#7f8c8d"),
            "coords":  best["coords"],
            "hit_lat": lat,
            "hit_lon": lon,
        })

    # Sort worst first
    found.sort(key=lambda z: -_RISK_ORDER.get(z["risk"], 0))

    # Parent/child deduplication
    original_count = len(found)
    found = _deduplicate_zones(found)
    
    if original_count != len(found):
        _debug_log(f"Scan route: Deduplication removed {original_count - len(found)} sub-zones.")

    return found


def get_worst_route_risk(route_zones: list[dict]) -> str:
    """Returns the worst risk level string from a list of scanned zones."""
    worst = 0
    for z in route_zones:
        worst = max(worst, _RISK_ORDER.get(z.get("risk", "none"), 0))
    levels = {v: k for k, v in _RISK_ORDER.items()}
    return levels.get(worst, "none")


def annotate_segments_with_crime(route: dict) -> None:
    """
    For each segment in route['segments'], check whether its coords overlap
    any crime zone bounding box and attach 'crime_risk' + 'crime_note'.

    Mutates the segment dicts in-place. Safe to call when segments is missing
    or empty. Called once per route, right after scan_route_crime_zones().

    Each segment gets:
        crime_risk: str  — 'high' | 'moderate' | 'low' | 'none'
        crime_note: str  — short summary from crime_zones.json, or ''
    """
    segments = route.get("segments", [])
    if not segments:
        return

    zones = _load_crime_zones()
    coord_zones = [z for z in zones if z.get("coords") and len(z["coords"]) == 4]

    for seg in segments:
        raw = seg.get("coords", [])

        # Flatten nested train-style coords: [[[lat,lon],...], ...]
        flat: list[tuple[float, float]] = []
        if raw and isinstance(raw[0], list) and raw[0] and isinstance(raw[0][0], list):
            for sub in raw:
                flat.extend((p[0], p[1]) for p in sub if len(p) >= 2)
        else:
            flat = [(p[0], p[1]) for p in raw if len(p) >= 2]

        if not flat:
            seg["crime_risk"] = "none"
            seg["crime_note"] = ""
            continue

        # Segments are short — 20 samples is plenty
        samples = _sample_waypoints(flat, max_samples=20)

        worst_risk = "none"
        worst_zone = None
        worst_area = float("inf")

        # Cache city lookups so we don't repeat for every zone per point
        coord_city_cache: dict[tuple, str | None] = {}

        for lat, lon in samples:
            cc_key = (round(lat, 3), round(lon, 3))
            if cc_key not in coord_city_cache:
                coord_city_cache[cc_key] = _get_city_for_coords(lat, lon)
            coord_city = coord_city_cache[cc_key]

            for zone in coord_zones:
                lat_min, lat_max, lon_min, lon_max = zone["coords"]
                if not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
                    continue

                # City-awareness gate — same logic as scan_route_crime_zones
                zone_city = _zone_city_keyword(zone.get("name", ""))
                if zone_city and coord_city and zone_city != coord_city:
                    continue

                z_risk = zone.get("risk", "none")
                box_area = (lat_max - lat_min) * (lon_max - lon_min)

                # Keep worst risk; break ties by smaller (more specific) zone
                if (_RISK_ORDER.get(z_risk, 0) > _RISK_ORDER.get(worst_risk, 0)
                        or (_RISK_ORDER.get(z_risk, 0) == _RISK_ORDER.get(worst_risk, 0)
                            and box_area < worst_area)):
                    worst_risk = z_risk
                    worst_zone = zone
                    worst_area = box_area

        seg["crime_risk"] = worst_risk
        seg["crime_note"] = worst_zone.get("summary", "") if worst_zone else ""


# ═════════════════════════════════════════════════════════════════════════════
# MAIN PUBLIC FUNCTIONS
# ═════════════════════════════════════════════════════════════════════════════

@timeit
def get_crime_risk_for_area(lat: float, lon: float, area_hint: str = "") -> dict:
    """
    Returns a structured crime risk assessment for the given coordinates.
    Priority order:
      1. Coordinate zone lookup (bounding boxes in crime_zones.json)
      2. Text match against area_hint in crime_zones.json
      3. Disk cache (for previously LLM-resolved areas)
      4. LLM web scrape + Gemini classification
    """
    area_hint_clean = (area_hint or "").strip()

    # 1. Coordinate lookup
    coord_result = _coord_zone_lookup(lat, lon)
    if coord_result:
        zone_name = coord_result.get("name", "")
        area_label = area_hint_clean or zone_name
        _debug_log(f"Decision: Using COORD match for '{zone_name}'")
        return _crime_result(
            coord_result.get("risk", "none"),
            coord_result.get("summary", ""),
            area_label,
        )

    # 2. Text match
    area = area_hint_clean if area_hint_clean and re.search(r'[a-zA-Z]', area_hint_clean) else _area_from_coords(lat, lon)
    
    _debug_log(f"Decision: No coord match. Trying text match for area '{area}'")
    static = _static_crime_lookup(area)
    if static:
        return static

    # 3. Disk cache
    cache_key = area.lower()
    cached = _load_cache(cache_key)
    if cached:
        _debug_log(f"Decision: Using CACHED result for '{cache_key}'")
        return cached

    # 4. LLM fallback
    _debug_log(f"Decision: Falling back to LLM for '{area}'")
    try:
        from llm import search_transport_info, scrape_url, context_model
    except (ImportError, ValueError) as e:
        _debug_log(f"CRITICAL: llm module import failed: {e}")
        return _crime_result("none", "No crime data available for this area.", area)

    query = f"crime snatching holdup robbery {area} Philippines 2025"
    _debug_log(f"LLM Query: {query}")
    
    try:
        results = search_transport_info(query)
    except Exception as e:
        _debug_log(f"Search failed: {e}")
        return _crime_error(f"Search failed: {e}", area)

    web_data = ""
    for r in results[:4]:
        url = r.get('href', '')
        if url:
            web_data += scrape_url(url) + "\n"

    web_data = web_data[:6000]

    sysinstruct = (
        "You are a crime risk analyst for Philippine commuter safety. "
        "Given recent news snippets about a specific area, output ONLY raw JSON with no "
        "markdown, no backticks, no preamble. "
        'Schema: {"risk_level": "none|low|moderate|high", "summary": "one sentence max 20 words"}. '
        "Use 'none' only if there are zero crime-related news hits. "
        "Use 'low' for isolated older incidents. "
        "Use 'moderate' for recent but not widespread crime. "
        "Use 'high' for multiple recent incidents or active crime advisories."
    )
    context = f"Area: {area}, Philippines\n\nNews snippets:\n{web_data if web_data.strip() else 'No results found.'}"

    try:
        raw = context_model(
            context, sysinstruct,
            rthoughts=False, thinking_budget=512,
            model="gemini-2.5-flash-lite",
        )
        clean  = re.sub(r'```json|```', '', raw).strip()
        parsed = json.loads(clean)
        risk   = parsed.get("risk_level", "none")
        if risk not in ("none", "low", "moderate", "high"):
            risk = "none"
        summary = parsed.get("summary", "")
        result  = _crime_result(risk, summary, area)
        _debug_log(f"LLM Result: Risk={risk}, Summary='{summary}'")
        _save_cache(cache_key, result)
        return result

    except (json.JSONDecodeError, KeyError) as e:
        _debug_log(f"LLM Response parsing failed: {e}")
        result = _crime_result("none", "", area)
        _save_cache(cache_key, result)
        return result
    except Exception as e:
        _debug_log(f"LLM call failed: {e}")
        return _crime_error(str(e), area)


def get_crime_warning(crime: dict, commuter_type: str) -> str:
    """Returns a tailored warning string for the crime risk level + commuter type."""
    if not crime.get("ok"):
        return ""
    risk = crime.get("risk_level", "none")
    if risk == "none":
        return ""
    group = _group_commuter(commuter_type)
    return _CRIME_WARNINGS.get(risk, {}).get(group, crime.get("label", ""))


def get_crime_warning_html(crime: dict, commuter_type: str = "") -> str:
    """
    Returns an HTML banner for crime risk.
    Returns empty string if risk is none or data unavailable.
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


@timeit
def apply_crime_to_routes(routes: list, crime: dict, commuter_type: str) -> list:
    """
    Applies a single crime-zone flat safety penalty to all routes in-place.
    """
    from risk_monitor.features import get_score_color, get_score_label, apply_penalty_to_route

    penalty = float(crime.get("penalty", 0))
    warning = get_crime_warning(crime, commuter_type)
    
    _debug_log(f"Applying single crime penalty {penalty} to {len(routes)} routes.")

    for r in routes:
        if penalty > 0:
            apply_penalty_to_route(r, penalty, commuter_type)
            r["score_color"] = get_score_color(r["safety_score"])
            r["score_label"] = get_score_label(r["safety_score"])
        r["crime_warning"] = warning if penalty > 0 else ""

    return routes


@timeit
def apply_crime_both_ends(
    routes: list,
    orig_crime: dict,
    dest_crime: dict,
    commuter_type: str,
) -> list:
    """
    Applies crime penalty using the WORSE of origin or destination risk,
    and builds a combined warning.
    """
    from risk_monitor.features import get_score_color, get_score_label, apply_penalty_to_route

    orig_level = _RISK_ORDER.get(orig_crime.get("risk_level", "none"), 0)
    dest_level = _RISK_ORDER.get(dest_crime.get("risk_level", "none"), 0)

    primary      = dest_crime if dest_level >= orig_level else orig_crime
    base_penalty = primary.get("penalty", 0)

    # Apply mode multiplier: car users are far less personally exposed than walkers
    _ct_key = commuter_type.lower().strip()
    _mode_mult = _CRIME_MODE_MULTIPLIER.get(_ct_key, 1.0)
    # Resolve transit aliases
    if _ct_key in ('transit', 'jeepney', 'bus', 'train', 'commute', 'puj'):
        _mode_mult = _CRIME_MODE_MULTIPLIER.get('transit', 1.0)
    base_penalty = round(base_penalty * _mode_mult, 1)
    
    _debug_log(f"Applying two-end penalty. Orig: {orig_crime.get('risk_level')}, Dest: {dest_crime.get('risk_level')}. Selected: {primary.get('risk_level')} ({base_penalty} pts)")

    orig_warn = get_crime_warning(orig_crime, commuter_type) if orig_level > 0 else ""
    dest_warn = get_crime_warning(dest_crime, commuter_type) if dest_level > 0 else ""

    orig_area = orig_crime.get("area", "")
    dest_area = dest_crime.get("area", "")

    if orig_area and dest_area and orig_area != dest_area and orig_level > 0 and dest_level > 0:
        if dest_level >= orig_level:
            warning = f"⚠️ {dest_area}: {dest_warn}"
            if orig_level > 0:
                warning += f" | Also: {orig_area} ({orig_crime.get('risk_level','').title()} risk)"
        else:
            warning = f"⚠️ {orig_area}: {orig_warn}"
            warning += f" | Also: {dest_area} ({dest_crime.get('risk_level','').title()} risk)"
    elif dest_level > 0 and dest_area:
        warning = dest_warn
    elif orig_level > 0 and orig_area:
        warning = orig_warn
    else:
        warning = ""

    worst_endpoint_risk = primary.get("risk_level", "none")

    for r in routes:
        if base_penalty > 0:
            apply_penalty_to_route(r, float(base_penalty), commuter_type)
            r["score_color"] = get_score_color(r["safety_score"])
            r["score_label"] = get_score_label(r["safety_score"])
        r["crime_warning"]          = warning if base_penalty > 0 else ""
        r["orig_crime"]             = orig_crime
        r["dest_crime"]             = dest_crime
        r["_endpoint_crime_risk"]   = worst_endpoint_risk

    return routes


@timeit
def apply_route_crime_to_routes(routes: list, commuter_type: str) -> list:
    """
    Reads pre-computed route["route_crime_zones"] and applies INCREMENTAL penalties.
    """
    from risk_monitor.features import get_score_color, get_score_label, apply_penalty_to_route

    group = _group_commuter(commuter_type)

    all_zones    = _load_crime_zones()
    coord_zones  = {z["name"]: z["coords"] for z in all_zones if z.get("coords") and len(z["coords"]) == 4}

    for r in routes:
        route_zones = r.get("route_crime_zones", [])
        if not route_zones:
            r.setdefault("route_zones_warning", "")
            continue

        endpoint_risk = r.get("_endpoint_crime_risk", "none")
        endpoint_ord  = _RISK_ORDER.get(endpoint_risk, 0)

        # ... [Logic for deduplication] ...
        orig_zone_name      = (r.get("orig_crime") or {}).get("area", "").lower()
        dest_zone_name      = (r.get("dest_crime") or {}).get("area", "").lower()
        endpoint_zone_names = {orig_zone_name, dest_zone_name} - {""}

        def _is_covered_by_endpoint(z_name, z_coords, z_ord):
            if not z_coords: return False
            for ep_name in endpoint_zone_names:
                ep_coords = coord_zones.get(ep_name)
                if ep_coords and endpoint_ord >= z_ord:
                    if _is_contained_within(z_coords, ep_coords):
                        return True
            return False

        deduped_route_zones = []
        for candidate in route_zones:
            c_name   = candidate["name"].lower()
            c_coords = candidate.get("coords")
            c_risk   = candidate.get("risk", "none")
            c_ord    = _RISK_ORDER.get(c_risk, 0)

            if c_ord == 0: continue
            if c_name in endpoint_zone_names: continue
            if _is_covered_by_endpoint(c_name, c_coords, c_ord): continue

            absorbed = False
            if c_coords:
                for other in route_zones:
                    if other is candidate: continue
                    o_coords = other.get("coords")
                    o_ord    = _RISK_ORDER.get(other.get("risk", "none"), 0)
                    if o_coords and o_ord >= c_ord and _is_contained_within(c_coords, o_coords):
                        absorbed = True
                        break
            if absorbed: continue

            deduped_route_zones.append(candidate)

        extra_penalty_total = 0.0
        notable             = []
        applied_zone_names  = set()

        # Reduced per-zone penalties — zones are geographic facts, not active threats.
        # A route passing through 6 zones shouldn't tank the score by 12+ pts.
        # Cap ensures crime zones don't dominate over actual trip characteristics.
        _PER_ZONE_PENALTY = {"high": 1.5, "moderate": 0.7, "low": 0.2}
        _MAX_ZONE_PENALTY = 8.0   # Cap: no matter how many zones, max −8 from path crime

        # Mode multiplier — car users face less personal crime risk than pedestrians
        _ct_key_z = commuter_type.lower().strip()
        _zone_mode_mult = _CRIME_MODE_MULTIPLIER.get(_ct_key_z, 1.0)
        if _ct_key_z in ('transit', 'jeepney', 'bus', 'train', 'commute', 'puj'):
            _zone_mode_mult = _CRIME_MODE_MULTIPLIER.get('transit', 1.0)

        for zone in deduped_route_zones:
            z_name = zone["name"].lower()
            z_risk = zone.get("risk", "none")
            z_ord  = _RISK_ORDER.get(z_risk, 0)

            if z_ord > endpoint_ord:
                diff        = _CRIME_PENALTY.get(z_risk, 0) - _CRIME_PENALTY.get(endpoint_risk, 0)
                incremental = diff + _PER_ZONE_PENALTY.get(z_risk, 1.0)
            else:
                incremental = _PER_ZONE_PENALTY.get(z_risk, 0.5)

            if incremental > 0 and z_name not in applied_zone_names:
                extra_penalty_total += incremental * _zone_mode_mult
                applied_zone_names.add(z_name)
                if z_risk in ("high", "moderate"):
                    notable.append(zone)

        # Cap total zone penalty so it doesn't dominate the score
        extra_penalty_total = min(extra_penalty_total, _MAX_ZONE_PENALTY)

        if extra_penalty_total > 0:
            _debug_log(f"Route '{r.get('name', 'unknown')}': Applying {extra_penalty_total:.1f} extra penalty for {len(notable)} zones.")
            apply_penalty_to_route(r, extra_penalty_total, commuter_type)
            r["score_color"] = get_score_color(r["safety_score"])
            r["score_label"] = get_score_label(r["safety_score"])

        if notable:
            worst_risk = notable[0]["risk"]
            zone_names = ", ".join(z["name"].title() for z in notable[:4])
            base_warn  = _CRIME_WARNINGS.get(worst_risk, {}).get(group, "")
            r["route_zones_warning"] = (
                f"{'🚨' if worst_risk == 'high' else '⚠️'} Route passes through "
                f"{worst_risk.title()}-risk area(s): {zone_names}. {base_warn}"
            )
        else:
            r["route_zones_warning"] = ""

    return routes


# ═════════════════════════════════════════════════════════════════════════════
# COMMUNITY REPORT INTEGRATION
# ═════════════════════════════════════════════════════════════════════════════

@timeit
def get_crime_risk_with_reports(
    lat: float,
    lon: float,
    area_hint: str,
    db,
) -> dict:
    """
    Full crime risk assessment combining static/LLM data and community reports.
    """
    base = get_crime_risk_for_area(lat, lon, area_hint)

    try:
        from risk_monitor.community_reports import get_reports_near
        nearby = get_reports_near(db, lat, lon, radius_deg=_REPORT_BUMP_RADIUS)
        _debug_log(f"Found {len(nearby)} community reports near ({lat}, {lon})")
    except Exception as e:
        _debug_log(f"Community reports check failed: {e}")
        nearby = []

    crime_reports = [r for r in nearby if r.get("report_type") in _REPORT_CRIME_TYPES]

    if not crime_reports:
        base["community_bump"] = 0
        base["community_note"] = ""
        return base

    verified   = [r for r in crime_reports if r.get("confirmations", 0) >= 2]
    unverified = [r for r in crime_reports if r.get("confirmations", 0) < 2]

    bump = 0
    if len(verified) >= 2:
        bump = 2
    elif verified or len(unverified) >= 2:
        bump = 1

    if bump == 0:
        base["community_bump"] = 0
        base["community_note"] = ""
        return base

    _LEVELS      = ["none", "low", "moderate", "high"]
    current_idx  = _LEVELS.index(base.get("risk_level", "none"))
    new_idx      = min(len(_LEVELS) - 1, current_idx + bump)
    new_risk     = _LEVELS[new_idx]

    if new_risk == base.get("risk_level"):
        base["community_bump"] = 0
        base["community_note"] = ""
        return base

    type_labels = list({r.get("report_type", "incident") for r in crime_reports})
    label_map   = {"crime": "crime/snatching", "harassment": "harassment"}
    type_str    = " and ".join(label_map.get(t, t) for t in type_labels)
    count       = len(crime_reports)
    note        = (
        f"{count} recent community report{'s' if count > 1 else ''} "
        f"of {type_str} within 550m."
    )
    
    _debug_log(f"Community bump applied: {base.get('risk_level')} -> {new_risk} ({note})")

    bumped = _crime_result(new_risk, base.get("summary", ""), base.get("area", ""))
    bumped["community_bump"] = bump
    bumped["community_note"] = note
    return bumped