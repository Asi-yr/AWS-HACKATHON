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
    if address in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[address]

    if "," in address:
        try:
            parts = [x.strip() for x in address.split(',')]
            lat, lon = float(parts[0]), float(parts[1])
            result = (lon, lat) if lon > 100 else (lat, lon)
            _GEOCODE_CACHE[address] = result
            return result
        except (ValueError, TypeError):
            pass
    url = (
        f"https://nominatim.openstreetmap.org/search"
        f"?q={requests.utils.quote(address)}&format=json&limit=1&countrycodes=ph"
    )
    try:
        resp = requests.get(url, headers={'User-Agent': 'SafeRoute/1.0'}, timeout=10).json()
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
    return _osrm_road_route(orig_lon, orig_lat, dest_lon, dest_lat,
                            "Car", _ROUTE_COLORS["car"])


def get_bus_route(orig_lon, orig_lat, dest_lon, dest_lat):
    """
    Bus routing.
    STATUS: STUB — falls back to OSRM driving path.

    TODO (next commit):
      • Query OSM relations tagged route=bus within Metro Manila bbox
      • Filter to routes passing near both endpoints
      • Snap to bus stop nodes, return ordered stop list
      • Optional: integrate GTFS feed when available
    """
    print("[bus] STUB: using OSRM fallback")
    return _osrm_road_route(orig_lon, orig_lat, dest_lon, dest_lat,
                            "Bus", _ROUTE_COLORS["bus"])


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


def _get_road_points(jroute):
    """Return waypoint list — supports new 'roads' key and old 'stops' key."""
    return jroute.get('roads') or jroute.get('stops') or []


def _infer_travel_direction(orig_lat, orig_lon, dest_lat, dest_lon):
    """
    Return dominant travel direction: Northbound/Southbound/Eastbound/Westbound.
    Picks the axis with the larger displacement.
    """
    dlat = dest_lat - orig_lat
    dlon = dest_lon - orig_lon
    if abs(dlat) >= abs(dlon):
        return 'Northbound' if dlat > 0 else 'Southbound'
    return 'Eastbound' if dlon > 0 else 'Westbound'


def _route_is_near(jroute, orig_lat, orig_lon, dest_lat, dest_lon, threshold_m=5000):
    """
    Fast pre-filter — no OSRM, no Nominatim.

    Passes only if:
      1. traffic_flow (if set) matches the inferred user travel direction.
      2. At least one road point is within threshold_m of the origin.
      3. At least one road point (later index) is within threshold_m of dest.
    """
    flow = jroute.get('traffic_flow', '')
    if flow:
        needed = _infer_travel_direction(orig_lat, orig_lon, dest_lat, dest_lon)
        if flow != needed:
            return False

    points = _get_road_points(jroute)
    orig_near_idx = None
    dest_near_idx = None

    for i, pt in enumerate(points):
        lat = pt.get('lat')
        lon = pt.get('lon') or pt.get('lng')
        if lat is None or lon is None:
            continue
        if _haversine_m(orig_lat, orig_lon, lat, lon) <= threshold_m:
            if orig_near_idx is None:
                orig_near_idx = i
        if _haversine_m(dest_lat, dest_lon, lat, lon) <= threshold_m:
            dest_near_idx = i

    if orig_near_idx is None or dest_near_idx is None:
        return False
    return orig_near_idx < dest_near_idx


