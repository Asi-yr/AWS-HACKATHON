import requests
import time
import json
import math
import os

# ════════════════════════════════════════════════════════════════════════════
#  navigation.py  —  SafeRouteAI
#  Route calculation for all commuter types.
#
#  ┌─────────────────────────────────────────────────────────────────────┐
#  │  SECTION MAP                                                        │
#  │  1. Overpass API retry wrapper          (line ~35)                  │
#  │  2. General helpers                     (line ~75)                  │
#  │  3. OSM name resolver                   (line ~125)                 │
#  │  4. !! TRAIN ROUTING — DO NOT MODIFY !! (line ~145)                 │
#  │     4a. _extract_relation_data()                                    │
#  │     4b. get_osm_railway_geometry()                                  │
#  │  5. Road / Bus routing                  (line ~330)                 │
#  │  5b. Jeepney JSON-backed routing        (line ~390)                 │
#  │  6. [FUTURE] Multi-modal connector hook (line ~530)                 │
#  │  7. Public API — get_navigation_data()  (line ~565)                 │
#  └─────────────────────────────────────────────────────────────────────┘
# ════════════════════════════════════════════════════════════════════════


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
            print(f"[overpass] Attempt {attempt + 1}/{max_retries} -> {endpoint}")
            resp = requests.post(endpoint, data=query, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            print(f"[overpass] Timed out on {endpoint}")
        except requests.exceptions.HTTPError as e:
            print(f"[overpass] HTTP error on {endpoint}: {e}")
        except requests.exceptions.RequestException as e:
            print(f"[overpass] Connection error on {endpoint}: {e}")
        attempt += 1
        if attempt < max_retries:
            wait = 3 * attempt
            print(f"[overpass] Waiting {wait}s before retry...")
            time.sleep(wait)
    print("[overpass] All attempts exhausted.")
    return None


# ── 2. General helpers ────────────────────────────────────────────────────────

_GEOCODE_CACHE = {}

def geocode_location(address):
    """Geocode origin/dest user input safely."""
    if address in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[address]

    if "," in address:
        try:
            parts =[x.strip() for x in address.split(',')]
            lat, lon = float(parts[0]), float(parts[1])
            result = (lon, lat) if lon > 100 else (lat, lon)
            _GEOCODE_CACHE[address] = result
            return result
        except (ValueError, TypeError):
            pass
            
    time.sleep(1.1) # Prevent rate-limit crash
    url = (f"https://nominatim.openstreetmap.org/search"
           f"?q={requests.utils.quote(address)}&format=json&limit=1&countrycodes=ph")
    try:
        headers = {'User-Agent': 'SafeRouteAI/1.0 (contact@saferoute.local)'}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            resp = response.json()
            if resp:
                result = float(resp[0]['lon']), float(resp[0]['lat'])
                _GEOCODE_CACHE[address] = result
                return result
    except Exception as e:
        print(f"Geocoding failed for '{address}': {e}")
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
    print(f"[railway] {len(segments)} raw ways -> {len(components)} component(s)")
    return components


# ── 3. OSM name resolver ──────────────────────────────────────────────────────
#  Maps frontend commuter_type values to their OSM relation name.
#  Add aliases here freely — do NOT touch anything in section 4.

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
#
#  STATUS: PRODUCTION-STABLE — working correctly for LRT-1, LRT-2, MRT-3, PNR
#
#  These two functions use OSM *route relations* (not raw way geometry) to:
#    • Obtain stations in their correct physical order (from relation members)
#    • Snap origin & destination to the nearest real OSM station node
#    • Slice exactly the stops between those two snap points
#    • Trim the track polyline to the same range — no overshoot, no undershoot
#
#  If you need to:
#    • Support a new line     → add an alias in _osm_name() above (section 3)
#    • Add transfer routing   → write a NEW function in section 6 that CALLS
#                               get_osm_railway_geometry() per leg
#    • Change map rendering   → edit _draw_train_route() in main.py only
#
#  DO NOT change _extract_relation_data() or get_osm_railway_geometry().
# ════════════════════════════════════════════════════════════════════════════

_STOP_ROLES           = {'stop', 'stop_entry_only', 'stop_exit_only'}
_STATION_RAILWAY_TAGS = {'station', 'stop', 'halt', 'tram_stop', 'subway_entrance'}


def _extract_relation_data(relation):
    # !! DO NOT MODIFY !!
    # Returns (stops_list, way_segments_list) from one OSM route relation.
    # Stops are in OSM member order = physical line sequence.
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
            # Skip platforms — duplicate positional data
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
    # !! DO NOT MODIFY !!
    # See section 4 header above for full explanation.
    name = _osm_name(user_input)
    print(f"[railway] Querying OSM route relation for: {name}")

    query = f"""
[out:json][timeout:35];
(
  relation["route"~"rail|light_rail|subway"]["name"~"{name}",i](14.2,120.9,14.8,121.2);
  relation["route"~"rail|light_rail|subway"]["ref"~"{name}",i](14.2,120.9,14.8,121.2);
);
out geom;
"""
    data = _overpass_query(query)
    if not data:
        print("[railway] Could not reach Overpass.")
        return None

    relations = [el for el in data.get('elements', []) if el.get('type') == 'relation']
    if not relations:
        print("[railway] No route relations found for this line.")
        return None

    print(f"[railway] Found {len(relations)} relation(s).")

    candidates = []
    all_ways   = []
    for rel in relations:
        stops, ways = _extract_relation_data(rel)
        all_ways.extend(ways)
        if len(stops) >= 2:
            candidates.append((stops, ways, rel.get('tags', {})))
            print(f"[railway]   '{rel.get('tags', {}).get('name', '?')}' "
                  f"-> {len(stops)} stops, {len(ways)} ways")

    if not candidates:
        print("[railway] No relations with usable stops found.")
        return None

    def score_candidate(stops):
        o_d = min(_dist_sq(s['lat'], s['lon'], orig_lat, orig_lon) for s in stops)
        d_d = min(_dist_sq(s['lat'], s['lon'], dest_lat, dest_lon) for s in stops)
        return o_d + d_d

    best_stops, _, _ = min(candidates, key=lambda c: score_candidate(c[0]))

    # Deduplicate way segments across relations before chaining
    seen_keys   = set()
    unique_ways = []
    for seg in all_ways:
        key  = (round(seg[0][0], 5), round(seg[0][1], 5),
                round(seg[-1][0], 5), round(seg[-1][1], 5))
        rkey = (key[2], key[3], key[0], key[1])
        if key not in seen_keys and rkey not in seen_keys:
            seen_keys.add(key)
            unique_ways.append(seg)

    print(f"[railway] {len(best_stops)} ordered stops | {len(unique_ways)} unique ways")

    def nearest_stop_idx(lat, lon, stops):
        return min(range(len(stops)),
                   key=lambda i: _dist_sq(stops[i]['lat'], stops[i]['lon'], lat, lon))

    orig_si = nearest_stop_idx(orig_lat, orig_lon, best_stops)
    dest_si = nearest_stop_idx(dest_lat, dest_lon, best_stops)

    print(f"[railway] Origin  -> '{best_stops[orig_si]['name']}' (idx {orig_si})")
    print(f"[railway] Dest    -> '{best_stops[dest_si]['name']}' (idx {dest_si})")

    if orig_si == dest_si:
        print("[railway] Origin and destination snap to the same station.")
        return None

    si, ei     = min(orig_si, dest_si), max(orig_si, dest_si)
    route_stops = best_stops[si: ei + 1]
    print(f"[railway] {len(route_stops)} stations: "
          f"'{route_stops[0]['name']}' -> '{route_stops[-1]['name']}'")

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
                print(f"[railway] Track trimmed to {len(trimmed)} pts.")

    return {'track_segments': track_segments, 'stations': route_stops}

# ════════════════════════════════════════════════════════════════════════════
#  END OF PROTECTED TRAIN SECTION — safe to edit everything below
# ════════════════════════════════════════════════════════════════════════════


# ── 5. Road / Bus routing ─────────────────────────────────────────────────────

_OSRM_BASE    = "https://router.project-osrm.org/route/v1/driving"
_OSRM_FOOT    = "https://router.project-osrm.org/route/v1/foot"
_ROUTE_COLORS = {
    "car":     ["#3498db", "#1a6fa3", "#0e3d5c"],
    "jeepney": ["#e67e22", "#d35400", "#a04000"],
    "bus":     ["#27ae60", "#1e8449", "#145a32"],
}


def _osrm_road_route(orig_lon, orig_lat, dest_lon, dest_lat, mode_label, colors):
    """Shared OSRM caller — returns a standard routes payload."""
    url = (
        f"{_OSRM_BASE}/{orig_lon},{orig_lat};{dest_lon},{dest_lat}"
        f"?overview=full&geometries=geojson&alternatives=true&steps=true"
    )
    try:
        r = requests.get(url, headers={'User-Agent': 'SafeRouteAI'}, timeout=10).json()
        if r.get("code") != "Ok":
            return {"error": "Could not calculate road route."}
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
    """Car / private vehicle — OSRM driving."""
    return _osrm_road_route(orig_lon, orig_lat, dest_lon, dest_lat, "Car", _ROUTE_COLORS["car"])


# ====
# new features that will be implemented soon, the motorcycle and the walk mode.
# when modifying please finally uncomment thanks.
# ====
#
def get_motorcycle_route(orig_lon, orig_lat, dest_lon, dest_lat):
    """Motorcycle routing — Uses OSRM driving but styled specifically for 2-wheels."""
    colors =["#8e44ad", "#9b59b6", "#af7ac5"] # Purple theme
    return _osrm_road_route(orig_lon, orig_lat, dest_lon, dest_lat, "Motorcycle", colors)

def get_walk_route(orig_lon, orig_lat, dest_lon, dest_lat):
    """Dedicated walking mode using OSRM Foot profile."""
    url = (
        f"{_OSRM_FOOT}/{orig_lon},{orig_lat};{dest_lon},{dest_lat}"
        f"?overview=full&geometries=geojson"
    )
    try:
        r = requests.get(url, headers={'User-Agent': 'SafeRouteAI'}, timeout=10).json()
        if r.get("code") == "Ok" and r.get("routes"):
            route = r["routes"][0]
            coords = [[pt[1], pt[0]] for pt in route["geometry"]["coordinates"]]
            return {"routes":[{
                "id": 0,
                "name": "Walking Route",
                "type": "walk",
                "color": "#2ecc71",
                "time": f"{int(route['duration'] / 60)} mins",
                "distance": f"{round(route['distance'] / 1000, 1)} km",
                "coords": coords,
                "segments":[],
                "stations":[],
                "safety_score": 90,
                "hazards_flagged": "Pedestrian paths only",
            }]}
    except Exception as e:
        print(f"[walk route] OSRM failed: {e}")
        
    return {"error": "Could not calculate walking route."}


# ═══════════════════════════════════════════════════════════════════════════
#  BUS ROUTING — OSM Overpass first, bus.json fallback
#
#  Strategy:
#   1. Query Overpass for route=bus relations whose stops are near both
#      origin and destination (within Metro Manila + nearby provinces bbox).
#   2. For each matching OSM relation: extract ordered stop nodes → build
#      OSRM polyline through those stops.
#   3. If Overpass returns nothing (timeout / no coverage), fall back to
#      bus.json endpoint pairs → Nominatim geocode → OSRM.
#
#  OSM stop nodes become the blue dot "stations" pins on the map.
# ═══════════════════════════════════════════════════════════════════════════

_BUS_OSM_CACHE   = {}    # keyed cache: routes_for_NODE, node_NODE
_BUS_POLY_CACHE  = {}     # cache_key → {polyline, stations, dur, dist}
_BUS_ROUTES_DATA = None   # bus.json fallback data

_OVERPASS_URL  = 'https://overpass-api.de/api/interpreter'
_BUS_BBOX      = '14.20,120.75,15.10,121.35'   # lat_min,lon_min,lat_max,lon_max


def _load_bus_json():
    """Load bus.json fallback, cached."""
    global _BUS_ROUTES_DATA
    if _BUS_ROUTES_DATA is not None:
        return _BUS_ROUTES_DATA
    base = os.path.dirname(os.path.abspath(__file__))
    cwd  = os.getcwd()
    for path in [
        os.path.join(base, 'map_transit', 'bus.json'),
        os.path.join(base, 'bus.json'),
        os.path.join(cwd,  'map_transit', 'bus.json'),
        os.path.join(cwd,  'bus.json'),
    ]:
        if not os.path.exists(path):
            continue
        try:
            data = json.loads(open(path, encoding='utf-8').read().strip())
            _BUS_ROUTES_DATA = data if isinstance(data, list) else [data]
            print(f"[bus] JSON fallback: {len(_BUS_ROUTES_DATA)} routes from {path}")
            return _BUS_ROUTES_DATA
        except Exception as e:
            print(f"[bus] JSON parse error {path}: {e}")
    _BUS_ROUTES_DATA = []
    return []


# def _fetch_stops_near(lat, lon, radius_m=600):
#     """
#     Query Overpass for bus stops within radius_m of a point.
#     Uses a small around: query — fast, never times out.
#     Returns list of {node_id, name, lat, lon}.
#     """
#     q = f"""
# [out:json][timeout:15];
# (
#   node["highway"="bus_stop"](around:{radius_m},{lat},{lon});
#   node["public_transport"="stop_position"](around:{radius_m},{lat},{lon});
#   node["public_transport"="platform"]["bus"="yes"](around:{radius_m},{lat},{lon});
# );
# out body;
# """
#     data = _overpass_query(q, max_retries=3, timeout=15)
#     if not data:
#         return []
#     stops = []
#     for el in data.get('elements', []):
#         if el['type'] == 'node' and 'lat' in el:
#             tags = el.get('tags', {})
#             stops.append({
#                 'node_id': el['id'],
#                 'name':    tags.get('name') or tags.get('ref') or f"Bus stop {el['id']}",
#                 'lat':     el['lat'],
#                 'lon':     el['lon'],
#             })
#     print(f"[bus OSM] {len(stops)} stops within {radius_m}m of ({lat:.4f},{lon:.4f})")
#     return stops


# def _fetch_routes_for_stop(node_id):
#     """
#     Given a stop node_id, fetch all bus route relations that include it.
#     Returns list of {osm_id, name, ref, stop_ids:[...]}.
#     Uses cached results to avoid duplicate queries.
#     """
#     cache_key = f"routes_for_{node_id}"
#     if cache_key in _BUS_OSM_CACHE:
#         return _BUS_OSM_CACHE[cache_key]

#     q = f"""
# [out:json][timeout:20];
# node({node_id});
# rel["route"="bus"](bn);
# out body;
# """
#     data = _overpass_query(q, max_retries=3, timeout=20)
#     routes = []
#     if data:
#         for el in data.get('elements', []):
#             if el['type'] != 'relation':
#                 continue
#             tags    = el.get('tags', {})
#             members = el.get('members', [])
#             stop_ids = [
#                 m['ref'] for m in members
#                 if m['type'] == 'node' and m.get('role') in
#                    ('stop', 'stop_entry_only', 'stop_exit_only', 'platform', '')
#             ]
#             routes.append({
#                 'osm_id':     el['id'],
#                 'route_name': tags.get('name') or f"Bus {tags.get('ref','?')}",
#                 'ref':        tags.get('ref', ''),
#                 'stop_ids':   stop_ids,
#             })

#     print(f"[bus OSM] stop {node_id} belongs to {len(routes)} bus relations")
#     _BUS_OSM_CACHE[cache_key] = routes
#     return routes


# def _fetch_stop_coords(stop_ids):
#     """
#     Fetch lat/lon for a list of OSM node ids.
#     Batches them in one Overpass query. Cached individually.
#     """
#     needed = [sid for sid in stop_ids if f"node_{sid}" not in _BUS_OSM_CACHE]
#     if needed:
#         ids_str = ''.join(f'node({sid});' for sid in needed)
#         q = f"[out:json][timeout:15];({ids_str});out body;"
#         data = _overpass_query(q, max_retries=2, timeout=15)
#         if data:
#             for el in data.get('elements', []):
#                 if el['type'] == 'node' and 'lat' in el:
#                     tags = el.get('tags', {})
#                     _BUS_OSM_CACHE[f"node_{el['id']}"] = {
#                         'node_id': el['id'],
#                         'name':    tags.get('name') or tags.get('ref') or f"Stop {el['id']}",
#                         'lat':     el['lat'],
#                         'lon':     el['lon'],
#                     }
#     return [_BUS_OSM_CACHE[f"node_{sid}"]
#             for sid in stop_ids if f"node_{sid}" in _BUS_OSM_CACHE]


# def _fetch_osm_bus_routes(orig_lat, orig_lon, dest_lat, dest_lon):
#     """
#     Two-step local query — never fetches all of Metro Manila at once:

#     Step 1: Find bus stops within 600m of origin AND within 600m of dest.
#     Step 2: One batched query — get all bus relations that include ANY
#             origin stop (using node union + rel(bn)).
#     Step 3: Keep only relations that also include a destination stop.
#     Step 4: Fetch ordered stop coords for matched relations.

#     Returns list of {osm_id, route_name, ref, stops:[{name,lat,lon}]}
#     """
#     orig_stops = _fetch_stops_near(orig_lat, orig_lon, radius_m=600)
#     dest_stops = _fetch_stops_near(dest_lat, dest_lon, radius_m=600)

#     if not orig_stops or not dest_stops:
#         print("[bus OSM] No stops found near origin or destination")
#         return []

#     dest_node_ids = {s['node_id'] for s in dest_stops}

#     # Single batched query: all bus relations touching any origin stop
#     orig_ids_str = ''.join(f'node({s["node_id"]});' for s in orig_stops)
#     q = f"""
# [out:json][timeout:25];
# (
#   {orig_ids_str}
# );
# rel["route"="bus"](bn);
# out body;
# """
#     data = _overpass_query(q, max_retries=3, timeout=25)
#     if not data:
#         print("[bus OSM] Batched relations query failed")
#         return []

#     # Parse relations, keep only those that also cover a dest stop
#     matched_relations = {}
#     for el in data.get('elements', []):
#         if el['type'] != 'relation':
#             continue
#         tags    = el.get('tags', {})
#         members = el.get('members', [])
#         stop_ids = [
#             m['ref'] for m in members
#             if m['type'] == 'node' and m.get('role') in
#                ('stop', 'stop_entry_only', 'stop_exit_only', 'platform', '')
#         ]
#         if not any(sid in dest_node_ids for sid in stop_ids):
#             continue
#         matched_relations[el['id']] = {
#             'osm_id':     el['id'],
#             'route_name': tags.get('name') or f"Bus {tags.get('ref','?')}",
#             'ref':        tags.get('ref', ''),
#             'stop_ids':   stop_ids,
#         }

#     if not matched_relations:
#         print("[bus OSM] No relations connect origin stops to destination stops")
#         return []

#     print(f"[bus OSM] {len(matched_relations)} matching relations found")

#     # Fetch full ordered stop coords for each matched relation
#     result = []
#     for rel in matched_relations.values():
#         stop_ids = rel['stop_ids'][:60]
#         stops    = _fetch_stop_coords(stop_ids)
#         if len(stops) < 2:
#             continue
#         result.append({
#             'osm_id':     rel['osm_id'],
#             'route_name': rel['route_name'],
#             'ref':        rel['ref'],
#             'stops':      stops,
#         })

#     return result


# def _osm_bus_is_near(route, orig_lat, orig_lon, dest_lat, dest_lon, threshold_m=600):
#     """
#     Check if an OSM bus route serves both origin and destination.
#     threshold_m is tight (600m) because we have real stop positions.
#     Returns (True, board_stop_idx, alight_stop_idx) or (False, None, None).
#     """
#     stops = route['stops']
#     board_idx  = None
#     board_dist = float('inf')
#     alight_idx = None
#     alight_dist = float('inf')

#     for i, s in enumerate(stops):
#         d_orig = _haversine_m(orig_lat, orig_lon, s['lat'], s['lon'])
#         d_dest = _haversine_m(dest_lat, dest_lon, s['lat'], s['lon'])
#         if d_orig < board_dist:
#             board_dist = d_orig
#             board_idx  = i
#         if d_dest < alight_dist:
#             alight_dist = d_dest
#             alight_idx  = i

#     if board_idx is None or alight_idx is None:
#         return False, None, None
#     if board_dist > threshold_m or alight_dist > threshold_m:
#         return False, None, None
#     if board_idx == alight_idx:
#         return False, None, None

#     # Both directions are valid for OSM routes (they may be one-way or circular)
#     return True, board_idx, alight_idx


# def _build_osm_bus_polyline(route, board_idx, alight_idx):
#     """
#     Build OSRM polyline for an OSM bus route using the stop nodes as waypoints.
#     Slices stops between board and alight (handles forward and reverse).
#     """
#     cache_key = f"osm:{route['osm_id']}:{board_idx}:{alight_idx}"
#     if cache_key in _BUS_POLY_CACHE:
#         return _BUS_POLY_CACHE[cache_key]

#     stops = route['stops']
#     # Determine direction
#     if board_idx < alight_idx:
#         seg_stops = stops[board_idx: alight_idx + 1]
#     else:
#         seg_stops = list(reversed(stops[alight_idx: board_idx + 1]))

#     if len(seg_stops) < 2:
#         _BUS_POLY_CACHE[cache_key] = None
#         return None

#     print(f"[bus OSM] Building '{route['route_name']}' "
#           f"({len(seg_stops)} stops, {board_idx}→{alight_idx})...")

#     wp_str     = ';'.join(f"{s['lon']},{s['lat']}" for s in seg_stops)
#     approaches = ';'.join('curb' for _ in seg_stops)
#     url = (
#         f"{_OSRM_BASE}/{wp_str}"
#         f"?overview=full&geometries=geojson"
#         f"&continue_straight=true"
#         f"&approaches={approaches}"
#     )
#     try:
#         r = requests.get(url, headers={'User-Agent': 'SafeRouteAI'}, timeout=15).json()
#         if r.get('code') == 'Ok' and r.get('routes'):
#             rt       = r['routes'][0]
#             polyline = [[pt[1], pt[0]] for pt in rt['geometry']['coordinates']]
#             result   = {
#                 'polyline':  polyline,
#                 'stations':  seg_stops,
#                 'dur':       rt['duration'],
#                 'dist':      rt['distance'],
#                 'source':    'osm',
#             }
#             _BUS_POLY_CACHE[cache_key] = result
#             print(f"[bus OSM] Built '{route['route_name']}': "
#                   f"{len(polyline)} pts, {rt['distance']/1000:.1f} km")
#             return result
#     except Exception as e:
#         print(f"[bus OSM] OSRM failed: {e}")

#     _BUS_POLY_CACHE[cache_key] = None
#     return None


# ── JSON fallback helpers (same Nominatim + OSRM pattern as jeepney) ─────────

_BUS_GEOCODE_CACHE = {}

def _geocode_bus_endpoint(name):
    """Nominatim geocode for bus.json endpoint names. Safe from crashes."""
    if name in _BUS_GEOCODE_CACHE:
        return _BUS_GEOCODE_CACHE[name]
        
    time.sleep(1.1) # Prevent rate-limit crash
    try:
        headers = {'User-Agent': 'SafeRouteAI/1.0 (contact@saferoute.local)'}
        response = requests.get(
            'https://nominatim.openstreetmap.org/search',
            params={'q': name, 'format': 'json', 'limit': 3, 'countrycodes': 'ph', 'bounded': 0},
            headers=headers, timeout=8
        )
        if response.status_code == 200:
            resp = response.json()
            if resp:
                lat, lon = float(resp[0]['lat']), float(resp[0]['lon'])
                print(f"[bus JSON geocode] '{name}' → {lat:.4f}, {lon:.4f}")
                _BUS_GEOCODE_CACHE[name] = (lat, lon)
                return lat, lon
            else:
                print(f"[bus JSON geocode] No results for '{name}'")
        else:
            print(f"[bus JSON geocode] Rate limited: HTTP {response.status_code}")
    except Exception as e:
        print(f"[bus JSON geocode] Failed '{name}': {e}")
    _BUS_GEOCODE_CACHE[name] = (None, None)
    return None, None


def _resolve_json_bus_route(jroute):
    """Geocode bus.json endpoint names once, cache in jroute['_resolved']."""
    if '_resolved' in jroute:
        return jroute['_resolved']
    resolved = []
    for road in jroute.get('roads', []):
        name = road if isinstance(road, str) else road.get('name', '')
        lat, lon = _geocode_bus_endpoint(name)
        if lat is not None:
            resolved.append({'name': name, 'lat': lat, 'lon': lon})
    jroute['_resolved'] = resolved
    return resolved


def _json_bus_is_near(jroute, orig_lat, orig_lon, dest_lat, dest_lon, threshold_m=6000):
    """Direction-aware pre-filter for JSON bus routes."""
    pts = _resolve_json_bus_route(jroute)
    if len(pts) < 2:
        return False, None

    def _check(ordered):
        if not any(_haversine_m(orig_lat, orig_lon, p['lat'], p['lon']) <= threshold_m for p in ordered):
            return False
        if not any(_haversine_m(dest_lat, dest_lon, p['lat'], p['lon']) <= threshold_m for p in ordered):
            return False
        d_o_first = _haversine_m(orig_lat, orig_lon, ordered[0]['lat'], ordered[0]['lon'])
        d_o_last  = _haversine_m(orig_lat, orig_lon, ordered[-1]['lat'], ordered[-1]['lon'])
        d_d_first = _haversine_m(dest_lat, dest_lon, ordered[0]['lat'], ordered[0]['lon'])
        d_d_last  = _haversine_m(dest_lat, dest_lon, ordered[-1]['lat'], ordered[-1]['lon'])
        return d_o_first < d_o_last and d_d_last < d_d_first

    if _check(pts):
        return True, True
    if _check(list(reversed(pts))):
        return True, False
    return False, None


def _build_json_bus_polyline(jroute, going_fwd=True):
    """OSRM polyline from bus.json geocoded endpoints."""
    name      = jroute['route_name']
    cache_key = f"json:{name}:{'fwd' if going_fwd else 'rev'}"
    if cache_key in _BUS_POLY_CACHE:
        return _BUS_POLY_CACHE[cache_key]

    pts     = _resolve_json_bus_route(jroute)
    ordered = pts if going_fwd else list(reversed(pts))
    if len(ordered) < 2:
        _BUS_POLY_CACHE[cache_key] = None
        return None

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
    except Exception as e:
        print(f"[bus JSON] OSRM failed: {e}")
    _BUS_POLY_CACHE[cache_key] = None
    return None


# ── Main entry point ──────────────────────────────────────────────────────────

def get_bus_route(orig_lon, orig_lat, dest_lon, dest_lat):
    """
    Bus routing — Exclusively uses bus.json fallback data.
    """
    color = (_ROUTE_COLORS["bus"][0]
             if isinstance(_ROUTE_COLORS.get("bus"), list)
             else _ROUTE_COLORS.get("bus", "#27ae60"))

    best = None
    print("[bus] Processing JSON routes from bus.json...")
    
    # Iterate exclusively through the local JSON file
    for jroute in _load_bus_json():
        passes, going_fwd = _json_bus_is_near(jroute, orig_lat, orig_lon, dest_lat, dest_lon)
        if not passes:
            continue
            
        built = _build_json_bus_polyline(jroute, going_fwd)
        if not built:
            continue
            
        polyline = built['polyline']
        if len(polyline) < 2:
            continue

        board_idx, board_lat, board_lon, board_m   = _snap_to_polyline(polyline, orig_lat, orig_lon)
        alight_idx, alight_lat, alight_lon, alght_m = _snap_to_polyline(polyline, dest_lat, dest_lon)
        
        if board_idx >= alight_idx:
            continue
        if board_m > _MAX_BOARD_WALK_M or alght_m > _MAX_ALIGHT_WALK_M:
            continue

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

    # Build the final response
    built   = best['built']
    bus_seg = best['bus_seg']

    w_board_coords,  w_board_dist,  w_board_dur  = _get_walk_segment(
        orig_lat, orig_lon, best['board_lat'], best['board_lon'])
    w_alight_coords, w_alight_dist, w_alight_dur = _get_walk_segment(
        best['alight_lat'], best['alight_lon'], dest_lat, dest_lon)

    bus_mins   = max(1, int(best['bus_dist'] / (20_000 / 60)))
    walk_mins  = int(((w_board_dur or 0) + (w_alight_dur or 0)) / 60)
    total_mins = bus_mins + walk_mins
    total_km   = round((best['bus_dist'] + (w_board_dist or 0) + (w_alight_dist or 0)) / 1_000, 1)

    segments =[]
    if w_board_coords and len(w_board_coords) >= 2:
        segments.append({'type': 'walk', 'coords': w_board_coords,
                         'color': '#7f8c8d', 'label': f"Walk {int(best['board_m'])}m to bus stop"})
    segments.append({'type': 'bus', 'coords': bus_seg, 'color': color,
                     'label': best['name']})
    if w_alight_coords and len(w_alight_coords) >= 2:
        segments.append({'type': 'walk', 'coords': w_alight_coords,
                         'color': '#7f8c8d', 'label': f"Walk {int(best['alight_m'])}m to destination"})

    return {
        'id':             0,
        'name':           best['name'],
        'type':           'bus',
        'color':          color,
        'time':           f"~{total_mins} mins",
        'distance':       f"{total_km} km",
        'coords':         bus_seg,
        'segments':       segments,
        'stations':       built['stations'],
        'board_point':    {'lat': best['board_lat'], 'lon': best['board_lon']},
        'alight_point':   {'lat': best['alight_lat'], 'lon': best['alight_lon']},
        'walk_board_m':   int(best['board_m']),
        'walk_alight_m':  int(best['alight_m']),
        'safety_score':   70,
        'hazards_flagged': "Source: JSON database",
    }

# ── 5b. Jeepney routing — JSON stops → OSRM waypoints → ordered stop pins ─────
#
#  jeepney.json lives in map_transit/ (falls back to root).
#  Each route entry has:
#    route_name  — display name
#    stops[]     — ordered array of {name, lat, lng} — NO geocoding needed.
#                  These exact coords are used as OSRM via-points in sequence.
#
#  Algorithm:
#    1. Read stop coords from JSON in order.  No Nominatim, no geocoding.
#    2. Feed ALL stops as mandatory OSRM waypoints → polyline follows the
#       real road corridor the jeepney travels, stop by stop.
#    3. The stops become ordered map pins (like train stations).
#    4. Snap user origin → nearest polyline point  (board point)
#       Snap user dest   → nearest polyline point  (alight point)
#    5. Accept only if board_idx < alight_idx and both walks ≤ threshold.
#    6. Slice stop list to only those between board and alight positions.
#    7. Return up to 3 best matches with walk → jeepney → walk segments.

_JEEPNEY_ROUTES_DATA = None   # raw JSON, loaded once
_JEEPNEY_POLY_CACHE  = {}     # route_name → {polyline, stations, dur, dist}

_BUS_ROUTES_DATA = None       # raw JSON, loaded once
_BUS_POLY_CACHE  = {}         # route_name → {polyline, stations, dur, dist}

_MAX_BOARD_WALK_M  = 2_000
_MAX_ALIGHT_WALK_M = 2_000


def _load_jeepney_data():
    """Load jeepney.json once and cache it in memory."""
    global _JEEPNEY_ROUTES_DATA
    if _JEEPNEY_ROUTES_DATA is not None:
        return _JEEPNEY_ROUTES_DATA

    base = os.path.dirname(os.path.abspath(__file__))
    cwd  = os.getcwd()

    candidates = [
        os.path.join(base, 'map_transit', 'jeepney.json'),
        os.path.join(base, 'jeepney.json'),
        os.path.join(cwd,  'map_transit', 'jeepney.json'),
        os.path.join(cwd,  'jeepney.json'),
    ]

    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            raw = open(path, encoding='utf-8').read().strip()
            # Auto-repair: file may be missing the opening '[' bracket
            if not raw.startswith('['):
                raw = '[' + raw
            data = json.loads(raw)
            # Normalise single-object files
            if isinstance(data, dict):
                data = [data]
            _JEEPNEY_ROUTES_DATA = data
            print(f"[jeepney] Loaded {len(data)} routes from {path}")
            for r in data:
                pts = r.get('roads') or r.get('stops') or []
                print(f"[jeepney]   '{r.get('route_name','?')}' [{r.get('traffic_flow','')}] — {len(pts)} road pts")
            return _JEEPNEY_ROUTES_DATA
        except Exception as e:
            print(f"[jeepney] Failed to parse {path}: {e}")

    print("[jeepney] jeepney.json not found. Searched:")
    for p in candidates:
        print(f"[jeepney]   {'EXISTS' if os.path.exists(p) else 'missing'} -> {p}")
    _JEEPNEY_ROUTES_DATA = []
    return []


# Cache for Nominatim road-name → (lat, lon) resolutions
_ROAD_GEOCODE_CACHE = {}

def _geocode_road(road_name):
    """Resolve a road name string to (lat, lon) for jeepney fallback safely."""
    if road_name in _ROAD_GEOCODE_CACHE:
        return _ROAD_GEOCODE_CACHE[road_name]

    time.sleep(1.1) # Prevent rate-limit crash
    params = {'q': road_name, 'format': 'json', 'limit': 5, 'countrycodes': 'ph', 'bounded': 1, 'viewbox': '120.85,14.35,121.20,14.85'}
    try:
        headers = {'User-Agent': 'SafeRouteAI/1.0 (contact@saferoute.local)'}
        response = requests.get('https://nominatim.openstreetmap.org/search', params=params, headers=headers, timeout=8)

        if response.status_code == 200:
            resp = response.json()
            best = None
            for r in resp:
                if r.get('type') in ('primary', 'secondary', 'tertiary', 'residential', 'trunk', 'motorway', 'road', 'unclassified'):
                    best = r
                    break
            if best is None and resp: best = resp[0]
            if best:
                lat, lon = float(best['lat']), float(best['lon'])
                print(f"[geocode] '{road_name}' → {lat:.4f}, {lon:.4f}")
                _ROAD_GEOCODE_CACHE[road_name] = (lat, lon)
                return lat, lon
    except Exception as e:
        print(f"[geocode] Failed for '{road_name}': {e}")
    _ROAD_GEOCODE_CACHE[road_name] = (None, None)
    return None, None


def _resolve_jeepney_route(jroute):
    """
    Geocode all road name strings in jroute['roads'] and return a list of
    resolved {name, lat, lon} dicts.  Results are added back into the jroute
    as jroute['_resolved'] so they're only geocoded once per server run.
    """
    if '_resolved' in jroute:
        return jroute['_resolved']

    resolved = []
    for road in jroute.get('roads', []):
        if isinstance(road, str):
            # New name-only format
            lat, lon = _geocode_road(road)
            if lat is not None:
                resolved.append({'name': road, 'lat': lat, 'lon': lon})
            else:
                print(f"[jeepney] Could not resolve '{road}' — skipping waypoint")
        elif isinstance(road, dict):
            # Old coord-based format fallback
            lat = road.get('lat') or (road.get('fwd') or {}).get('lat')
            lon = road.get('lng') or road.get('lon') or (road.get('fwd') or {}).get('lng')
            if lat and lon:
                resolved.append({'name': road.get('name', 'Road'), 'lat': lat, 'lon': lon})

    jroute['_resolved'] = resolved
    return resolved


def _route_is_near(jroute, orig_lat, orig_lon, dest_lat, dest_lon, threshold_m=5000):
    """
    Pre-filter + direction detection using geocoded road coords.

    Geocodes road names on first call (cached).  Then checks both directions:
      Forward (A→B): origin near first point, dest near last point
      Reverse (B→A): origin near last point, dest near first point

    Returns (True, going_fwd) or (False, None).
    """
    pts = _resolve_jeepney_route(jroute)
    if len(pts) < 2:
        return False, None

    def _check(ordered_pts):
        orig_near = any(_haversine_m(orig_lat, orig_lon, p['lat'], p['lon']) <= threshold_m
                        for p in ordered_pts)
        dest_near = any(_haversine_m(dest_lat, dest_lon, p['lat'], p['lon']) <= threshold_m
                        for p in ordered_pts)
        if not (orig_near and dest_near):
            return False
        d_o_first = _haversine_m(orig_lat, orig_lon, ordered_pts[0]['lat'], ordered_pts[0]['lon'])
        d_o_last  = _haversine_m(orig_lat, orig_lon, ordered_pts[-1]['lat'], ordered_pts[-1]['lon'])
        d_d_first = _haversine_m(dest_lat, dest_lon, ordered_pts[0]['lat'], ordered_pts[0]['lon'])
        d_d_last  = _haversine_m(dest_lat, dest_lon, ordered_pts[-1]['lat'], ordered_pts[-1]['lon'])
        return d_o_first < d_o_last and d_d_last < d_d_first

    if _check(pts):
        return True, True
    if _check(list(reversed(pts))):
        return True, False
    return False, None


def _build_jeepney_polyline(jroute, going_fwd=True):
    """
    Build OSRM road polyline. Uses geocoded road-name coords.
    going_fwd=False reverses the waypoint order for the B→A direction.
    OSRM approaches=curb keeps the route on the correct curbside.
    """
    name      = jroute['route_name']
    cache_key = f"{name}:{'fwd' if going_fwd else 'rev'}"
    if cache_key in _JEEPNEY_POLY_CACHE:
        return _JEEPNEY_POLY_CACHE[cache_key]

    pts = _resolve_jeepney_route(jroute)
    if len(pts) < 2:
        print(f"[jeepney] '{name}' — not enough geocoded points.")
        _JEEPNEY_POLY_CACHE[cache_key] = None
        return None

    ordered = pts if going_fwd else list(reversed(pts))
    direction = 'fwd' if going_fwd else 'rev'
    print(f"[jeepney] Building '{name}' [{direction}] ({len(ordered)} pts)...")

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
            result   = {
                'polyline': polyline,
                'stations': ordered,
                'dur':      rt['duration'],
                'dist':     rt['distance'],
            }
            _JEEPNEY_POLY_CACHE[cache_key] = result
            print(f"[jeepney] Built '{name}' [{direction}]: {len(polyline)} pts, "
                  f"{rt['distance']/1000:.1f} km")
            return result
        else:
            print(f"[jeepney] OSRM error for '{name}': {r.get('code')}")
    except Exception as e:
        print(f"[jeepney] OSRM failed for '{name}': {e}")

    _JEEPNEY_POLY_CACHE[cache_key] = None
    return None


def _snap_to_polyline(polyline, lat, lon):
    """Return (index, snapped_lat, snapped_lon, dist_m) on polyline closest to (lat, lon)."""
    best = min(range(len(polyline)),
               key=lambda i: _haversine_m(lat, lon, polyline[i][0], polyline[i][1]))
    return best, polyline[best][0], polyline[best][1], \
           _haversine_m(lat, lon, polyline[best][0], polyline[best][1])


def _polyline_distance_m(polyline):
    """Sum of haversine distances along a polyline in metres."""
    return sum(
        _haversine_m(polyline[i][0], polyline[i][1],
                     polyline[i + 1][0], polyline[i + 1][1])
        for i in range(len(polyline) - 1)
    )


def _get_walk_segment(orig_lat, orig_lon, dest_lat, dest_lon):
    """
    Return walking polyline, distance_m, duration_s between two points.
    Tries OSRM foot profile first; falls back to a straight-line connector
    so the map always has something to draw.
    """
    # Skip trivial walks (< 15 m) — don't clutter the map
    straight = _haversine_m(orig_lat, orig_lon, dest_lat, dest_lon)
    if straight < 15:
        return None, 0, 0

    url = (
        f"{_OSRM_FOOT}/{orig_lon},{orig_lat};{dest_lon},{dest_lat}"
        f"?overview=full&geometries=geojson"
    )
    try:
        r = requests.get(url, headers={'User-Agent': 'SafeRouteAI'}, timeout=8).json()
        if r.get('code') == 'Ok' and r.get('routes'):
            rt = r['routes'][0]
            coords = [[pt[1], pt[0]] for pt in rt['geometry']['coordinates']]
            return coords, rt['distance'], rt['duration']
    except Exception as e:
        print(f"[walk] OSRM foot failed ({e}), using straight-line fallback")

    # Straight-line fallback — simple but always works
    return ([[orig_lat, orig_lon], [dest_lat, dest_lon]],
            straight,
            straight / 1.2)  # ~1.2 m/s walking speed


def get_jeepney_route(orig_lon, orig_lat, dest_lon, dest_lat):
    """
    Find the single best jeepney route for this origin/destination.

    Steps:
      1. Pre-filter all routes using raw JSON stop coords — cheap haversine
         check.  Routes where no stop is near the user are skipped entirely,
         so we never waste Nominatim or OSRM calls on irrelevant routes.
      2. Build OSRM polyline only for the pre-filtered candidates.
      3. Snap user origin/dest to nearest polyline point.
      4. Return the one best match (least total walking distance).
    """
    all_routes = _load_jeepney_data()
    color      = _ROUTE_COLORS["jeepney"][0]

    # ── Step 1: cheap pre-filter + direction detection ───────────────────
    nearby = []
    for r in all_routes:
        passes, going_fwd = _route_is_near(r, orig_lat, orig_lon, dest_lat, dest_lon)
        if passes:
            nearby.append((r, going_fwd))
    print(f"[jeepney] {len(nearby)}/{len(all_routes)} routes pass pre-filter")

    if not nearby:
        return {"error": (
            "No jeepney route found near your origin and destination. "
            "Try a different commuter type or check your locations."
        )}

    # ── Step 2 & 3: build polyline + snap, keep only valid direction ──────
    best = None

    for jroute, going_fwd in nearby:
        built = _build_jeepney_polyline(jroute, going_fwd)
        if not built:
            continue

        polyline = built['polyline']
        if len(polyline) < 2:
            continue

        board_idx,  board_lat,  board_lon,  board_m  = _snap_to_polyline(polyline, orig_lat, orig_lon)
        alight_idx, alight_lat, alight_lon, alght_m  = _snap_to_polyline(polyline, dest_lat, dest_lon)

        if board_idx >= alight_idx:
            continue
        if board_m > _MAX_BOARD_WALK_M or alght_m > _MAX_ALIGHT_WALK_M:
            continue

        jeepney_seg = polyline[board_idx: alight_idx + 1]
        jeep_dist_m = _polyline_distance_m(jeepney_seg)
        total_walk  = board_m + alght_m

        # Slice stops to those between board and alight
        route_stops = []
        for stop in built['stations']:
            si, _, _, _ = _snap_to_polyline(polyline, stop['lat'], stop['lon'])
            if board_idx <= si <= alight_idx:
                route_stops.append({**stop, '_idx': si})
        route_stops.sort(key=lambda s: s['_idx'])
        for s in route_stops:
            s.pop('_idx', None)

        cand = {
            'jroute':      jroute,
            'board_lat':   board_lat,   'board_lon':  board_lon,
            'board_m':     board_m,
            'alight_lat':  alight_lat,  'alight_lon': alight_lon,
            'alight_m':    alght_m,
            'jeepney_seg': jeepney_seg,
            'jeep_dist_m': jeep_dist_m,
            'total_walk_m': total_walk,
            'route_stops': route_stops,
        }

        if best is None or total_walk < best['total_walk_m']:
            best = cand

    if best is None:
        return {"error": (
            "No jeepney route found near your origin and destination. "
            "Try a different commuter type or check your locations."
        )}

    # ── Step 4: build the single result ───────────────────────────────────
    jroute      = best['jroute']
    jeepney_seg = best['jeepney_seg']

    w_board_coords,  w_board_dist,  w_board_dur  = _get_walk_segment(
        orig_lat, orig_lon, best['board_lat'], best['board_lon']
    )
    w_alight_coords, w_alight_dist, w_alight_dur = _get_walk_segment(
        best['alight_lat'], best['alight_lon'], dest_lat, dest_lon
    )

    jeep_mins  = max(1, int(best['jeep_dist_m'] / (15_000 / 60)))
    walk_mins  = int(((w_board_dur or 0) + (w_alight_dur or 0)) / 60)
    total_mins = jeep_mins + walk_mins
    total_km   = round(
        (best['jeep_dist_m'] + (w_board_dist or 0) + (w_alight_dist or 0)) / 1_000, 1
    )

    segments = []
    if w_board_coords and len(w_board_coords) >= 2:
        segments.append({
            'type':   'walk',
            'coords': w_board_coords,
            'color':  '#7f8c8d',
            'label':  f"Walk {int(best['board_m'])}m to jeepney stop",
        })
    segments.append({
        'type':   'jeepney',
        'coords': jeepney_seg,
        'color':  color,
        'label':  jroute['route_name'],
    })
    if w_alight_coords and len(w_alight_coords) >= 2:
        segments.append({
            'type':   'walk',
            'coords': w_alight_coords,
            'color':  '#7f8c8d',
            'label':  f"Walk {int(best['alight_m'])}m to destination",
        })

    print(f"[jeepney] Best match: '{jroute['route_name']}' "
          f"walk_in={int(best['board_m'])}m walk_out={int(best['alight_m'])}m")

    return {"routes": [{
        'id':              0,
        'name':            jroute['route_name'],
        'type':            'jeepney',
        'color':           color,
        'time':            f"~{total_mins} mins",
        'distance':        f"{total_km} km",
        'coords':          jeepney_seg,
        'segments':        segments,
        'stations':        best['route_stops'],
        'board_point':     {'lat': best['board_lat'], 'lon': best['board_lon']},
        'alight_point':    {'lat': best['alight_lat'], 'lon': best['alight_lon']},
        'walk_board_m':    int(best['board_m']),
        'walk_alight_m':   int(best['alight_m']),
        'safety_score':    75,
        'hazards_flagged': 'Variable — mid-block stops',
    }]}


# ── 6. [FUTURE] Multi-modal connector hook ───────────────────────────────────
#
#  Reserved for connecting multiple route legs together
#  e.g. Walk → LRT-1 → Transfer → MRT-3 → Walk.
#
#  Design contract (to be implemented in a future commit):
#    • Each "leg" dict:
#        {
#          "leg_type":  "walk" | "train" | "bus" | "jeepney",
#          "line_name": str,            # e.g. "LRT-1"
#          "coords":    [[lat,lon]...], # polyline
#          "stations":  [{lat,lon,name}...],
#          "color":     hex str,
#          "time":      str,
#        }
#    • Journey dict:
#        {
#          "journey_type": "multimodal",
#          "legs": [leg, leg, ...],
#          "total_time": str,
#          "transfer_points": [{lat,lon,name}...],
#        }

def plan_multimodal_journey(orig_lon, orig_lat, dest_lon, dest_lat, modes=None):
    """
    Heuristic multimodal router:
    Finds the best Train backbone (LRT-1, LRT-2, MRT-3) and merges it with 
    connecting Jeepney or Walking legs for a seamless combined route.
    """
    total_dist_straight = _haversine_m(orig_lat, orig_lon, dest_lat, dest_lon)
    
    train_lines =["mrt-3", "lrt-1", "lrt-2"]
    best_train_data = None
    best_train = None
    best_score = float('inf')
    
    # 1. Evaluate which Train line connects the journey best
    for t in train_lines:
        t_data = get_osm_railway_geometry(t, orig_lat, orig_lon, dest_lat, dest_lon)
        if t_data and len(t_data['stations']) >= 2:
            s_start = t_data['stations'][0]
            s_end   = t_data['stations'][-1]
            dist_o  = _haversine_m(orig_lat, orig_lon, s_start['lat'], s_start['lon'])
            dist_d  = _haversine_m(dest_lat, dest_lon, s_end['lat'], s_end['lon'])
            score   = dist_o + dist_d
            
            if score < best_score and score < (total_dist_straight * 1.5):
                best_score = score
                best_train = t
                best_train_data = t_data
                
    # Fallback to single modes if train is unviable (e.g. short distances)
    if not best_train_data:
        j_route = get_jeepney_route(orig_lon, orig_lat, dest_lon, dest_lat)
        if "error" not in j_route and j_route.get("routes"): return j_route
        b_route = get_bus_route(orig_lon, orig_lat, dest_lon, dest_lat)
        if "error" not in b_route: return {"routes": [b_route]}
        return get_car_route(orig_lon, orig_lat, dest_lon, dest_lat)

    # 2. Build the multi-leg segments
    s_start = best_train_data['stations'][0]
    s_end   = best_train_data['stations'][-1]
    
    # Hardcoded metas to ensure safety during lookup
    t_meta_dict = {
        "lrt-1": {"color": "#008000", "label": "LRT-1 (Green)"},
        "lrt-2": {"color": "#0000CD", "label": "LRT-2 (Blue)"},
        "mrt-3": {"color": "#DAA520", "label": "MRT-3 (Yellow)"}
    }
    t_meta = t_meta_dict.get(best_train, {"color": "#8e44ad", "label": best_train})

    segments =[]
    total_time_mins = 0
    total_dist_km = 0.0
    stations =[]

    # Leg 1: Origin → Train Start (Jeepney or Walk)
    dist_to_train = _haversine_m(orig_lat, orig_lon, s_start['lat'], s_start['lon'])
    if dist_to_train > 800:
        j1 = get_jeepney_route(orig_lon, orig_lat, s_start['lon'], s_start['lat'])
        if "error" not in j1 and j1.get("routes"):
            r = j1["routes"][0]
            segments.extend(r.get("segments",[]))
            total_time_mins += int(r['time'].replace('~','').replace(' mins',''))
            total_dist_km += float(r['distance'].replace(' km',''))
            if 'stations' in r: stations.extend(r['stations'])
        else:
            w_coords, w_d, w_t = _get_walk_segment(orig_lat, orig_lon, s_start['lat'], s_start['lon'])
            if w_coords:
                segments.append({'type': 'walk', 'coords': w_coords, 'label': f'Walk to {s_start["name"]}', 'color': '#7f8c8d'})
                total_time_mins += int(w_t/60)
                total_dist_km += w_d/1000
    else:
        w_coords, w_d, w_t = _get_walk_segment(orig_lat, orig_lon, s_start['lat'], s_start['lon'])
        if w_coords:
            segments.append({'type': 'walk', 'coords': w_coords, 'label': f'Walk to {s_start["name"]}', 'color': '#7f8c8d'})
            total_time_mins += int(w_t/60)
            total_dist_km += w_d/1000

    # Leg 2: The Train Backbone
    train_dist = sum(_polyline_distance_m(seg) for seg in best_train_data['track_segments'])
    train_mins = max(1, int(train_dist / (40000 / 60))) # Approx 40km/h
    segments.append({
        'type': 'train',
        'coords': best_train_data['track_segments'],
        'color': t_meta['color'],
        'label': t_meta['label']
    })
    total_time_mins += train_mins
    total_dist_km += train_dist / 1000
    stations.extend(best_train_data['stations'])

    # Leg 3: Train End → Destination (Jeepney or Walk)
    dist_from_train = _haversine_m(s_end['lat'], s_end['lon'], dest_lat, dest_lon)
    if dist_from_train > 800:
        j2 = get_jeepney_route(s_end['lon'], s_end['lat'], dest_lon, dest_lat)
        if "error" not in j2 and j2.get("routes"):
            r = j2["routes"][0]
            segments.extend(r.get("segments",[]))
            total_time_mins += int(r['time'].replace('~','').replace(' mins',''))
            total_dist_km += float(r['distance'].replace(' km',''))
            if 'stations' in r: stations.extend(r['stations'])
        else:
            w_coords, w_d, w_t = _get_walk_segment(s_end['lat'], s_end['lon'], dest_lat, dest_lon)
            if w_coords:
                segments.append({'type': 'walk', 'coords': w_coords, 'label': f'Walk to dest', 'color': '#7f8c8d'})
                total_time_mins += int(w_t/60)
                total_dist_km += w_d/1000
    else:
        w_coords, w_d, w_t = _get_walk_segment(s_end['lat'], s_end['lon'], dest_lat, dest_lon)
        if w_coords:
            segments.append({'type': 'walk', 'coords': w_coords, 'label': f'Walk to dest', 'color': '#7f8c8d'})
            total_time_mins += int(w_t/60)
            total_dist_km += w_d/1000

    # Compile the full map polyline path
    all_coords = []
    for seg in segments:
        if seg['type'] == 'train':
            for t_seg in seg['coords']: all_coords.extend(t_seg)
        else:
            all_coords.extend(seg['coords'])

    return {"routes":[{
        "id": 0,
        "name": f"Combined via {t_meta['label']}",
        "type": "multimodal",
        "color": "#9b59b6",
        "time": f"~{total_time_mins} mins",
        "distance": f"{total_dist_km:.1f} km",
        "coords": all_coords,
        "segments": segments,
        "stations": stations,
        "safety_score": 85,
        "hazards_flagged": "Multiple transfers required",
    }]}


# ── 7. Public API — get_navigation_data() ────────────────────────────────────
#
#  Dispatcher: maps commuter_type (from frontend) to the right function.
#  Train types are matched first — do NOT reorder those checks.

# All frontend values that should trigger train routing
_TRAIN_TYPES = {"lrt-1", "lrt-2", "mrt-3", "pnr", "mrt-7"}

# Per-line display metadata
_TRAIN_META = {
    "lrt-1": {"color": "#008000", "label": "LRT-1 (Green Line)"},
    "lrt-2": {"color": "#0000CD", "label": "LRT-2 (Blue Line)"},
    "mrt-3": {"color": "#DAA520", "label": "MRT-3 (Yellow Line)"},
    "pnr":   {"color": "#8B4513", "label": "PNR (Commuter Rail)"},
    "mrt-7": {"color": "#800080", "label": "MRT-7"},
}


def get_navigation_data(orig_lon, orig_lat, dest_lon, dest_lat, commuter_type, flood_zones):
    ctype = commuter_type.lower().strip()

    # 1. TRANSIT -> Routes completely through the smart multimodal engine
    if ctype == "transit":
        return plan_multimodal_journey(orig_lon, orig_lat, dest_lon, dest_lat)

    # 2. WALK -> Dedicated OSRM foot routing
    if ctype == "walk":
        return get_walk_route(orig_lon, orig_lat, dest_lon, dest_lat)

    # 3. MOTORCYCLE -> Dedicated OSRM routing
    if ctype == "motorcycle":
        return get_motorcycle_route(orig_lon, orig_lat, dest_lon, dest_lat)

    # 4. CAR (Default) -> Dedicated OSRM driving
    return get_car_route(orig_lon, orig_lat, dest_lon, dest_lat)