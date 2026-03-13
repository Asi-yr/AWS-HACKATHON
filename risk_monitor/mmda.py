"""
mmda.py
-------
MMDA (Metro Manila Development Authority) real-time data for SafeRoute.

Data sources (all public, no API key):
  1. MMDA Traffic Navigator RSS / JSON feed
     https://trafficnavigator.mmda.gov.ph/
  2. Number coding schedule (static, embedded — changes only by MMDA order)
  3. MMDA Social Media scrape fallback (Twitter/X public feed)

Provides:
  - get_number_coding(plate_last_digit, dt=None)  → is vehicle coded today?
  - get_road_closures()                           → list of active closures
  - apply_mmda_to_routes(routes, plate, dt)       → flag coded routes
  - get_mmda_status_html(plate, dt)               → banner HTML

Nothing runs on import. All logic is in pure functions.
Cache TTL: 10 minutes for closures, 1 hour for coding schedule.
"""

import requests
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from functools import lru_cache

# Suppress InsecureRequestWarning — MMDA endpoints have cert issues in local dev
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_PHT = timezone(timedelta(hours=8))

# ── Browser-like headers to avoid 403 ────────────────────────────────────────
# MMDA Traffic Navigator blocks plain script requests — spoof a real browser.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection":      "keep-alive",
}

# ── Number Coding Schedule ────────────────────────────────────────────────────
# Source: MMDA Unified Vehicular Volume Reduction Program (UVVRP)
# Coding hours: 7:00 AM – 8:00 PM on weekdays only
# Last digits coded per day (Mon=0, Tue=1, ... Fri=4)
_CODING_SCHEDULE = {
    0: [1, 2],   # Monday
    1: [3, 4],   # Tuesday
    2: [5, 6],   # Wednesday
    3: [7, 8],   # Thursday
    4: [9, 0],   # Friday
}
_CODING_START_H = 7
_CODING_END_H   = 20


def get_number_coding(plate_last_digit: int, dt: datetime = None) -> dict:
    """
    Check if a vehicle is subject to number coding right now (or at a given time).

    Args:
        plate_last_digit: Last digit of plate number (0-9)
        dt: datetime to check (default: now PHT)

    Returns:
        {
          "coded":        bool,
          "digit":        int,
          "day_name":     str,
          "coded_digits": list,
          "window":       str,   # "7:00 AM – 8:00 PM"
          "reason":       str,
          "color":        str,
        }
    """
    if dt is None:
        dt = datetime.now(_PHT)
    else:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_PHT)

    weekday   = dt.weekday()   # 0=Mon, 6=Sun
    hour      = dt.hour
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_name  = day_names[weekday]

    # Weekends: no coding
    if weekday >= 5:
        return _coding_result(False, plate_last_digit, day_name, [],
                              f"No coding on {day_name}s.", "#27ae60")

    coded_digits = _CODING_SCHEDULE.get(weekday, [])
    in_window    = _CODING_START_H <= hour < _CODING_END_H

    if plate_last_digit in coded_digits and in_window:
        return _coding_result(True, plate_last_digit, day_name, coded_digits,
                              f"Plate ending in {plate_last_digit} is coded on {day_name}s "
                              f"({_CODING_START_H}:00 AM – {_CODING_END_H}:00 PM).",
                              "#c0392b")
    elif plate_last_digit in coded_digits and not in_window:
        window = "before 7:00 AM" if hour < _CODING_START_H else "after 8:00 PM"
        return _coding_result(False, plate_last_digit, day_name, coded_digits,
                              f"Plate ending in {plate_last_digit} is coded on {day_name}s "
                              f"but coding window is currently closed ({window}).",
                              "#f39c12")
    else:
        return _coding_result(False, plate_last_digit, day_name, coded_digits,
                              f"Plate ending in {plate_last_digit} is NOT coded today ({day_name}). "
                              f"Coded digits today: {', '.join(str(d) for d in coded_digits)}.",
                              "#27ae60")


def _coding_result(coded, digit, day, coded_digits, reason, color):
    return {
        "coded":        coded,
        "digit":        digit,
        "day_name":     day,
        "coded_digits": coded_digits,
        "window":       f"{_CODING_START_H}:00 AM – {_CODING_END_H}:00 PM",
        "reason":       reason,
        "color":        color,
    }


# ── Road Closures ─────────────────────────────────────────────────────────────
# mmda.gov.ph + trafficnavigator.mmda.gov.ph are both behind Cloudflare Bot
# Fight Mode and return 403 to all Python clients unconditionally.
# TomTom/HERE require paid API keys.
#
# CONFIRMED WORKING (no key required):
#   1. OSM Overpass API  — road closure/construction tags, Metro Manila bbox
#   2. GDACS RSS         — PH disaster events affecting roads (floods/quakes)
#
_MNL_BBOX = (14.40, 120.90, 14.85, 121.15)   # minLat, minLon, maxLat, maxLon