def _build_jeepney_polyline(jroute):
    """
    Build OSRM road polyline from jroute['roads'] (new format) or 'stops' (old).
    Coords are road-midpoint positions — no Nominatim.

    OSRM params:
      continue_straight=true  — no U-turns at waypoints
      approaches=curb         — correct curbside on divided roads
    """
    name = jroute['route_name']
    if name in _JEEPNEY_POLY_CACHE:
        return _JEEPNEY_POLY_CACHE[name]

    raw_points = _get_road_points(jroute)
    if len(raw_points) < 2:
        print(f"[jeepney] '{name}' has fewer than 2 road points — skipping.")
        _JEEPNEY_POLY_CACHE[name] = None
        return None

    stations  = []
    waypoints = []

    for pt in raw_points:
        lat   = pt.get('lat')
        lon   = pt.get('lon') or pt.get('lng')
        pname = pt.get('name', 'Road point')
        if lat is None or lon is None:
            print(f"[jeepney]   '{pname}' missing coords — skipped")
            continue
        stations.append({'name': pname, 'lat': lat, 'lon': lon})
        waypoints.append((lon, lat))

    if len(waypoints) < 2:
        print(f"[jeepney] Not enough valid points for '{name}'")
        _JEEPNEY_POLY_CACHE[name] = None
        return None

    flow = jroute.get('traffic_flow', '')
    print(f"[jeepney] Building '{name}' [{flow}] ({len(waypoints)} pts)...")

    wp_str     = ';'.join(f"{lon},{lat}" for lon, lat in waypoints)
    approaches = ';'.join('curb' for _ in waypoints)
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
                'stations': stations,
                'dur':      rt['duration'],
                'dist':     rt['distance'],
            }
            _JEEPNEY_POLY_CACHE[name] = result
            print(f"[jeepney] Built '{name}': {len(polyline)} pts, "
                  f"{rt['distance']/1000:.1f} km")
            return result
        else:
            print(f"[jeepney] OSRM error for '{name}': {r.get('code')}")
    except Exception as e:
        print(f"[jeepney] OSRM failed for '{name}': {e}")

    _JEEPNEY_POLY_CACHE[name] = None
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

    # ── Step 1: cheap pre-filter ──────────────────────────────────────────
    nearby = [r for r in all_routes
              if _route_is_near(r, orig_lat, orig_lon, dest_lat, dest_lon)]
    print(f"[jeepney] {len(nearby)}/{len(all_routes)} routes pass pre-filter")

    if not nearby:
        return {"error": (
            "No jeepney route found near your origin and destination. "
            "Try a different commuter type or check your locations."
        )}

    # ── Step 2 & 3: build polyline + snap, keep only valid direction ──────
    best = None

    for jroute in nearby:
        built = _build_jeepney_polyline(jroute)
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
#
#  ENTRY POINT (implement here when ready):
#
#    def plan_multimodal_journey(orig_lon, orig_lat, dest_lon, dest_lat, modes: list):
#        legs = []
#        for mode in modes:
#            # call get_osm_railway_geometry() for rail legs
#            # call get_jeepney_route() / get_bus_route() for road legs
#            # insert walk legs between transfer points
#        return {"journey_type": "multimodal", "legs": legs}
#
#  In get_navigation_data() below, route to plan_multimodal_journey() when
#  commuter_type == "multimodal" or when the frontend sends a modes list.


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

    # ── Train lines — DO NOT move or reorder this block
    if ctype in _TRAIN_TYPES or any(x in ctype for x in ["train", "rail", "lrt", "mrt", "pnr"]):
        meta   = _TRAIN_META.get(ctype, {"color": "#8e44ad", "label": commuter_type})
        result = get_osm_railway_geometry(ctype, orig_lat, orig_lon, dest_lat, dest_lon)
        if not result:
            return {"error": (
                f"Could not find route for '{commuter_type}'. "
                "The line may be missing from OSM or both stops may be the same."
            )}
        return {"routes": [{
            "id":              0,
            "name":            meta["label"],
            "type":            "train",
            "color":           meta["color"],
            "time":            "N/A",
            "distance":        "N/A",
            "coords":          result['track_segments'],
            "segments":        [],
            "stations":        result['stations'],
            "safety_score":    95,
            "hazards_flagged": "Clear",
        }]}

    # ── Jeepney: JSON-backed designated-route matching
    if ctype == "jeepney":
        return get_jeepney_route(orig_lon, orig_lat, dest_lon, dest_lat)

    if ctype == "bus":
        return get_bus_route(orig_lon, orig_lat, dest_lon, dest_lat)

    # ── Default: car / unrecognised → OSRM car routing
    return get_car_route(orig_lon, orig_lat, dest_lon, dest_lat)