"""
safe_spots.py
-------------
Refuge points and safe spots for SafeRoute.

Sources:
  1. OpenStreetMap Overpass API — police, hospitals, fire stations, pharmacies,
     7-Eleven / convenience stores, barangay halls (all free, no key needed)
  2. User-submitted safe spots (stored in app DB via community_reports.py)

A "safe spot" is any location a commuter can retreat to if they feel unsafe,
need help, or need to wait out a hazard (flood, typhoon, civil unrest).

Nothing runs on import. Cache TTL: 30 minutes (OSM data is stable).
"""

import requests
import math
from datetime import datetime, timezone, timedelta

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_PHT = timezone(timedelta(hours=8))

# Overpass API endpoint
_OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Cache
_spot_cache: dict = {}
_SPOT_TTL = 1800   # 30 minutes

# ── OSM amenity → safe spot config ───────────────────────────────────────────
_AMENITY_CFG = {
    "police":           {"icon": "👮", "label": "Police Station",   "color": "#2980b9", "priority": 1},
    "hospital":         {"icon": "🏥", "label": "Hospital",          "color": "#e74c3c", "priority": 1},
    "fire_station":     {"icon": "🚒", "label": "Fire Station",      "color": "#e67e22", "priority": 2},
    "pharmacy":         {"icon": "💊", "label": "Pharmacy",          "color": "#27ae60", "priority": 3},
    "clinic":           {"icon": "🏥", "label": "Clinic",            "color": "#27ae60", "priority": 3},
    "barangay_hall":    {"icon": "🏛️", "label": "Barangay Hall",     "color": "#8e44ad", "priority": 2},
    "community_centre": {"icon": "🏛️", "label": "Community Center",  "color": "#8e44ad", "priority": 3},
    "convenience":      {"icon": "🏪", "label": "Convenience Store", "color": "#16a085", "priority": 4},
}

# Shop tags (7-Eleven, convenience stores)
_SHOP_CFG = {
    "convenience": {"icon": "🏪", "label": "Convenience Store", "color": "#16a085", "priority": 4},
    "supermarket": {"icon": "🛒", "label": "Supermarket",        "color": "#16a085", "priority": 4},
}

# Evacuation centers (OSM social_facility or emergency tags)
_EMERGENCY_CFG = {
    "evacuation_centre": {"icon": "⛺", "label": "Evacuation Center", "color": "#c0392b", "priority": 1},
}


