import requests
import time
import json
import math
import os

# ════════════════════════════════════════════════════════════════════════════
#  navigation.py  —  SafeRouteAI
#  Route calculation for all commuter types.
# ════════════════════════════════════════════════════════════════════════════

# ── 0. HARDCODED LOCATION ATLAS (Prevents HTTP 429 Rate Limits) ──────────────
# Common transport hubs in Metro Manila to avoid querying Nominatim repeatedly.
_KNOWN_LOCATIONS = {
    "lrt monumento station": (14.654, 120.983), "monumento": (14.654, 120.983),
    "baclaran church": (14.532, 120.993), "baclaran": (14.532, 120.993),
    "araneta center": (14.619, 121.053), "cubao": (14.619, 121.053),
    "sm fairview": (14.734, 121.057), "fairview": (14.734, 121.057),
    "quiapo church": (14.598, 120.983), "quiapo": (14.598, 120.983),
    "novaliches public market": (14.723, 121.038),
    "divisoria market": (14.603, 120.968), "divisoria": (14.603, 120.968),
    "alabang town center": (14.425, 121.027), "alabang": (14.417, 121.043),
    "pitx terminal": (14.511, 120.992), "pitx": (14.511, 120.992),
    "edsa-taft": (14.537, 121.001), "pasay rotunda": (14.537, 121.001),
    "antipolo cathedral": (14.587, 121.176), "antipolo": (14.587, 121.176),
    "marikina public market": (14.633, 121.096),
    "las pinas city hall": (14.446, 120.993),
    "valenzuela city hall": (14.695, 120.973),
    "bocaue public market": (14.796, 120.925),
    "valenzuela gateway complex": (14.712, 120.989), "vgc": (14.712, 120.989),
    "malanday terminal": (14.715, 120.954),
    "sm mall of asia": (14.535, 120.982), "moa": (14.535, 120.982),
    "sm north edsa": (14.656, 121.028), "trinoma": (14.653, 121.033),
    "market! market!": (14.549, 121.055), "bgc": (14.549, 121.055),
    "fti terminal": (14.511, 121.038),
    "navotas bus terminal": (14.647, 120.952),
    "ayala center": (14.550, 121.025), "ayala": (14.550, 121.025),
    "pacita complex": (14.345, 121.056),
    "starmall alabang": (14.416, 121.043),
    "tungkong mangga": (14.778, 121.072), "sjdm": (14.814, 121.045),
    "sucat interchange": (14.449, 121.047),
    "lawton plaza": (14.594, 120.980), "lawton": (14.594, 120.980),
    "taytay public market": (14.566, 121.135),
    "montalban town center": (14.733, 121.125),
    "pala-pala": (14.296, 120.958),
    "sm megamall": (14.584, 121.056),
    "robinsons place antipolo": (14.591, 121.173),
    "glorietta": (14.551, 121.025),
    "naia terminal 3": (14.517, 121.017),
    "meycauayan public market": (14.736, 120.958),
    "malinta": (14.691, 120.967),
    "n. domingo street": (14.609, 121.028),
    "c.m. recto avenue": (14.603, 120.985),
    "aurora boulevard": (14.620, 121.050),
    "quezon boulevard": (14.600, 120.984),
    "j.p. rizal avenue": (14.566, 121.045),
    "taft avenue": (14.570, 120.990),
    "kamuning road": (14.629, 121.042),
    "rizal avenue extension": (14.650, 120.983),
    "susano road": (14.745, 121.039),
    "dr. jose n. rodriguez avenue": (14.768, 121.065),
    "radial road 10": (14.630, 120.955),
    "karuhatan road": (14.693, 120.972),
    "shaw boulevard": (14.587, 121.045),
    "mall of asia arena": (14.533, 120.984),
    "commonwealth avenue": (14.666, 121.066),
}

# ── 1. Overpass API retry wrapper ────────────────────────────────────────────

_OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]

