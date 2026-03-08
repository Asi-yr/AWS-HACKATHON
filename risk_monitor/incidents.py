"""
incidents.py
------------
Real-time incident feed for SafeRoute Philippines.

Data sources (all public, no API key required):
  1. NDRRMC (National Disaster Risk Reduction and Management Council)
     RSS feed — official PH government disaster/incident alerts
     https://www.ndrrmc.gov.ph/

  2. GDACS (Global Disaster Alerting Coordination System)
     RSS feed filtered to Philippines
     https://www.gdacs.org/

  3. PAGASA severe weather advisories (already in features.py for typhoon)
     Reused here for fire-relevant weather (drought, heat advisory).

  4. Community reports from the app's own DB (fire, road_closed, flooding)
     These are the most real-time — submitted by users, verified by confirmations.

Incident types returned:
    {
      "id":          str,          # unique key
      "type":        str,          # "fire", "flood", "earthquake", "hazmat", "road_closed"
      "title":       str,
      "description": str,
      "lat":         float or None,
      "lon":         float or None,
      "radius_m":    int,          # estimated affected radius in meters
      "severity":    str,          # "low", "moderate", "high", "critical"
      "color":       str,          # hex
      "icon":        str,          # emoji
      "source":      str,          # source name
      "source_url":  str,
      "reported_at": str,
      "expires_in_h":int,          # approximate expiry hours
    }

Integration in main.py:
    from risk_monitor.incidents import get_active_incidents, apply_incidents_to_routes

    incidents = get_active_incidents()
    apply_incidents_to_routes(routes, incidents, orig_lat, orig_lon, dest_lat, dest_lon)
    nav_response["incidents"] = incidents
"""

import requests
import json
import time
import re
import os
from datetime import datetime, timezone, timedelta

# ── Cache ─────────────────────────────────────────────────────────────────────
_CACHE: dict = {}
_CACHE_TTL   = 600   # 10 minutes — incidents are time-sensitive

_PHT = timezone(timedelta(hours=8))

# ── Severity config ───────────────────────────────────────────────────────────
_SEVERITY_COLORS = {
    "low":      "#f39c12",
    "moderate": "#e67e22",
    "high":     "#e74c3c",
    "critical": "#6c1a1a",
}

_TYPE_ICONS = {
    "fire":       "🔥",
    "flood":      "🌊",
    "earthquake": "🌍",
    "hazmat":     "☣️",
    "road_closed":"🚧",
    "landslide":  "⛰️",
    "accident":   "💥",
    "other":      "⚠️",
}

_TYPE_RADIUS = {
    "fire":       600,
    "flood":      800,
    "earthquake": 5000,
    "hazmat":     500,
    "road_closed":150,
    "landslide":  400,
    "accident":   200,
    "other":      300,
}

# ── Safety penalty per incident type ──────────────────────────────────────────
_INCIDENT_PENALTY = {
    "fire":       50,
    "flood":      35,
    "earthquake": 40,
    "hazmat":     45,
    "road_closed":20,
    "landslide":  35,
    "accident":   15,
    "other":      10,
}


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def get_active_incidents(ph_only: bool = True) -> list:
    """
    Fetch and merge incident data from all available sources.
    Returns a deduplicated list of active incident dicts.
    Results are cached for 10 minutes.
    """
    cache_key = "incidents_ph" if ph_only else "incidents_all"
    cached = _CACHE.get(cache_key)
    if cached and (time.time() - cached["ts"]) < _CACHE_TTL:
        return cached["data"]

    incidents = []

    # Source 1: NDRRMC RSS (official PH government)
    try:
        ndrrmc = _fetch_ndrrmc_incidents()
        incidents.extend(ndrrmc)
    except Exception as e:
        print(f"[incidents] NDRRMC fetch failed: {e}")

    # Source 2: GDACS filtered to PH
    try:
        gdacs = _fetch_gdacs_incidents()
        incidents.extend(gdacs)
    except Exception as e:
        print(f"[incidents] GDACS fetch failed: {e}")

    # Source 3: ReliefWeb API (UN OCHA) — PH disasters
    try:
        rw = _fetch_reliefweb_incidents()
        incidents.extend(rw)
    except Exception as e:
        print(f"[incidents] ReliefWeb fetch failed: {e}")

    # Deduplicate by proximity + type
    incidents = _deduplicate(incidents)

    _CACHE[cache_key] = {"ts": time.time(), "data": incidents}
    return incidents