_closure_cache: dict = {}
_CLOSURE_TTL = 600  # 10 min


def _is_dns_error(ex: Exception) -> bool:
    msg = str(ex).lower()
    return any(k in msg for k in ("getaddrinfo failed", "name or service not known",
                                   "nameresolutionerror", "failed to resolve",
                                   "nodename nor servname"))


def get_road_closures() -> list:
    """
    Fetch active Metro Manila road closures.
    Sources: OSM Overpass (primary) -> GDACS RSS (fallback).
    Returns [] silently on failure.
    """
    import time
    now = time.time()
    cached = _closure_cache.get("closures")
    if cached and (now - cached["ts"]) < _CLOSURE_TTL:
        return cached["data"]
    closures = _fetch_osm_closures() or _fetch_gdacs_ph_incidents()
    _closure_cache["closures"] = {"ts": now, "data": closures}
    return closures


def _fetch_osm_closures() -> list:
    """OSM Overpass API — confirmed working, free, no key needed."""
    minLat, minLon, maxLat, maxLon = _MNL_BBOX
    bb = f"{minLat},{minLon},{maxLat},{maxLon}"
    # Only fetch ways/nodes that have a name, ref, or addr:street tag so we
    # never end up with a pile of "Unnamed road" entries in the closure list.
    query = (
        '[out:json][timeout:12];'
        '('
        f'way["access"="no"]["highway"]["name"]({bb});'
        f'way["access"="no"]["highway"]["ref"]({bb});'
        f'way["construction"]["highway"]["name"]({bb});'
        f'way["construction"]["highway"]["ref"]({bb});'
        f'way["highway"]["closed"="yes"]["name"]({bb});'
        f'way["highway"]["closed"="yes"]["ref"]({bb});'
        ');'
        'out center 40;'
    )
    try:
        resp = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            headers={"User-Agent": "SafeRoute/1.0 (PH safety navigation)"},
            timeout=15, verify=True,
        )
        if resp.status_code != 200:
            return []
        closures = []
        for el in resp.json().get("elements", [])[:30]:
            tags   = el.get("tags", {})
            name   = (tags.get("name") or tags.get("ref") or tags.get("addr:street") or "").strip()
            if not name:
                continue   # skip — no usable label to show the user
            reason = (tags.get("construction") or tags.get("note") or tags.get("access") or tags.get("barrier") or "Road closure")
            center = el.get("center", {})
            lat    = _safe_float(center.get("lat") or el.get("lat"))
            lon    = _safe_float(center.get("lon") or el.get("lon"))
            sev    = "moderate" if "construction" in tags else "high"
            closures.append({
                "id":          f"osm_{el.get('id', hash(name) & 0xFFFFFF)}",
                "road":        str(name)[:120],
                "direction":   "Both directions",
                "reason":      str(reason).capitalize()[:200],
                "severity":    sev,
                "lat":         lat,
                "lon":         lon,
                "reported_at": datetime.now(_PHT).strftime("%Y-%m-%d %H:%M PHT"),
                "source":      "OpenStreetMap",
                "color":       _severity_color(sev),
                "icon":        "🚧",
            })
        return closures
    except Exception:
        return []


def _fetch_gdacs_ph_incidents() -> list:
    """GDACS RSS filtered to PH bounding box — confirmed working, no key."""
    PH_LAT = (4.5, 21.1)
    PH_LON = (115.8, 127.0)
    try:
        resp = requests.get(
            "https://www.gdacs.org/xml/rss.xml",
            headers={"User-Agent": "SafeRoute/1.0"},
            timeout=10, verify=True,
        )
        if resp.status_code != 200:
            return []
        closures = []
        for item in ET.fromstring(resp.content).findall(".//item"):
            raw = ET.tostring(item, encoding="unicode")
            lat = _safe_float(_re_tag(raw, "geo:lat") or _re_tag(raw, "latitude"))
            lon = _safe_float(_re_tag(raw, "geo:long") or _re_tag(raw, "longitude"))
            if lat is None or lon is None:
                continue
            if not (PH_LAT[0] <= lat <= PH_LAT[1] and PH_LON[0] <= lon <= PH_LON[1]):
                continue
            title    = item.findtext("title") or ""
            desc     = item.findtext("description") or ""
            combined = (title + " " + desc).lower()
            if not any(w in combined for w in ["flood", "earthquake", "cyclone", "landslide"]):
                continue
            sev = "high" if "red" in combined else "moderate" if "orange" in combined else "low"
            closures.append({
                "id":          f"gdacs_{hash(title) & 0xFFFFFF}",
                "road":        title[:120],
                "direction":   "Area advisory",
                "reason":      desc[:200],
                "severity":    sev,
                "lat":         lat,
                "lon":         lon,
                "reported_at": item.findtext("pubDate") or datetime.now(_PHT).strftime("%Y-%m-%d %H:%M PHT"),
                "source":      "GDACS",
                "color":       _severity_color(sev),
                "icon":        "⚠️",
            })
        return closures
    except Exception:
        return []