def _overpass_query(query, max_retries=5, timeout=30):
    headers = {'User-Agent': 'SafeRoute/1.0'}
    attempt = 0
    while attempt < max_retries:
        endpoint = _OVERPASS_ENDPOINTS[attempt % len(_OVERPASS_ENDPOINTS)]
        try:
            # print(f"[overpass] Attempt {attempt + 1}/{max_retries} -> {endpoint}")
            resp = requests.post(endpoint, data=query, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            pass # Silent fail to next retry
        attempt += 1
        if attempt < max_retries:
            time.sleep(2 * attempt)
    return None


# ── 2. General helpers ────────────────────────────────────────────────────────

_GEOCODE_CACHE = {}
_OSRM_DISTANCE_CACHE = {}  # Cache for OSRM walking distances

def geocode_location(address):
    """Geocode origin/dest user input safely."""
    # 1. Check Memory Cache
    if address in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[address]

    # 2. Check Hardcoded Atlas (Fuzzy Match)
    clean_addr = address.lower().strip()
    for key, coords in _KNOWN_LOCATIONS.items():
        if key in clean_addr:
            _GEOCODE_CACHE[address] = (coords[1], coords[0]) # Lon, Lat
            return (coords[1], coords[0])

    # 3. Coordinate String Check
    if "," in address:
        try:
            parts = [x.strip() for x in address.split(',')]
            lat, lon = float(parts[0]), float(parts[1])
            # Ensure Lat/Lon order (PH is approx Lat 14, Lon 121)
            result = (lon, lat) if lon > 100 else (lat, lon)
            _GEOCODE_CACHE[address] = result
            return result
        except (ValueError, TypeError):
            pass
            
    # 4. Nominatim (Last Resort)
    time.sleep(1.1) 
    url = (f"https://nominatim.openstreetmap.org/search"
           f"?q={requests.utils.quote(address)}&format=json&limit=1&countrycodes=ph")
    try:
        headers = {'User-Agent': 'SafeRouteAI/1.0 (contact@saferoute.local)'}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            resp = response.json()
            if resp:
                result = float(resp[0]['lon']), float(resp[0]['lat'])
                _GEOCODE_CACHE[address] = result
                return result
    except Exception:
        pass
    
    _GEOCODE_CACHE[address] = (None, None)
    return None, None


def _dist_sq(lat1, lon1, lat2, lon2):
    return (lat1 - lat2) ** 2 + (lon1 - lon2) ** 2


def _closest_idx(line, lat, lon):
    return min(range(len(line)), key=lambda i: _dist_sq(line[i][0], line[i][1], lat, lon))


def _haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres between two lat/lon points."""
    R = 6_371_000
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lon2 - lon1)
    a = math.sin(dφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ════════════════════════════════════════════════════════════════════════════
# CRITICAL FIX: OSRM Walking Distance Functions
# These replace haversine for walk-to-station distance calculations
# Haversine (air distance) was causing 800m → 3km walking mismatches
# OSRM queries actual street networks from OpenStreetMap
# ════════════════════════════════════════════════════════════════════════════

def _osrm_walk_distance(lat1, lon1, lat2, lon2, timeout=5):
    """
    Get actual street walking distance using OSRM.
    Returns distance in meters, or None if OSRM fails.
    """
    try:
        url = (
            f"https://router.project-osrm.org/route/v1/foot/"
            f"{lon1},{lat1};{lon2},{lat2}?overview=false"
        )
        resp = requests.get(url, timeout=timeout).json()
        if resp.get('code') == 'Ok' and resp.get('routes'):
            distance = resp['routes'][0].get('distance')
            if distance:
                return int(distance)
        return None
    except Exception:
        return None


def _osrm_walk_distance_cached(lat1, lon1, lat2, lon2):
    """
    Cached version of OSRM walking distance to reduce API calls.
    Key is rounded to 4 decimals (~11m precision).
    """
    key = (round(lat1, 4), round(lon1, 4), round(lat2, 4), round(lon2, 4))
    if key in _OSRM_DISTANCE_CACHE:
        return _OSRM_DISTANCE_CACHE[key]
    result = _osrm_walk_distance(lat1, lon1, lat2, lon2)
    _OSRM_DISTANCE_CACHE[key] = result
    return result


def _chain_one(segments, start_idx, used):
    ep = {}
    for i, seg in enumerate(segments):
        ep[tuple(seg[0])]  = ('start', i)
        ep[tuple(seg[-1])] = ('end',   i)

    path = list(segments[start_idx])
    used.add(start_idx)

    while True:
        grew = False
        m = ep.get(tuple(path[-1]))
        if m and m[1] not in used:
            side, idx = m
            s = segments[idx]
            path.extend(s[1:] if side == 'start' else list(reversed(s[:-1])))
            used.add(idx)
            grew = True
        if not grew:
            m = ep.get(tuple(path[0]))
            if m and m[1] not in used:
                side, idx = m
                s = segments[idx]
                path = (s[:-1] + path) if side == 'end' else (list(reversed(s[1:])) + path)
                used.add(idx)
                grew = True
        if not grew:
            break
    return path


def _chain_all(segments):
    used = set()
    components = []
    for i in range(len(segments)):
        if i not in used:
            components.append(_chain_one(segments, i, used))
    return components


# ── 3. OSM name resolver ──────────────────────────────────────────────────────

def _osm_name(user_input):
    key = user_input.lower().replace(" ", "").replace("-", "")
    return {
        "lrt1":   "Line 1", "line1":  "Line 1",
        "lrt2":   "Line 2", "line2":  "Line 2",
        "mrt3":   "Line 3", "mrt":    "Line 3", "line3": "Line 3",
        "mrt7":   "Line 7", "line7":  "Line 7",
        "pnr":    "PNR",
        "subway": "Metro Manila Subway",
    }.get(key, user_input)


# ════════════════════════════════════════════════════════════════════════════
#  4. !! TRAIN ROUTING — DO NOT MODIFY !!
# ════════════════════════════════════════════════════════════════════════════

_STOP_ROLES           = {'stop', 'stop_entry_only', 'stop_exit_only'}
_STATION_RAILWAY_TAGS = {'station', 'stop', 'halt', 'tram_stop', 'subway_entrance'}


def _extract_relation_data(relation):
    stops = []
    ways  = []
    seen_stop_refs = set()

    for member in relation.get('members', []):
        mtype = member.get('type')
        role  = member.get('role', '')

        if mtype == 'node':
            tags    = member.get('tags', {})
            is_stop = (
                role in _STOP_ROLES or
                tags.get('railway') in _STATION_RAILWAY_TAGS or
                tags.get('public_transport') in ('stop_position', 'station')
            )
            if role == 'platform' or tags.get('public_transport') == 'platform':
                continue
            ref = member.get('ref') or f"{member.get('lat')},{member.get('lon')}"
            if is_stop and ref not in seen_stop_refs:
                seen_stop_refs.add(ref)
                station_name = (
                    tags.get('name') or tags.get('name:en') or tags.get('ref') or 'Station'
                )
                stops.append({'lat': member['lat'], 'lon': member['lon'], 'name': station_name})

        elif mtype == 'way' and 'geometry' in member:
            ways.append([[pt['lat'], pt['lon']] for pt in member['geometry']])

    return stops, ways


def get_osm_railway_geometry(user_input, orig_lat, orig_lon, dest_lat, dest_lon):
    name = _osm_name(user_input)
    query = f"""
[out:json][timeout:35];
(
  relation["route"~"rail|light_rail|subway"]["name"~"{name}",i](14.2,120.9,14.8,121.2);
  relation["route"~"rail|light_rail|subway"]["ref"~"{name}",i](14.2,120.9,14.8,121.2);
);
out geom;
"""
    data = _overpass_query(query)
    if not data: return None

    relations = [el for el in data.get('elements', []) if el.get('type') == 'relation']
    if not relations: return None

    candidates = []
    all_ways   = []
    for rel in relations:
        stops, ways = _extract_relation_data(rel)
        all_ways.extend(ways)
        if len(stops) >= 2:
            candidates.append((stops, ways, rel.get('tags', {})))

    if not candidates: return None

    def score_candidate(stops):
        o_d = min(_dist_sq(s['lat'], s['lon'], orig_lat, orig_lon) for s in stops)
        d_d = min(_dist_sq(s['lat'], s['lon'], dest_lat, dest_lon) for s in stops)
        return o_d + d_d

    best_stops, _, _ = min(candidates, key=lambda c: score_candidate(c[0]))

    seen_keys   = set()
    unique_ways = []
    for seg in all_ways:
        key  = (round(seg[0][0], 5), round(seg[0][1], 5),
                round(seg[-1][0], 5), round(seg[-1][1], 5))
        rkey = (key[2], key[3], key[0], key[1])
        if key not in seen_keys and rkey not in seen_keys:
            seen_keys.add(key)
            unique_ways.append(seg)

    def nearest_stop_idx(lat, lon, stops):
        return min(range(len(stops)),
                   key=lambda i: _dist_sq(stops[i]['lat'], stops[i]['lon'], lat, lon))

    orig_si = nearest_stop_idx(orig_lat, orig_lon, best_stops)
    dest_si = nearest_stop_idx(dest_lat, dest_lon, best_stops)

    if orig_si == dest_si: return None

    si, ei     = min(orig_si, dest_si), max(orig_si, dest_si)
    route_stops = best_stops[si: ei + 1]

    track_segments = []
    if unique_ways:
        components = _chain_all(unique_ways)
        main_track = max(components, key=len)

        if len(main_track) >= 2:
            def snap_track(lat, lon):
                return min(range(len(main_track)),
                           key=lambda i: _dist_sq(main_track[i][0], main_track[i][1], lat, lon))

            t_start = snap_track(route_stops[0]['lat'],  route_stops[0]['lon'])
            t_end   = snap_track(route_stops[-1]['lat'], route_stops[-1]['lon'])
            ts, te  = min(t_start, t_end), max(t_start, t_end)
            trimmed = main_track[ts: te + 1]
            if len(trimmed) >= 2:
                track_segments.append(trimmed)

    return {'track_segments': track_segments, 'stations': route_stops}


# ── 5. Road / Bus routing ─────────────────────────────────────────────────────

_OSRM_BASE    = "https://router.project-osrm.org/route/v1/driving"
_ROUTE_COLORS = {
    "car":     ["#3498db", "#1a6fa3", "#0e3d5c"],
    "jeepney": ["#e67e22", "#d35400", "#a04000"],
    "bus":     ["#27ae60", "#1e8449", "#145a32"],
}


def _osrm_road_route(orig_lon, orig_lat, dest_lon, dest_lat, mode_label, colors):
    url = (
        f"{_OSRM_BASE}/{orig_lon},{orig_lat};{dest_lon},{dest_lat}"
        f"?overview=full&geometries=geojson&alternatives=3&steps=true"
    )
    try:
        r = requests.get(url, headers={'User-Agent': 'SafeRouteAI'}, timeout=10).json()
        if r.get("code") != "Ok": return {"error": "Could not calculate road route."}
    except Exception:
        return {"error": "Routing server is currently unavailable."}

    routes = []
    for i, route in enumerate(r.get("routes", [])[:3]):
        coords = [[pt[1], pt[0]] for pt in route["geometry"]["coordinates"]]
        routes.append({
            "id":              i,
            "name":            f"{mode_label} Route {i + 1}",
            "type":            "road",
            "color":           colors[i % len(colors)],
            "time":            f"{int(route['duration'] / 60)} mins",
            "distance":        f"{round(route['distance'] / 1000, 1)} km",
            "coords":          coords,
            "segments":        [],
            "stations":        [],
            "safety_score":    80,
            "hazards_flagged": "Clear",
        })
    return {"routes": routes}


def get_car_route(orig_lon, orig_lat, dest_lon, dest_lat):
    return _osrm_road_route(orig_lon, orig_lat, dest_lon, dest_lat, "Car", _ROUTE_COLORS["car"])


def get_motorcycle_route(orig_lon, orig_lat, dest_lon, dest_lat):
    colors = ["#8e44ad", "#9b59b6", "#af7ac5"]
    return _osrm_road_route(orig_lon, orig_lat, dest_lon, dest_lat, "Motorcycle", colors)

def _fetch_osrm_foot(orig_lon, orig_lat, dest_lon, dest_lat):
    headers = {'User-Agent': 'SafeRouteAI/1.0 (contact@saferoute.local)'}
    
    # 1. Try FOSSGIS first
    url_fossgis = f"https://routing.openstreetmap.de/routed-foot/route/v1/driving/{orig_lon},{orig_lat};{dest_lon},{dest_lat}?overview=full&geometries=geojson&alternatives=3"
    try:
        r = requests.get(url_fossgis, headers=headers, timeout=6).json()
        if r.get('code') == 'Ok' and r.get('routes'): return r
    except Exception: pass

    # 2. Fallback to standard OSRM foot
    url_standard = f"https://router.project-osrm.org/route/v1/foot/{orig_lon},{orig_lat};{dest_lon},{dest_lat}?overview=full&geometries=geojson&alternatives=3"
    try:
        r = requests.get(url_standard, headers=headers, timeout=6).json()
        if r.get('code') == 'Ok' and r.get('routes'): return r
    except Exception: pass

    return None

def get_walk_route(orig_lon, orig_lat, dest_lon, dest_lat):
    r = _fetch_osrm_foot(orig_lon, orig_lat, dest_lon, dest_lat)
    if r:
        walk_colors = ["#2ecc71", "#27ae60", "#1abc9c"]
        walk_names  = ["Walking Route", "Alternative Walk", "Scenic Walk"]
        routes_out  = []
        for i, route in enumerate(r["routes"][:3]):
            coords = [[pt[1], pt[0]] for pt in route["geometry"]["coordinates"]]
            routes_out.append({
                "id":              i,
                "name":            walk_names[i] if i < len(walk_names) else f"Walk Option {i+1}",
                "type":            "walk",
                "color":           walk_colors[i] if i < len(walk_colors) else "#2ecc71",
                "time":            f"{int(route['duration'] / 60)} mins",
                "distance":        f"{round(route['distance'] / 1000, 1)} km",
                "coords":          coords,
                "segments":        [],
                "stations":        [],
                "safety_score":    90,
                "hazards_flagged": "Pedestrian paths only",
            })
        if routes_out:
            routes_out[0]["mode_label"] = "Only Route" if len(routes_out) == 1 else "Fastest"
            if len(routes_out) > 1: routes_out[1]["mode_label"] = "Alternative"
            if len(routes_out) > 2: routes_out[2]["mode_label"] = "Scenic"
        return {"routes": routes_out}
    return {"error": "Could not calculate walking route."}


# ── Bus Routing ───────────────────────────────────────────────────────────────

_BUS_OSM_CACHE   = {}
_BUS_POLY_CACHE  = {}
_BUS_ROUTES_DATA = None

def _load_bus_json():
    global _BUS_ROUTES_DATA
    if _BUS_ROUTES_DATA is not None: return _BUS_ROUTES_DATA
    base = os.path.dirname(os.path.abspath(__file__))
    cwd  = os.getcwd()
    for path in [os.path.join(base, 'map_transit', 'bus.json'), os.path.join(base, 'bus.json'), os.path.join(cwd, 'bus.json')]:
        if not os.path.exists(path): continue
        try:
            data = json.loads(open(path, encoding='utf-8').read().strip())
            _BUS_ROUTES_DATA = data if isinstance(data, list) else [data]
            return _BUS_ROUTES_DATA
        except Exception: pass
    _BUS_ROUTES_DATA = []
    return []

_BUS_GEOCODE_CACHE = {}

def _geocode_bus_endpoint(name):
    # 1. Check Atlas first
    clean = name.lower().strip()
    for k, v in _KNOWN_LOCATIONS.items():
        if k in clean: return v[0], v[1]

    # 2. Check Cache
    if name in _BUS_GEOCODE_CACHE: return _BUS_GEOCODE_CACHE[name]
        
    # 3. Nominatim (Rarely reached now)
    time.sleep(1.1)
    try:
        headers = {'User-Agent': 'SafeRouteAI/1.0'}
        response = requests.get(
            'https://nominatim.openstreetmap.org/search',
            params={'q': name, 'format': 'json', 'limit': 1, 'countrycodes': 'ph'},
            headers=headers, timeout=5
        )
        if response.status_code == 200:
            resp = response.json()
            if resp:
                lat, lon = float(resp[0]['lat']), float(resp[0]['lon'])
                _BUS_GEOCODE_CACHE[name] = (lat, lon)
                return lat, lon
    except Exception: pass
    _BUS_GEOCODE_CACHE[name] = (None, None)
    return None, None


def _resolve_json_bus_route(jroute):
    if '_resolved' in jroute: return jroute['_resolved']
    resolved = []
    for road in jroute.get('roads', []):
        name = road if isinstance(road, str) else road.get('name', '')
        lat, lon = _geocode_bus_endpoint(name)
        if lat is not None:
            resolved.append({'name': name, 'lat': lat, 'lon': lon})
    jroute['_resolved'] = resolved
    return resolved


def _json_bus_is_near(jroute, orig_lat, orig_lon, dest_lat, dest_lon, threshold_m=6000):
    pts = _resolve_json_bus_route(jroute)
    if len(pts) < 2: return False, None

    def _check(ordered):
        if not any(_haversine_m(orig_lat, orig_lon, p['lat'], p['lon']) <= threshold_m for p in ordered): return False
        if not any(_haversine_m(dest_lat, dest_lon, p['lat'], p['lon']) <= threshold_m for p in ordered): return False
        d_o_first = _haversine_m(orig_lat, orig_lon, ordered[0]['lat'], ordered[0]['lon'])
        d_o_last  = _haversine_m(orig_lat, orig_lon, ordered[-1]['lat'], ordered[-1]['lon'])
        d_d_first = _haversine_m(dest_lat, dest_lon, ordered[0]['lat'], ordered[0]['lon'])
        d_d_last  = _haversine_m(dest_lat, dest_lon, ordered[-1]['lat'], ordered[-1]['lon'])
        return d_o_first < d_o_last and d_d_last < d_d_first

    if _check(pts): return True, True
    if _check(list(reversed(pts))): return True, False
    return False, None


def _build_json_bus_polyline(jroute, going_fwd=True):
    name      = jroute['route_name']
    cache_key = f"json:{name}:{'fwd' if going_fwd else 'rev'}"
    if cache_key in _BUS_POLY_CACHE: return _BUS_POLY_CACHE[cache_key]

    pts     = _resolve_json_bus_route(jroute)
    ordered = pts if going_fwd else list(reversed(pts))
    if len(ordered) < 2: return None

    wp_str     = ';'.join(f"{p['lon']},{p['lat']}" for p in ordered)
    approaches = ';'.join('curb' for _ in ordered)
    url = (
        f"{_OSRM_BASE}/{wp_str}"
        f"?overview=full&geometries=geojson"
        f"&continue_straight=true&approaches={approaches}"
    )
    try:
        r = requests.get(url, headers={'User-Agent': 'SafeRouteAI'}, timeout=15).json()
        if r.get('code') == 'Ok' and r.get('routes'):
            rt       = r['routes'][0]
            polyline = [[pt[1], pt[0]] for pt in rt['geometry']['coordinates']]
            result   = {'polyline': polyline, 'stations': ordered,
                        'dur': rt['duration'], 'dist': rt['distance'], 'source': 'json'}
            _BUS_POLY_CACHE[cache_key] = result
            return result
    except Exception: pass
    _BUS_POLY_CACHE[cache_key] = None
    return None


def get_bus_route(orig_lon, orig_lat, dest_lon, dest_lat):
    color = "#27ae60"
    best = None
    
    for jroute in _load_bus_json():
        passes, going_fwd = _json_bus_is_near(jroute, orig_lat, orig_lon, dest_lat, dest_lon)
        if not passes: continue
            
        built = _build_json_bus_polyline(jroute, going_fwd)
        if not built: continue
            
        polyline = built['polyline']
        if len(polyline) < 2: continue

        board_idx, board_lat, board_lon, board_m   = _snap_to_polyline(polyline, orig_lat, orig_lon)
        alight_idx, alight_lat, alight_lon, alght_m = _snap_to_polyline(polyline, dest_lat, dest_lon)
        
        if board_idx >= alight_idx: continue
        if board_m > 3000 or alght_m > 3000: continue

        bus_seg    = polyline[board_idx: alight_idx + 1]
        total_walk = board_m + alght_m
        
        cand = {
            'name': jroute['route_name'], 'built': built,
            'board_lat': board_lat, 'board_lon': board_lon, 'board_m': board_m,
            'alight_lat': alight_lat, 'alight_lon': alight_lon, 'alight_m': alght_m,
            'bus_seg': bus_seg, 'bus_dist': _polyline_distance_m(bus_seg),
            'total_walk_m': total_walk,
        }
        
        if best is None or total_walk < best['total_walk_m']:
            best = cand

    if best is None:
        return {"error": "No bus route found near your origin and destination."}

    built   = best['built']
    bus_seg = best['bus_seg']

    w_board_seg, w_board_dist, w_board_dur = _walk_leg(
        orig_lat, orig_lon, best['board_lat'], best['board_lon'], "Walk to bus stop")
    
    w_alight_seg, w_alight_dist, w_alight_dur = _walk_leg(
        best['alight_lat'], best['alight_lon'], dest_lat, dest_lon, "Walk to destination")

    bus_mins   = max(1, int(best['bus_dist'] / (20_000 / 60)))
    walk_mins  = int(((w_board_dur or 0) + (w_alight_dur or 0)) / 60)
    total_mins = bus_mins + walk_mins
    total_km   = round((best['bus_dist'] + (w_board_dist or 0) + (w_alight_dist or 0)) / 1_000, 1)

    segments = []
    if w_board_seg:
        segments.append(w_board_seg)
    segments.append({'type': 'bus', 'coords': bus_seg, 'color': color,
                     'label': best['name']})
    if w_alight_seg:
        segments.append(w_alight_seg)

    return {
        'id': 0, 'name': best['name'], 'type': 'bus', 'color': color,
        'time': f"~{total_mins} mins", 'distance': f"{total_km} km",
        'coords': bus_seg, 'segments': segments, 'stations': built['stations'],
        'board_point': {'lat': best['board_lat'], 'lon': best['board_lon']},
        'alight_point': {'lat': best['alight_lat'], 'lon': best['alight_lon']},
        'walk_board_m': int(best['board_m']), 'walk_alight_m': int(best['alight_m']),
        'safety_score': 70, 'hazards_flagged': "Source: JSON database",
    }

# ── Jeepney Routing ──────────────────────────────────────────────────────────

_JEEPNEY_ROUTES_DATA = None
_JEEPNEY_POLY_CACHE  = {}

def _load_jeepney_data():
    global _JEEPNEY_ROUTES_DATA
    if _JEEPNEY_ROUTES_DATA is not None: return _JEEPNEY_ROUTES_DATA
    base = os.path.dirname(os.path.abspath(__file__))
    cwd  = os.getcwd()
    for path in [os.path.join(base, 'map_transit', 'jeepney.json'), os.path.join(base, 'jeepney.json'), os.path.join(cwd, 'jeepney.json')]:
        if not os.path.exists(path): continue
        try:
            raw = open(path, encoding='utf-8').read().strip()
            if not raw.startswith('['): raw = '[' + raw
            data = json.loads(raw)
            _JEEPNEY_ROUTES_DATA = data if isinstance(data, list) else [data]
            return _JEEPNEY_ROUTES_DATA
        except Exception: pass
    _JEEPNEY_ROUTES_DATA = []
    return []

_ROAD_GEOCODE_CACHE = {}

def _geocode_road(road_name):
    # 1. Check Atlas
    clean = road_name.lower().strip()
    for k, v in _KNOWN_LOCATIONS.items():
        if k in clean: return v[0], v[1]

    # 2. Check Cache
    if road_name in _ROAD_GEOCODE_CACHE: return _ROAD_GEOCODE_CACHE[road_name]

    # 3. Nominatim
    time.sleep(1.1)
    params = {'q': road_name, 'format': 'json', 'limit': 1, 'countrycodes': 'ph', 'bounded': 1, 'viewbox': '120.85,14.35,121.20,14.85'}
    try:
        headers = {'User-Agent': 'SafeRouteAI/1.0'}
        response = requests.get('https://nominatim.openstreetmap.org/search', params=params, headers=headers, timeout=5)
        if response.status_code == 200:
            resp = response.json()
            if resp:
                lat, lon = float(resp[0]['lat']), float(resp[0]['lon'])
                _ROAD_GEOCODE_CACHE[road_name] = (lat, lon)
                return lat, lon
    except Exception: pass
    _ROAD_GEOCODE_CACHE[road_name] = (None, None)
    return None, None


def _resolve_jeepney_route(jroute):
    if '_resolved' in jroute: return jroute['_resolved']
    resolved = []
    for road in jroute.get('roads', []):
        if isinstance(road, str):
            lat, lon = _geocode_road(road)
            if lat is not None: resolved.append({'name': road, 'lat': lat, 'lon': lon})
        elif isinstance(road, dict):
            lat = road.get('lat') or (road.get('fwd') or {}).get('lat')
            lon = road.get('lng') or road.get('lon') or (road.get('fwd') or {}).get('lng')
            if lat and lon: resolved.append({'name': road.get('name', 'Road'), 'lat': lat, 'lon': lon})
    jroute['_resolved'] = resolved
    return resolved


def _route_is_near(jroute, orig_lat, orig_lon, dest_lat, dest_lon, threshold_m=5000):
    pts = _resolve_jeepney_route(jroute)
    if len(pts) < 2: return False, None

    def _check(ordered_pts):
        orig_near = any(_haversine_m(orig_lat, orig_lon, p['lat'], p['lon']) <= threshold_m for p in ordered_pts)
        dest_near = any(_haversine_m(dest_lat, dest_lon, p['lat'], p['lon']) <= threshold_m for p in ordered_pts)
        if not (orig_near and dest_near): return False
        d_o_first = _haversine_m(orig_lat, orig_lon, ordered_pts[0]['lat'], ordered_pts[0]['lon'])
        d_o_last  = _haversine_m(orig_lat, orig_lon, ordered_pts[-1]['lat'], ordered_pts[-1]['lon'])
        d_d_first = _haversine_m(dest_lat, dest_lon, ordered_pts[0]['lat'], ordered_pts[0]['lon'])
        d_d_last  = _haversine_m(dest_lat, dest_lon, ordered_pts[-1]['lat'], ordered_pts[-1]['lon'])
        return d_o_first < d_o_last and d_d_last < d_d_first

    if _check(pts): return True, True
    if _check(list(reversed(pts))): return True, False
    return False, None


def _build_jeepney_polyline(jroute, going_fwd=True):
    name      = jroute['route_name']
    cache_key = f"{name}:{'fwd' if going_fwd else 'rev'}"
    if cache_key in _JEEPNEY_POLY_CACHE: return _JEEPNEY_POLY_CACHE[cache_key]

    pts = _resolve_jeepney_route(jroute)
    if len(pts) < 2: return None

    ordered = pts if going_fwd else list(reversed(pts))
    wp_str     = ';'.join(f"{p['lon']},{p['lat']}" for p in ordered)
    approaches = ';'.join('curb' for _ in ordered)
    url = (
        f"{_OSRM_BASE}/{wp_str}"
        f"?overview=full&geometries=geojson"
        f"&continue_straight=true"
        f"&approaches={approaches}"
    )
    try:
        r = requests.get(url, headers={'User-Agent': 'SafeRouteAI'}, timeout=15).json()
        if r.get('code') == 'Ok' and r.get('routes'):
            rt       = r['routes'][0]
            polyline = [[pt[1], pt[0]] for pt in rt['geometry']['coordinates']]
            result   = {'polyline': polyline, 'stations': ordered, 'dur': rt['duration'], 'dist': rt['distance']}
            _JEEPNEY_POLY_CACHE[cache_key] = result
            return result
    except Exception: pass
    _JEEPNEY_POLY_CACHE[cache_key] = None
    return None


def _snap_to_polyline(polyline, lat, lon):
    best = min(range(len(polyline)), key=lambda i: _haversine_m(lat, lon, polyline[i][0], polyline[i][1]))
    return best, polyline[best][0], polyline[best][1], _haversine_m(lat, lon, polyline[best][0], polyline[best][1])


def _polyline_distance_m(polyline):
    return sum(_haversine_m(polyline[i][0], polyline[i][1], polyline[i + 1][0], polyline[i + 1][1]) for i in range(len(polyline) - 1))


def get_jeepney_route(orig_lon, orig_lat, dest_lon, dest_lat):
    all_routes = _load_jeepney_data()
    color      = "#e67e22"
    nearby = []
    for r in all_routes:
        passes, going_fwd = _route_is_near(r, orig_lat, orig_lon, dest_lat, dest_lon)
        if passes: nearby.append((r, going_fwd))

    if not nearby:
        return {"error": "No jeepney route found near your origin and destination."}

    best = None
    for jroute, going_fwd in nearby:
        built = _build_jeepney_polyline(jroute, going_fwd)
        if not built: continue

        polyline = built['polyline']
        if len(polyline) < 2: continue

        board_idx,  board_lat,  board_lon,  board_m  = _snap_to_polyline(polyline, orig_lat, orig_lon)
        alight_idx, alight_lat, alight_lon, alght_m  = _snap_to_polyline(polyline, dest_lat, dest_lon)

        if board_idx >= alight_idx: continue
        if board_m > 3000 or alght_m > 3000: continue

        jeepney_seg = polyline[board_idx: alight_idx + 1]
        jeep_dist_m = _polyline_distance_m(jeepney_seg)
        total_walk  = board_m + alght_m

        route_stops = []
        for stop in built['stations']:
            si, _, _, _ = _snap_to_polyline(polyline, stop['lat'], stop['lon'])
            if board_idx <= si <= alight_idx:
                route_stops.append({**stop, '_idx': si})
        route_stops.sort(key=lambda s: s['_idx'])
        for s in route_stops: s.pop('_idx', None)

        cand = {
            'jroute': jroute, 'board_lat': board_lat, 'board_lon': board_lon, 'board_m': board_m,
            'alight_lat': alight_lat, 'alight_lon': alight_lon, 'alight_m': alght_m,
            'jeepney_seg': jeepney_seg, 'jeep_dist_m': jeep_dist_m, 'total_walk_m': total_walk,
            'route_stops': route_stops,
        }
        if best is None or total_walk < best['total_walk_m']: best = cand

    if best is None:
        return {"error": "No jeepney route found near your origin and destination."}

    jroute      = best['jroute']
    jeepney_seg = best['jeepney_seg']

    w_board_seg, w_board_dist, w_board_dur = _walk_leg(
        orig_lat, orig_lon, best['board_lat'], best['board_lon'], "Walk to jeepney stop"
    )
    
    w_alight_seg, w_alight_dist, w_alight_dur = _walk_leg(
        best['alight_lat'], best['alight_lon'], dest_lat, dest_lon, "Walk to destination"
    )

    jeep_mins  = max(1, int(best['jeep_dist_m'] / (15_000 / 60)))
    walk_mins  = int(((w_board_dur or 0) + (w_alight_dur or 0)) / 60)
    total_mins = jeep_mins + walk_mins
    total_km   = round((best['jeep_dist_m'] + (w_board_dist or 0) + (w_alight_dist or 0)) / 1_000, 1)

    segments = []
    if w_board_seg:
        segments.append(w_board_seg)
    segments.append({'type': 'jeepney', 'coords': jeepney_seg, 'color': color, 'label': jroute['route_name']})
    if w_alight_seg:
        segments.append(w_alight_seg)

    return {"routes": [{
        'id': 0, 'name': jroute['route_name'], 'type': 'jeepney', 'color': color,
        'time': f"~{total_mins} mins", 'distance': f"{total_km} km",
        'coords': jeepney_seg, 'segments': segments, 'stations': best['route_stops'],
        'board_point': {'lat': best['board_lat'], 'lon': best['board_lon']},
        'alight_point': {'lat': best['alight_lat'], 'lon': best['alight_lon']},
        'walk_board_m': int(best['board_m']), 'walk_alight_m': int(best['alight_m']),
        'safety_score': 75, 'hazards_flagged': 'Variable — mid-block stops',
    }]}


# ── Transit Planner ──────────────────────────────────────────────────────────

_TRAIN_META = {
    "lrt-1": {"color": "#27ae60", "label": "LRT-1", "subtitle": "Green Line",    "emoji": "🚇"},
    "lrt-2": {"color": "#2980b9", "label": "LRT-2", "subtitle": "Blue Line",     "emoji": "🚇"},
    "mrt-3": {"color": "#f39c12", "label": "MRT-3", "subtitle": "Yellow Line",   "emoji": "🚆"},
    "pnr":   {"color": "#8B4513", "label": "PNR",   "subtitle": "Commuter Rail", "emoji": "🚂"},
}
_LINE_CACHE = {}
_TRANSFERS = [
    {"from_line": "lrt-1", "from_station": "Doroteo Jose", "to_line": "lrt-2", "to_station": "Recto", "from_lat": 14.5997, "from_lon": 120.9842, "to_lat": 14.5994, "to_lon": 120.9858, "label": "Walk via CM Recto Ave footbridge (~5 min)", "est_min": 5},
    {"from_line": "lrt-1", "from_station": "EDSA", "to_line": "mrt-3", "to_station": "Taft Avenue", "from_lat": 14.5366, "from_lon": 121.0003, "to_lat": 14.5369, "to_lon": 121.0013, "label": "Walk via enclosed walkway (~3 min)", "est_min": 3},
    {"from_line": "lrt-2", "from_station": "Araneta Center-Cubao", "to_line": "mrt-3", "to_station": "Araneta Center-Cubao", "from_lat": 14.6235, "from_lon": 121.0534, "to_lat": 14.6226, "to_lon": 121.0528, "label": "Walk via Cubao interchange (~8 min)", "est_min": 8},
]

def _walk_leg(from_lat, from_lon, to_lat, to_lon, label):
    straight = _haversine_m(from_lat, from_lon, to_lat, to_lon)
    if straight < 5: return None, 0, 0
    if straight < 80:
        coords = [[from_lat, from_lon], [to_lat, to_lon]]
        return {'type': 'walk', 'coords': coords, 'color': '#7f8c8d', 'label': label}, straight, straight / 1.2
    r = _fetch_osrm_foot(from_lon, from_lat, to_lon, to_lat)
    if r:
        rt = r['routes'][0]
        if rt['distance'] > straight * 2.5 and straight > 50:
            coords = [[from_lat, from_lon], [to_lat, to_lon]]
            return {'type': 'walk', 'coords': coords, 'color': '#7f8c8d', 'label': label}, straight, straight / 1.2
        coords = [[p[1], p[0]] for p in rt['geometry']['coordinates']]
        return {'type': 'walk', 'coords': coords, 'color': '#7f8c8d', 'label': label}, rt['distance'], rt['duration']
    coords = [[from_lat, from_lon], [to_lat, to_lon]]
    return {'type': 'walk', 'coords': coords, 'color': '#7f8c8d', 'label': label}, straight, straight / 1.2

def _fetch_full_line(line_id):
    cached = _LINE_CACHE.get(line_id)
    if cached is not None: return cached
    name = _osm_name(line_id)
    query = f"""
[out:json][timeout:40];
(
  relation["route"~"rail|light_rail|subway"]["name"~"{name}",i](14.2,120.9,14.8,121.2);
  relation["route"~"rail|light_rail|subway"]["ref"~"{name}",i](14.2,120.9,14.8,121.2);
);
out geom;
"""
    data = _overpass_query(query, max_retries=3, timeout=40)
    if not data: return None, None
    relations = [el for el in data.get('elements', []) if el['type'] == 'relation']
    if not relations: return None, None
    best_rel = max(relations, key=lambda r: sum(1 for m in r.get('members',[]) if m.get('role', '') in _STOP_ROLES))
    stops, ways = _extract_relation_data(best_rel)
    if len(stops) < 2: return None, None
    _LINE_CACHE[line_id] = (stops, ways)
    return stops, ways

def _slice_line(all_stations, all_ways, orig_lat, orig_lon, dest_lat, dest_lon):
    if not all_stations or len(all_stations) < 2: return None
    orig_idx = min(range(len(all_stations)), key=lambda i: _dist_sq(all_stations[i]['lat'], all_stations[i]['lon'], orig_lat, orig_lon))
    dest_idx = min(range(len(all_stations)), key=lambda i: _dist_sq(all_stations[i]['lat'], all_stations[i]['lon'], dest_lat, dest_lon))
    if orig_idx == dest_idx: return None
    si, ei = min(orig_idx, dest_idx), max(orig_idx, dest_idx)
    sliced = all_stations[si:ei + 1]
    track_segments = []
    if all_ways:
        components = _chain_all(all_ways)
        main_track = max(components, key=len)
        if len(main_track) >= 2:
            t_start = _closest_idx(main_track, sliced[0]['lat'],  sliced[0]['lon'])
            t_end   = _closest_idx(main_track, sliced[-1]['lat'], sliced[-1]['lon'])
            ts, te  = min(t_start, t_end), max(t_start, t_end)
            trimmed = main_track[ts:te + 1]
            if len(trimmed) >= 2: track_segments.append(trimmed)
    if not track_segments: track_segments = [[[s['lat'], s['lon']] for s in sliced]]
    return {'stations': sliced, 'track_segments': track_segments}

def _connector_legs(from_lat, from_lon, to_lat, to_lon, label):
    dist_straight = _haversine_m(from_lat, from_lon, to_lat, to_lon)
    if dist_straight <= 1500:
        seg, d, t = _walk_leg(from_lat, from_lon, to_lat, to_lon, label)
        if seg: return [seg], d, t
        return [], dist_straight, dist_straight / 1.2
    try:
        jr = get_jeepney_route(from_lon, from_lat, to_lon, to_lat)
        if "error" not in jr and jr.get("routes"):
            r = jr["routes"][0]
            segs = r.get("segments", [])
            if segs:
                dist_total = 0.0
                for s in segs:
                    c = s.get("coords", [])
                    if len(c) >= 2: dist_total += _polyline_distance_m(c)
                try:
                    t_str = r.get("time", "").replace("~", "").replace(" mins", "").strip()
                    dur_total = int(t_str) * 60
                except Exception: dur_total = max(60, int(dist_total / 5))
                return segs, dist_total, dur_total
    except Exception: pass
    seg, d, t = _walk_leg(from_lat, from_lon, to_lat, to_lon, label)
    if seg: return [seg], d, t
    return [], dist_straight, dist_straight / 1.2

def _build_transit_card(line_id, train_data, meta, orig_lat, orig_lon, dest_lat, dest_lon, card_id, segments_override=None, name_override=None):
    meta = meta or _TRAIN_META.get(line_id, {"color": "#8e44ad", "label": line_id, "subtitle": "", "emoji": "🚇"})
    s_start = train_data['stations'][0]
    s_end = train_data['stations'][-1]
    if segments_override is not None:
        segments = segments_override
    else:
        segments = []
        in_segs, _, _ = _connector_legs(orig_lat, orig_lon, s_start['lat'], s_start['lon'], f"To {s_start['name']}")
        for s in in_segs: segments.append(s)
        track = train_data['track_segments']
        flat = [c for seg in track for c in seg]
        segments.append({'type': 'train', 'coords': track, 'flat': flat, 'color': meta['color'], 'label': meta['label'], 'stations': train_data['stations']})
        out_segs, _, _ = _connector_legs(s_end['lat'], s_end['lon'], dest_lat, dest_lon, "To destination")
        for s in out_segs: segments.append(s)
    all_coords = []
    for seg in segments:
        if seg['type'] == 'train': all_coords.extend(seg.get('flat') or [c for track in seg['coords'] for c in track])
        else: all_coords.extend(seg['coords'])
    t_mins = 0; t_dist_m = 0.0
    for seg in segments:
        if seg['type'] == 'train':
            d = sum(_polyline_distance_m(s) for s in seg['coords'])
            t_mins += max(1, int(d / (40_000 / 60)))
            t_dist_m += d
        else:
            coords = seg['coords']
            d = _polyline_distance_m(coords) if len(coords) >= 2 else 0
            t_mins += max(1, int(d / (1.2 * 60)))
            t_dist_m += d
    sc = len(train_data['stations'])
    return {
        "id": card_id, "name": name_override or meta['label'], "subtitle": meta.get('subtitle', ''),
        "type": "transit", "color": meta['color'], "emoji": meta.get('emoji', '🚇'),
        "time": f"~{t_mins} mins", "distance": f"{t_dist_m / 1000:.1f} km",
        "coords": all_coords, "segments": segments, "stations": train_data['stations'],
        "station_count": sc, "safety_score": 88, "hazards_flagged": f"{sc} stops · {s_start['name']} → {s_end['name']}",
    }

def _build_transfer_card(line_a, data_a, meta_a, line_b, data_b, meta_b, transfer, orig_lat, orig_lon, dest_lat, dest_lon, card_id):
    sa_start = data_a['stations'][0]
    sa_end = data_a['stations'][-1]
    sb_start = data_b['stations'][0]
    sb_end = data_b['stations'][-1]
    segments = []
    w_in, _, _ = _walk_leg(orig_lat, orig_lon, sa_start['lat'], sa_start['lon'], f"Walk to {sa_start['name']}")
    if w_in: segments.append(w_in)
    track_a = data_a['track_segments']
    flat_a = [c for seg in track_a for c in seg]
    segments.append({'type': 'train', 'coords': track_a, 'flat': flat_a, 'color': meta_a['color'], 'label': meta_a['label'], 'stations': data_a['stations']})
    w_xfer, _, _ = _walk_leg(sa_end['lat'], sa_end['lon'], sb_start['lat'], sb_start['lon'], transfer['label'])
    if w_xfer: segments.append(w_xfer)
    else: segments.append({'type': 'walk', 'coords': [[sa_end['lat'], sa_end['lon']], [sb_start['lat'], sb_start['lon']]], 'color': '#95a5a6', 'label': transfer['label']})
    track_b = data_b['track_segments']
    flat_b = [c for seg in track_b for c in seg]
    segments.append({'type': 'train', 'coords': track_b, 'flat': flat_b, 'color': meta_b['color'], 'label': meta_b['label'], 'stations': data_b['stations']})
    w_out, _, _ = _walk_leg(sb_end['lat'], sb_end['lon'], dest_lat, dest_lon, "Walk to destination")
    if w_out: segments.append(w_out)
    merged_data = {'stations': data_a['stations'] + data_b['stations'], 'track_segments': track_a + track_b}
    meta_combo = {**meta_a, 'label': f"{meta_a['label']} + {meta_b['label']}", 'subtitle': f"Transfer at {sa_end['name']} → {sb_start['name']}", 'emoji': '🔄'}
    return _build_transit_card(line_a, merged_data, meta_combo, orig_lat, orig_lon, dest_lat, dest_lon, card_id, segments_override=segments, name_override=f"{meta_a['label']} + {meta_b['label']}")

# ── Transit Metadata ─────────────────────────────────────────────────────────
_TRAIN_META = {
    "lrt-1": {"color": "#27ae60", "label": "LRT-1", "subtitle": "Green Line",    "emoji": "🚇"},
    "lrt-2": {"color": "#2980b9", "label": "LRT-2", "subtitle": "Blue Line",     "emoji": "🚇"},
    "mrt-3": {"color": "#f39c12", "label": "MRT-3", "subtitle": "Yellow Line",   "emoji": "🚆"},
    "pnr":   {"color": "#8B4513", "label": "PNR",   "subtitle": "Commuter Rail", "emoji": "🚂"},
}

# Standardized Transfer Nodes (Coordinates of actual interchanges)
_TRANSFERS = [
    {
        "id": "L1_L2_DJOSE",
        "from_line": "lrt-1", "to_line": "lrt-2",
        "from_station": "Doroteo Jose", "to_station": "Recto",
        "lat": 14.6000, "lon": 120.9850,
        "label": "Transfer via D. Jose-Recto Walkway"
    },
    {
        "id": "L1_M3_EDSA",
        "from_line": "lrt-1", "to_line": "mrt-3",
        "from_station": "EDSA", "to_station": "Taft Avenue",
        "lat": 14.5370, "lon": 121.0010,
        "label": "Transfer via EDSA-Taft Walkway"
    },
    {
        "id": "L2_M3_CUBAO",
        "from_line": "lrt-2", "to_line": "mrt-3",
        "from_station": "Araneta Center-Cubao", "to_station": "Araneta Center-Cubao",
        "lat": 14.6220, "lon": 121.0520,
        "label": "Transfer via Gateway-Farmers Walkway"
    }
]

# ── Transit Planner Overhaul ──────────────────────────────────────────────────

def plan_transit_journey(orig_lon, orig_lat, dest_lon, dest_lat):
    # CRITICAL FIX: Reduced from 800m haversine to 400m actual street walking
    # 800m haversine was causing users to walk 2-3km on streets
    MAX_WALK_TO_STATION = 400
    
    results = []
    card_id = 0
    
    # 1. Evaluate Direct Lines (No Transfers)
    direct_candidates = []
    for line_id in ["lrt-1", "lrt-2", "mrt-3"]:
        all_st, all_wy = _fetch_full_line(line_id)
        if not all_st: continue
        
        td = _slice_line(all_st, all_wy, orig_lat, orig_lon, dest_lat, dest_lon)
        if not td: continue
        
        # CRITICAL FIX: Use OSRM (real streets) instead of haversine (air distance)
        d_walk_start = _osrm_walk_distance_cached(orig_lat, orig_lon, td['stations'][0]['lat'], td['stations'][0]['lon'])
        d_walk_end = _osrm_walk_distance_cached(dest_lat, dest_lon, td['stations'][-1]['lat'], td['stations'][-1]['lon'])
        
        # Only include if both segments are within walking distance
        if (d_walk_start and d_walk_start <= MAX_WALK_TO_STATION and 
            d_walk_end and d_walk_end <= MAX_WALK_TO_STATION):
            direct_candidates.append({
                'type': 'direct', 'line_id': line_id, 'td': td, 
                'walk_dist': d_walk_start + d_walk_end, 
                'walk_start': d_walk_start,
                'walk_end': d_walk_end,
                'meta': _TRAIN_META[line_id]
            })

    # 2. Evaluate Transfer Lines (e.g., LRT-2 to LRT-1)
    transfer_candidates = []
    for xfer in _TRANSFERS:
        l1, l2 = xfer['from_line'], xfer['to_line']
        
        # Check Line A (Origin to Transfer Node)
        all_st_a, all_wy_a = _fetch_full_line(l1)
        td_a = _slice_line(all_st_a, all_wy_a, orig_lat, orig_lon, xfer['lat'], xfer['lon'])
        
        # Check Line B (Transfer Node to Destination)
        all_st_b, all_wy_b = _fetch_full_line(l2)
        td_b = _slice_line(all_st_b, all_wy_b, xfer['lat'], xfer['lon'], dest_lat, dest_lon)
        
        if td_a and td_b:
            # CRITICAL FIX: Use OSRM instead of haversine
            d_walk_start = _osrm_walk_distance_cached(orig_lat, orig_lon, td_a['stations'][0]['lat'], td_a['stations'][0]['lon'])
            d_walk_end = _osrm_walk_distance_cached(dest_lat, dest_lon, td_b['stations'][-1]['lat'], td_b['stations'][-1]['lon'])
            
            if (d_walk_start and d_walk_start <= MAX_WALK_TO_STATION and 
                d_walk_end and d_walk_end <= MAX_WALK_TO_STATION):
                transfer_candidates.append({
                    'type': 'transfer', 'xfer': xfer, 'td_a': td_a, 'td_b': td_b,
                    'walk_dist': d_walk_start + d_walk_end,
                    'walk_start': d_walk_start,
                    'walk_end': d_walk_end,
                    'meta_a': _TRAIN_META[l1], 'meta_b': _TRAIN_META[l2]
                })

    # 3. Sort by Walk Distance (Shortest Walk Wins)
    direct_candidates.sort(key=lambda x: x['walk_dist'])
    transfer_candidates.sort(key=lambda x: x['walk_dist'])

    # Build Top Results
    if direct_candidates:
        best = direct_candidates[0]
        results.append(_build_transit_card(best['line_id'], best['td'], best['meta'], orig_lat, orig_lon, dest_lat, dest_lon, 0))
    
    if transfer_candidates:
        best = transfer_candidates[0]
        results.append(_build_transfer_card(
            best['meta_a']['label'].lower(), best['td_a'], best['meta_a'],
            best['meta_b']['label'].lower(), best['td_b'], best['meta_b'],
            best['xfer'], orig_lat, orig_lon, dest_lat, dest_lon, 1
        ))

    # CRITICAL FIX: Fallback to bus/jeepney if no trains nearby
    if not results:
        bus_result = get_bus_route(orig_lon, orig_lat, dest_lon, dest_lat)
        if "error" not in bus_result:
            return {"routes": [bus_result]}
        
        jeep_result = get_jeepney_route(orig_lon, orig_lat, dest_lon, dest_lat)
        if "error" not in jeep_result:
            return {"routes": [jeep_result]}
        
        return {"error": "No transit stations within 400m walking distance. Try Car or Jeepney mode."}

    return {"routes": results}


def get_nearby_transit(lat, lon, radius_m=1000):
    nearby = []
    for r in _load_jeepney_data():
        pts = _resolve_jeepney_route(r)
        best_p = None
        min_d = float('inf')
        for p in pts:
            d = _haversine_m(lat, lon, p['lat'], p['lon'])
            if d < min_d: min_d = d; best_p = p
        if min_d <= radius_m and best_p:
            nearby.append({'type': 'jeepney', 'color': '#e67e22', 'route_name': r['route_name'], 'name': best_p['name'], 'lat': best_p['lat'], 'lon': best_p['lon'], 'dist': min_d})
    for r in _load_bus_json():
        pts = _resolve_json_bus_route(r)
        best_p = None
        min_d = float('inf')
        for p in pts:
            d = _haversine_m(lat, lon, p['lat'], p['lon'])
            if d < min_d: min_d = d; best_p = p
        if min_d <= radius_m and best_p:
            nearby.append({'type': 'bus', 'color': '#2980b9', 'route_name': r['route_name'], 'name': best_p['name'], 'lat': best_p['lat'], 'lon': best_p['lon'], 'dist': min_d})
    for line_id, data in _LINE_CACHE.items():
        if data:
            stations, _ = data
            best_st = None
            min_d = float('inf')
            for st in stations:
                d = _haversine_m(lat, lon, st['lat'], st['lon'])
                if d < min_d: min_d = d; best_st = st
            if min_d <= radius_m and best_st:
                nearby.append({'type': 'train', 'color': '#27ae60', 'route_name': line_id.upper(), 'name': best_st['name'], 'lat': best_st['lat'], 'lon': best_st['lon'], 'dist': min_d})
    nearby.sort(key=lambda x: x['dist'])
    return nearby[:5]

def get_navigation_data(orig_lon, orig_lat, dest_lon, dest_lat, commuter_type, flood_zones):
    ctype = commuter_type.lower().strip()
    if _haversine_m(orig_lat, orig_lon, dest_lat, dest_lon) <= 1000 and ctype in ["train", "transit", "jeepney", "bus"]:
        return get_walk_route(orig_lon, orig_lat, dest_lon, dest_lat)
    if ctype == "train": return plan_transit_journey(orig_lon, orig_lat, dest_lon, dest_lat)
    if ctype == "transit" or ctype == "jeepney":
        result = get_jeepney_route(orig_lon, orig_lat, dest_lon, dest_lat)
        if "error" not in result: return result
        result = get_bus_route(orig_lon, orig_lat, dest_lon, dest_lat)
        if "error" not in result: return {"routes": [result]}
        return {"error": "No jeepney or bus route found for this journey."}
    if ctype == "walk": return get_walk_route(orig_lon, orig_lat, dest_lon, dest_lat)
    if ctype == "motorcycle": return get_motorcycle_route(orig_lon, orig_lat, dest_lon, dest_lat)
    return get_car_route(orig_lon, orig_lat, dest_lon, dest_lat)