def get_incidents_near(lat: float, lon: float, radius_m: float = 5000) -> list:
    """Return only incidents within radius_m metres of (lat, lon)."""
    import math
    all_inc = get_active_incidents()
    result  = []
    for inc in all_inc:
        if inc.get("lat") is None or inc.get("lon") is None:
            continue
        dist = _haversine_m(lat, lon, inc["lat"], inc["lon"])
        if dist <= radius_m + inc.get("radius_m", 300):
            result.append({**inc, "_dist_m": int(dist)})
    return sorted(result, key=lambda x: x["_dist_m"])


def apply_incidents_to_routes(
    routes: list,
    incidents: list,
    orig_lat: float, orig_lon: float,
    dest_lat: float, dest_lon: float,
    scan_radius_m: float = 1500,
) -> list:
    """
    For each route, check if any known incident falls along its path.
    Applies safety score penalty and attaches incident_warnings list.

    Also flags routes that pass through active fire zones with
    route['avoid_recommended'] = True for the frontend to highlight.
    """
    from risk_monitor.features import get_score_color, get_score_label

    for route in routes:
        # Collect waypoints from this route's geometry
        wps = _extract_waypoints(route)
        if not wps:
            # Fallback: just check endpoints
            wps = [[orig_lat, orig_lon], [dest_lat, dest_lon]]

        route_incidents = []
        seen_ids        = set()

        for inc in incidents:
            if inc.get("lat") is None: continue
            if inc["id"] in seen_ids:  continue

            inc_radius = inc.get("radius_m", 300)

            # Sample waypoints every ~500m along the route
            step = max(1, len(wps) // 40)
            hit  = False
            for wp in wps[::step]:
                dist = _haversine_m(wp[0], wp[1], inc["lat"], inc["lon"])
                if dist <= inc_radius + scan_radius_m:
                    hit = True
                    break

            if hit:
                seen_ids.add(inc["id"])
                route_incidents.append(inc)

        # Apply cumulative penalty from all incidents on this route
        total_penalty = 0
        for inc in route_incidents:
            sev = inc.get("severity", "moderate")
            base_pen = _INCIDENT_PENALTY.get(inc["type"], 10)
            multiplier = {"low": 0.5, "moderate": 1.0, "high": 1.5, "critical": 2.0}.get(sev, 1.0)
            total_penalty += int(base_pen * multiplier)

        if total_penalty > 0:
            route["safety_score"] = max(0, route.get("safety_score", 75) - total_penalty)
            route["score_color"]  = get_score_color(route["safety_score"])
            route["score_label"]  = get_score_label(route["safety_score"])

        # Build human-readable warnings
        warnings = []
        for inc in route_incidents:
            icon = _TYPE_ICONS.get(inc["type"], "⚠️")
            dist_txt = f" ({inc.get('_dist_m', '?')}m from route)" if "_dist_m" in inc else ""
            warnings.append(f"{icon} {inc['title']}{dist_txt}")

        route["incident_warnings"] = warnings

        # Fire-specific flag — drives "avoid recommended" UI
        fire_on_route = any(i["type"] == "fire" for i in route_incidents)
        route["avoid_recommended"] = fire_on_route
        if fire_on_route:
            route["fire_warning"] = (
                "🔥 Active fire incident reported along this route. "
                "An alternate route is strongly recommended."
            )

    return routes


def get_incidents_map_data(incidents: list) -> list:
    """
    Returns a JSON-serialisable list suitable for the frontend to
    draw incident markers on the Leaflet map.
    """
    return [
        {
            "id":          inc["id"],
            "type":        inc["type"],
            "title":       inc["title"],
            "description": inc.get("description", ""),
            "lat":         inc["lat"],
            "lon":         inc["lon"],
            "radius_m":    inc.get("radius_m", 300),
            "severity":    inc.get("severity", "moderate"),
            "color":       inc.get("color", "#e74c3c"),
            "icon":        _TYPE_ICONS.get(inc["type"], "⚠️"),
            "source":      inc.get("source", ""),
            "source_url":  inc.get("source_url", ""),
            "reported_at": inc.get("reported_at", ""),
        }
        for inc in incidents
        if inc.get("lat") is not None
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# DATA SOURCE FETCHERS
# ═══════════════════════════════════════════════════════════════════════════════

def _fetch_ndrrmc_incidents() -> list:
    """
    Fetch from NDRRMC's public situation report page and parse active incidents.
    NDRRMC publishes situation reports as PDFs + JSON summaries.
    We use their public API endpoint for active advisories.
    """
    incidents = []

    # NDRRMC publishes flood and fire advisories via their public feed
    urls_to_try = [
        "https://www.ndrrmc.gov.ph/index.php/component/content/?format=json&layout=featured",
        "https://ndrrmc.gov.ph/rss.xml",
    ]

    headers = {"User-Agent": "SafeRoute/1.0 (safety research, contact@saferoute.local)"}

    for url in urls_to_try:
        try:
            resp = requests.get(url, headers=headers, timeout=8)
            if resp.status_code != 200:
                continue

            text = resp.text
            # Parse RSS if XML
            if "<?xml" in text or "<rss" in text:
                items = _parse_rss_items(text)
                for item in items[:15]:
                    inc = _classify_ndrrmc_item(item)
                    if inc:
                        incidents.append(inc)
                break
        except Exception:
            continue

    return incidents


def _fetch_gdacs_incidents() -> list:
    """
    Fetch from GDACS RSS feed, filter to Philippines bounding box.
    PH bounding box: lat 4.5–21.1, lon 115.8–127.0
    """
    GDACS_RSS = "https://www.gdacs.org/xml/rss.xml"
    PH_LAT_MIN, PH_LAT_MAX = 4.5,   21.1
    PH_LON_MIN, PH_LON_MAX = 115.8, 127.0

    headers = {"User-Agent": "SafeRoute/1.0"}
    incidents = []

    try:
        resp = requests.get(GDACS_RSS, headers=headers, timeout=10)
        if resp.status_code != 200:
            return incidents

        items = _parse_rss_items(resp.text)
        for item in items:
            # GDACS embeds geo:lat / geo:long in items
            lat = _extract_geo_tag(item.get("raw", ""), "lat")
            lon = _extract_geo_tag(item.get("raw", ""), "long")

            # Skip if no geo or outside Philippines
            if lat is None or lon is None:
                continue
            if not (PH_LAT_MIN <= lat <= PH_LAT_MAX and PH_LON_MIN <= lon <= PH_LON_MAX):
                continue

            title = item.get("title", "")
            desc  = item.get("description", "")
            itype = _classify_gdacs_type(title + " " + desc)

            severity = "moderate"
            if "Red" in title or "RED" in title:
                severity = "high"
            elif "Orange" in title or "ORANGE" in title:
                severity = "moderate"
            elif "Green" in title or "GREEN" in title:
                severity = "low"

            incidents.append({
                "id":          f"gdacs_{hash(title) & 0xFFFFFF}",
                "type":        itype,
                "title":       title[:80],
                "description": desc[:200],
                "lat":         lat,
                "lon":         lon,
                "radius_m":    _TYPE_RADIUS.get(itype, 500),
                "severity":    severity,
                "color":       _SEVERITY_COLORS.get(severity, "#e74c3c"),
                "source":      "GDACS",
                "source_url":  item.get("link", "https://www.gdacs.org/"),
                "reported_at": item.get("pubDate", ""),
                "expires_in_h": 24,
            })

    except Exception as e:
        print(f"[incidents] GDACS parse error: {e}")

    return incidents


def _fetch_reliefweb_incidents() -> list:
    """
    ReliefWeb API (UN OCHA) — free, no key needed.
    Fetches recent disasters/crises for Philippines.
    https://apidoc.reliefweb.int/
    """
    url = "https://api.reliefweb.int/v1/disasters?appname=saferoute&filter[field]=country.iso3&filter[value]=PHL&limit=10&sort[]=date:desc&fields[include][]=name&fields[include][]=type&fields[include][]=status&fields[include][]=date"

    headers = {"User-Agent": "SafeRoute/1.0"}
    incidents = []

    try:
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code != 200:
            return incidents

        data  = resp.json()
        items = data.get("data", [])

        for item in items[:10]:
            fields = item.get("fields", {})
            name   = fields.get("name", "")
            status = fields.get("status", "")
            if status not in ("alert", "ongoing"):
                continue  # Skip past/closed disasters

            dtype = fields.get("type", [{}])
            dtype_name = dtype[0].get("name", "").lower() if dtype else ""
            itype = _classify_reliefweb_type(dtype_name + " " + name.lower())

            # ReliefWeb doesn't always have precise coordinates — use Manila centroid
            # as a country-level placeholder (shown differently in UI)
            date_str = fields.get("date", {}).get("created", "")

            incidents.append({
                "id":          f"rw_{item.get('id', hash(name) & 0xFFFFFF)}",
                "type":        itype,
                "title":       name[:80],
                "description": f"Status: {status}. Source: ReliefWeb / UN OCHA",
                "lat":         None,   # Country-level — no precise coords
                "lon":         None,
                "radius_m":    _TYPE_RADIUS.get(itype, 500),
                "severity":    "high" if status == "alert" else "moderate",
                "color":       _SEVERITY_COLORS.get("high" if status == "alert" else "moderate"),
                "source":      "ReliefWeb / UN OCHA",
                "source_url":  f"https://reliefweb.int/disaster/{item.get('id', '')}",
                "reported_at": date_str,
                "expires_in_h": 48,
                "_country_level": True,  # No map pin, but shown in sidebar
            })

    except Exception as e:
        print(f"[incidents] ReliefWeb error: {e}")

    return incidents


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_rss_items(xml_text: str) -> list:
    """Very lightweight RSS parser — avoids lxml dependency."""
    items   = []
    pattern = re.compile(r'<item[^>]*>(.*?)</item>', re.DOTALL | re.IGNORECASE)
    for m in pattern.finditer(xml_text):
        raw   = m.group(1)
        title = _tag(raw, "title")
        desc  = _tag(raw, "description") or _tag(raw, "summary")
        link  = _tag(raw, "link") or _tag(raw, "guid")
        pub   = _tag(raw, "pubDate") or _tag(raw, "dc:date") or ""
        items.append({"title": title, "description": desc,
                       "link": link, "pubDate": pub, "raw": raw})
    return items


def _tag(text: str, name: str) -> str:
    m = re.search(rf'<{name}[^>]*>(.*?)</{name}>', text, re.DOTALL | re.IGNORECASE)
    if not m:
        return ""
    # Strip CDATA
    val = m.group(1).strip()
    val = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', val, flags=re.DOTALL)
    # Strip HTML tags
    val = re.sub(r'<[^>]+>', '', val)
    return val.strip()


def _extract_geo_tag(text: str, tag: str) -> float | None:
    m = re.search(rf'geo:{tag}>([0-9.\-]+)', text, re.IGNORECASE)
    if not m:
        m = re.search(rf'{tag}="([0-9.\-]+)"', text, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def _classify_gdacs_type(text: str) -> str:
    t = text.lower()
    if any(x in t for x in ["fire", "wildfire", "blaze"]):   return "fire"
    if any(x in t for x in ["flood", "inundation"]):          return "flood"
    if any(x in t for x in ["earthquake", "quake", "seismic"]):return "earthquake"
    if any(x in t for x in ["cyclone", "typhoon", "storm"]):  return "flood"
    if any(x in t for x in ["landslide", "mudslide"]):        return "landslide"
    if any(x in t for x in ["hazmat", "chemical", "spill"]):  return "hazmat"
    return "other"


def _classify_reliefweb_type(text: str) -> str:
    return _classify_gdacs_type(text)


def _classify_ndrrmc_item(item: dict) -> dict | None:
    title = item.get("title", "")
    desc  = item.get("description", "")
    text  = (title + " " + desc).lower()

    itype = _classify_gdacs_type(text)
    if itype == "other" and not any(x in text for x in ["disaster", "emergency", "incident", "hazard", "fire", "flood"]):
        return None

    # Try to extract coordinates from description (NDRRMC sometimes includes DMS)
    lat = _extract_dms_or_decimal(desc, "lat")
    lon = _extract_dms_or_decimal(desc, "lon")

    severity = "moderate"
    if any(x in text for x in ["critical", "severe", "major", "catastrophic"]):
        severity = "high"
    elif any(x in text for x in ["minor", "small"]):
        severity = "low"

    return {
        "id":          f"ndrrmc_{hash(title) & 0xFFFFFF}",
        "type":        itype,
        "title":       title[:80],
        "description": desc[:200],
        "lat":         lat,
        "lon":         lon,
        "radius_m":    _TYPE_RADIUS.get(itype, 400),
        "severity":    severity,
        "color":       _SEVERITY_COLORS.get(severity, "#e67e22"),
        "source":      "NDRRMC",
        "source_url":  item.get("link", "https://www.ndrrmc.gov.ph/"),
        "reported_at": item.get("pubDate", ""),
        "expires_in_h": 12,
    }


def _extract_dms_or_decimal(text: str, which: str) -> float | None:
    """Try to extract lat or lon from text. Very basic — looks for decimal degrees."""
    if which == "lat":
        m = re.search(r'(?:lat(?:itude)?[:\s]+)([0-9]{1,2}\.[0-9]+)', text, re.IGNORECASE)
    else:
        m = re.search(r'(?:lon(?:gitude)?[:\s]+)([0-9]{2,3}\.[0-9]+)', text, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def _deduplicate(incidents: list) -> list:
    """Remove near-duplicate incidents (same type within 2km)."""
    seen    = []
    result  = []
    for inc in incidents:
        lat, lon = inc.get("lat"), inc.get("lon")
        itype    = inc.get("type", "other")
        dup      = False
        if lat and lon:
            for s_lat, s_lon, s_type in seen:
                if s_type == itype and _haversine_m(lat, lon, s_lat, s_lon) < 2000:
                    dup = True
                    break
            if not dup:
                seen.append((lat, lon, itype))
        if not dup:
            result.append(inc)
    return result


def _extract_waypoints(route: dict) -> list:
    """Extract [lat, lon] waypoints from a route dict."""
    wps = []
    if route.get("segments"):
        for seg in route["segments"]:
            c = seg.get("coords", [])
            if c and isinstance(c[0], list) and isinstance(c[0][0], list):
                for sub in c: wps.extend(sub)
            else:
                wps.extend(c)
    if not wps:
        wps = route.get("coords", [])
    return wps


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    import math
    R  = 6_371_000
    φ1 = math.radians(lat1); φ2 = math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lon2 - lon1)
    a  = math.sin(dφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(dλ/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