def get_safe_spots_near(lat: float, lon: float, radius_m: int = 1500) -> list:
    """
    Fetch safe spots within radius_m meters of a coordinate via OSM Overpass.

    Args:
        lat, lon:  Center coordinate
        radius_m:  Search radius in meters (default 1500 = ~15 min walk)

    Returns list of:
        {
          "id":       str,
          "name":     str,
          "type":     str,       # amenity type key
          "label":    str,       # human label
          "icon":     str,
          "color":    str,
          "lat":      float,
          "lon":      float,
          "address":  str,
          "priority": int,       # 1 = highest priority refuge
          "dist_m":   float,     # distance from query point
          "open_24h": bool,
        }
    """
    import time as _time
    cache_key = f"{round(lat,3)}_{round(lon,3)}_{radius_m}"
    now = _time.time()
    cached = _spot_cache.get(cache_key)
    if cached and (now - cached["ts"]) < _SPOT_TTL:
        return cached["data"]

    # Build Overpass QL query — fetch all relevant amenity types in one call
    amenity_list = "|".join(_AMENITY_CFG.keys())
    shop_list    = "|".join(_SHOP_CFG.keys())

    query = f"""
    [out:json][timeout:15];
    (
      node(around:{radius_m},{lat},{lon})[amenity~"^({amenity_list})$"];
      way(around:{radius_m},{lat},{lon})[amenity~"^({amenity_list})$"];
      node(around:{radius_m},{lat},{lon})[shop~"^({shop_list})$"];
      node(around:{radius_m},{lat},{lon})[emergency="evacuation_centre"];
      node(around:{radius_m},{lat},{lon})["social_facility"="evacuation_centre"];
    );
    out center tags;
    """

    try:
        resp = requests.post(_OVERPASS_URL,
                             data={"data": query},
                             headers={"User-Agent": "SafeRoute/1.0"},
                             timeout=15)
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
    except Exception:
        _spot_cache[cache_key] = {"ts": now, "data": []}
        return []

    spots = []
    seen  = set()

    for el in elements:
        tags = el.get("tags", {})
        # Get coordinates (nodes have lat/lon directly; ways have center)
        el_lat = el.get("lat") or (el.get("center") or {}).get("lat")
        el_lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if not el_lat or not el_lon:
            continue

        # Determine type and config
        amenity = tags.get("amenity", "")
        shop    = tags.get("shop", "")
        emerg   = tags.get("emergency", "") or tags.get("social_facility", "")

        cfg = (_AMENITY_CFG.get(amenity) or
               _SHOP_CFG.get(shop) or
               (_EMERGENCY_CFG.get("evacuation_centre") if "evacuation" in emerg else None))
        if not cfg:
            continue

        name = (tags.get("name") or
                tags.get("name:en") or
                cfg["label"])

        # De-duplicate by rounded coords
        key = f"{round(el_lat,4)}_{round(el_lon,4)}"
        if key in seen:
            continue
        seen.add(key)

        dist_m = _haversine_m(lat, lon, el_lat, el_lon)
        addr   = _build_address(tags)
        open24 = tags.get("opening_hours", "").lower() in ("24/7", "mo-su 00:00-24:00")

        spots.append({
            "id":       str(el.get("id", key)),
            "name":     name,
            "type":     amenity or shop or emerg,
            "label":    cfg["label"],
            "icon":     cfg["icon"],
            "color":    cfg["color"],
            "lat":      el_lat,
            "lon":      el_lon,
            "address":  addr,
            "priority": cfg["priority"],
            "dist_m":   round(dist_m),
            "open_24h": open24,
        })

    # Sort: priority first (police/hospital), then by distance
    spots.sort(key=lambda s: (s["priority"], s["dist_m"]))

    _spot_cache[cache_key] = {"ts": now, "data": spots}
    return spots


def _pick_route_sample_points(route_coords: list, num_points: int) -> list:
    """Pick num_points evenly spaced coords from route_coords (always includes first + last)."""
    total = len(route_coords)
    if total == 0:
        return []
    if total <= num_points:
        return list(route_coords)
    indices = [int(round(i * (total - 1) / (num_points - 1))) for i in range(num_points)]
    seen = set()
    result = []
    for idx in indices:
        if idx not in seen:
            seen.add(idx)
            result.append(route_coords[idx])
    return result