def _re_tag(xml_str: str, tag: str) -> str | None:
    m = re.search(rf"<{re.escape(tag)}[^>]*>([^<]+)</{re.escape(tag)}>", xml_str)
    return m.group(1).strip() if m else None


def _parse_mmda_item(item: dict) -> dict | None:
    """Parse a raw MMDA API item into our standard format."""
    try:
        road = (item.get("location") or item.get("road") or
                item.get("name") or item.get("title") or "Unknown road")
        reason = (item.get("remarks") or item.get("reason") or
                  item.get("description") or item.get("type") or "Road closure")

        # Try to extract coordinates
        lat = _safe_float(item.get("lat") or item.get("latitude") or item.get("y"))
        lon = _safe_float(item.get("lng") or item.get("lon") or
                          item.get("longitude") or item.get("x"))

        severity = _infer_severity(reason)

        return {
            "id":          str(item.get("id") or id(item)),
            "road":        str(road)[:120],
            "direction":   str(item.get("direction") or item.get("bound") or "Both directions"),
            "reason":      str(reason)[:200],
            "severity":    severity,
            "lat":         lat,
            "lon":         lon,
            "reported_at": str(item.get("date") or item.get("created_at") or
                               datetime.now(_PHT).strftime("%Y-%m-%d %H:%M PHT")),
            "source":      "MMDA",
            "color":       _severity_color(severity),
            "icon":        "🚧",
        }
    except Exception:
        return None


def _infer_severity(text: str) -> str:
    t = (text or "").lower()
    if any(w in t for w in ["closed", "impassable", "flooded", "accident", "fire"]):
        return "high"
    if any(w in t for w in ["heavy", "slow", "construction", "repair"]):
        return "moderate"
    return "low"


def _severity_color(sev: str) -> str:
    return {"low": "#f39c12", "moderate": "#e67e22", "high": "#e74c3c"}.get(sev, "#e67e22")


def _safe_float(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def apply_mmda_to_routes(routes: list, plate_last_digit: int | None = None) -> list:
    """
    Attach MMDA closure warnings to routes.
    Also flags if the vehicle is number-coded.

    Args:
        routes:           Route list
        plate_last_digit: Last digit of user's plate (None = skip coding check)
    """
    closures = get_road_closures()
    coding   = get_number_coding(plate_last_digit) if plate_last_digit is not None else None

    for route in routes:
        route["mmda_closures"]      = []
        route["number_coded"]       = False
        route["number_coding_info"] = None

        # Number coding — apply to car/motorcycle only
        if coding and coding["coded"]:
            ct = route.get("commuter_type", "").lower()
            if any(x in ct for x in ["car", "motor", "motorcycle", "drive"]):
                route["number_coded"]       = True
                route["number_coding_info"] = coding
                from risk_monitor.features import apply_penalty_to_route
                apply_penalty_to_route(route, 20, ct)

        # Road closures — proximity check if coords available
        coords = _get_route_coords(route)
        for closure in closures:
            if closure.get("lat") and closure.get("lon"):
                if _near_route(closure["lat"], closure["lon"], coords, radius_deg=0.008):
                    route["mmda_closures"].append(closure)

    return routes


def _get_route_coords(route: dict) -> list:
    coords = []
    if route.get("coords"):
        return route["coords"]
    for seg in route.get("segments", []):
        if seg.get("coords"):
            coords.extend(seg["coords"])
    return coords


def _near_route(lat: float, lon: float, coords: list, radius_deg: float = 0.008) -> bool:
    if not coords:
        return False
    for pt in coords[::10]:
        if abs(pt[0] - lat) < radius_deg and abs(pt[1] - lon) < radius_deg:
            return True
    return False


def get_mmda_banner_html(coding: dict, closures: list) -> str:
    """
    Returns an HTML banner for number coding + closure alerts.
    Returns empty string if nothing to warn about.
    """
    parts = []
    if coding and coding["coded"]:
        parts.append(
            f'<div style="background:#c0392b;color:#fff;padding:7px 16px;font-size:13px;'
            f'font-weight:bold;text-align:center;">🚗 Number Coding: {coding["reason"]}</div>'
        )
    if closures:
        named = [c for c in closures if c["road"].strip().lower() not in ("unnamed road", "")]
        if named:
            roads = ", ".join(c["road"] for c in named[:3])
            parts.append(
                f'<div style="background:#e67e22;color:#fff;padding:7px 16px;font-size:13px;'
                f'font-weight:bold;text-align:center;">🚧 Road Closure: {roads}</div>'
            )
    return "\n".join(parts)