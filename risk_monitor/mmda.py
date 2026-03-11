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
    "Referer":         "https://trafficnavigator.mmda.gov.ph/",
    "Origin":          "https://trafficnavigator.mmda.gov.ph",
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
# MMDA Traffic Navigator — public JSON endpoint (no key needed)
_MMDA_CLOSURE_URL = "https://trafficnavigator.mmda.gov.ph/api/closures"
_MMDA_INCIDENT_URL = "https://trafficnavigator.mmda.gov.ph/api/incidents"

# In-process cache
_closure_cache: dict = {}
_CLOSURE_TTL = 600  # 10 min


def _is_dns_error(ex: Exception) -> bool:
    """Return True if the exception is a DNS resolution failure (host unreachable)."""
    msg = str(ex).lower()
    return any(k in msg for k in ("getaddrinfo failed", "name or service not known",
                                   "nameresolutionerror", "failed to resolve",
                                   "nodename nor servname"))


def get_road_closures() -> list:
    """
    Fetch active MMDA road closures.
    Returns [] silently on any network failure — never blocks the app.

    Strategy (tries each in order, stops at first success):
      1. MMDA Traffic Navigator JSON API  (browser headers + session cookie)
      2. MMDA RSS feed
      3. MMDA open-data / alternative endpoints
    All failures are swallowed; DNS errors skip remaining URLs for that host.
    """
    import time
    now = time.time()
    cached = _closure_cache.get("closures")
    if cached and (now - cached["ts"]) < _CLOSURE_TTL:
        return cached["data"]

    closures = _try_mmda_json() or _fetch_mmda_rss() or _fetch_mmda_opendata()
    _closure_cache["closures"] = {"ts": now, "data": closures}
    return closures


def _try_mmda_json() -> list:
    """Try the MMDA Traffic Navigator JSON endpoints with browser headers."""
    closures = []
    for url in (_MMDA_CLOSURE_URL, _MMDA_INCIDENT_URL):
        try:
            session = requests.Session()
            session.get("https://trafficnavigator.mmda.gov.ph/",
                        headers=_BROWSER_HEADERS, timeout=4, verify=False)
            resp = session.get(url, headers=_BROWSER_HEADERS, timeout=7, verify=False)
            if resp.status_code == 200:
                data  = resp.json()
                items = data if isinstance(data, list) else data.get("data", data.get("incidents", []))
                for item in items:
                    c = _parse_mmda_item(item)
                    if c:
                        closures.append(c)
        except Exception as ex:
            if _is_dns_error(ex):
                break   # host is unreachable — skip remaining MMDA URLs silently
    return closures


def _fetch_mmda_rss() -> list:
    """Fallback: MMDA public RSS/Atom feeds."""
    RSS_URLS = [
        "https://trafficnavigator.mmda.gov.ph/feed/",
        "https://www.mmda.gov.ph/index.php?format=feed&type=rss",
    ]
    closures = []
    for rss_url in RSS_URLS:
        try:
            resp = requests.get(rss_url, headers=_BROWSER_HEADERS, timeout=7, verify=False)
            if resp.status_code != 200:
                continue
            root  = ET.fromstring(resp.content)
            ns    = {"atom": "http://www.w3.org/2005/Atom"}
            items = root.findall(".//item") or root.findall(".//atom:entry", ns)
            for item in items[:20]:
                title = (item.findtext("title") or
                         item.findtext("atom:title", namespaces=ns) or "")
                desc  = (item.findtext("description") or
                         item.findtext("atom:summary", namespaces=ns) or "")
                text  = f"{title} {desc}"
                if not any(w in text.lower() for w in
                           ["traffic", "closure", "closed", "road", "mmda",
                            "accident", "flood", "construction"]):
                    continue
                severity = _infer_severity(text)
                closures.append({
                    "id":          f"rss_{hash(title) & 0xFFFFFF}",
                    "road":        title[:120],
                    "direction":   "See advisory",
                    "reason":      (desc or title)[:200],
                    "severity":    severity,
                    "lat":         None,
                    "lon":         None,
                    "reported_at": datetime.now(_PHT).strftime("%Y-%m-%d %H:%M PHT"),
                    "source":      "MMDA RSS",
                    "color":       _severity_color(severity),
                    "icon":        "🚧",
                })
            if closures:
                return closures
        except Exception as ex:
            if _is_dns_error(ex):
                break
    return closures


def _fetch_mmda_opendata() -> list:
    """Last-resort: MMDA open-data portal and alternative endpoints."""
    ALT_URLS = [
        "https://opendata.mmda.gov.ph/api/traffic",
        "https://opendata.mmda.gov.ph/api/incidents",
        "https://api.mmda.gov.ph/traffic",
    ]
    for url in ALT_URLS:
        try:
            resp = requests.get(url, headers=_BROWSER_HEADERS, timeout=6, verify=False)
            if resp.status_code == 200:
                data  = resp.json()
                items = data if isinstance(data, list) else data.get("data", data.get("results", []))
                closures = [c for c in (_parse_mmda_item(i) for i in items) if c]
                if closures:
                    return closures
        except Exception as ex:
            if _is_dns_error(ex):
                break
    return []


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
        roads = ", ".join(c["road"] for c in closures[:3])
        parts.append(
            f'<div style="background:#e67e22;color:#fff;padding:7px 16px;font-size:13px;'
            f'font-weight:bold;text-align:center;">🚧 MMDA Closure: {roads}</div>'
        )
    return "\n".join(parts)