def get_safe_spots_along_route(route_coords: list,
                                num_sample_points: int = 10,
                                radius_m: int = 600) -> list:
    """
    Find safe spots evenly distributed along the full route path.
    Uses ThreadPoolExecutor to query all sample points in parallel,
    making it 5-10x faster than sequential queries.

    Returns de-duplicated list of safe spots sorted by priority then distance.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if not route_coords:
        return []

    sample = _pick_route_sample_points(route_coords, num_sample_points)
    if not sample:
        return []

    seen_ids  = set()
    all_spots = []

    # Parallel Overpass queries — each independent, safe to run concurrently
    with ThreadPoolExecutor(max_workers=min(len(sample), 10)) as pool:
        futures = {pool.submit(get_safe_spots_near, pt[0], pt[1], radius_m): pt
                   for pt in sample}
        for fut in as_completed(futures):
            try:
                spots = fut.result()
            except Exception:
                spots = []
            for s in spots:
                if s["id"] not in seen_ids:
                    seen_ids.add(s["id"])
                    all_spots.append(s)

    all_spots.sort(key=lambda s: (s["priority"], s["dist_m"]))
    return all_spots   # no cap — return everything found along the full route


def get_flat_route_coords(route: dict) -> list:
    """
    Extract a flat list of [lat, lon] coordinates from a route object,
    handling all route types (road, train, jeepney, bus, transit, multimodal).
    """
    coords = []
    if route.get("segments"):
        for seg in route["segments"]:
            sc = seg.get("coords", [])
            # Train segments have nested lists: [[[lat,lon],...],...]
            if sc and isinstance(sc[0], list) and sc[0] and isinstance(sc[0][0], list):
                for sub in sc:
                    coords.extend(sub)
            else:
                coords.extend(sc)
    if not coords and route.get("coords"):
        coords = route["coords"]
    return coords


def apply_safe_spots_to_routes(routes: list) -> list:
    """
    Attach safe spots to each route on-demand only (not in main pipeline).
    """
    for route in routes:
        coords = get_flat_route_coords(route)
        route["safe_spots"] = get_safe_spots_along_route(coords)
    return routes


def get_route_safe_spots_js(route: dict) -> str:
    """
    Fetch safe spots for a single route and return Leaflet JS string.
    Called by /api/safe-spots/route for on-demand toggle loading.
    """
    coords = get_flat_route_coords(route)
    spots  = get_safe_spots_along_route(coords)
    return get_safe_spots_js(spots)


def get_spots_for_coords(coord_list: list, radius_m: int = 600) -> list:
    """
    Fetch safe spots near a list of [lat, lon] sample points in parallel.
    Used by /api/safe-spots/batch for client-driven progressive loading.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    if not coord_list:
        return []
    seen_ids  = set()
    all_spots = []
    with ThreadPoolExecutor(max_workers=min(len(coord_list), 10)) as pool:
        futures = {pool.submit(get_safe_spots_near, pt[0], pt[1], radius_m): pt
                   for pt in coord_list}
        for fut in as_completed(futures):
            try:
                spots = fut.result()
            except Exception:
                spots = []
            for s in spots:
                if s["id"] not in seen_ids:
                    seen_ids.add(s["id"])
                    all_spots.append(s)
    all_spots.sort(key=lambda s: (s["priority"], s["dist_m"]))
    return all_spots   # no cap — caller (frontend cluster) handles rendering limits


def get_safe_spots_js(spots: list) -> str:
    """
    Generate JavaScript to render safe spot markers on the Leaflet map.
    Injected into the page as a <script> block via Jinja: {{ safe_spots_js | safe }}
    """
    if not spots:
        return ""

    lines = ["(function() {",
             "  if (typeof map === 'undefined') return;",
             "  var safeSpotGroup = L.featureGroup().addTo(map);",
             "  window._safeSpotGroup = safeSpotGroup;"]

    for s in spots:
        name_esc  = s['name'].replace("'", "\\'").replace('"', '&quot;')
        addr_esc  = s['address'].replace("'", "\\'")
        open24    = "Yes" if s["open_24h"] else "Unknown"
        lat       = s['lat']
        lon       = s['lon']
        color     = s['color']
        icon      = s['icon']
        label     = s['label']
        div_style = (
            f"background:{color};color:#fff;"
            "border-radius:50%;width:26px;height:26px;display:flex;"
            "align-items:center;justify-content:center;font-size:14px;"
            "box-shadow:0 2px 6px rgba(0,0,0,0.4);border:2px solid rgba(255,255,255,0.8);"
        )
        marker_js = (
            f"  L.marker([{lat},{lon}], {{"
            f"    icon: L.divIcon({{"
            f"      className: '',"
            f"      html: '<div style=\"{div_style}\">{icon}</div>',"
            f"      iconSize:[26,26],iconAnchor:[13,13]"
            f"    }}),"
            f"    pane:'hazardMarkers',zIndexOffset:800"
            f"  }}).addTo(safeSpotGroup)"
            f"  .bindPopup('<b>{name_esc}</b><br>{label}<br>"
            f"<small>{addr_esc}</small><br>"
            f"<span style=\"color:#27ae60;font-size:11px;\">&#10003; Safe refuge point</span><br>"
            f"<span style=\"font-size:10px;color:#888;\">Open 24h: {open24}</span>')"
            f"  .bindTooltip('{icon} {name_esc}');"
        )
        lines.append(marker_js)

    lines.append("})();")
    return "\n".join(lines)


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    R = 6371000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _build_address(tags: dict) -> str:
    parts = [
        tags.get("addr:housenumber", ""),
        tags.get("addr:street", ""),
        tags.get("addr:suburb", "") or tags.get("addr:city", ""),
    ]
    return ", ".join(p for p in parts if p).strip(", ") or "Address not available"