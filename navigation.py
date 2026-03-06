import requests
import time

# ── Overpass retry ────────────────────────────────────────────────────────────

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

# ── Helpers ───────────────────────────────────────────────────────────────────

def geocode_location(address):
    if "," in address:
        try:
            parts = [x.strip() for x in address.split(',')]
            lat, lon = float(parts[0]), float(parts[1])
            return (lon, lat) if lon > 100 else (lat, lon)
        except (ValueError, TypeError):
            pass
    url = f"https://nominatim.openstreetmap.org/search?q={address}&format=json&limit=1&countrycodes=ph"
    try:
        resp = requests.get(url, headers={'User-Agent': 'SafeRoute/1.0'}, timeout=10).json()
        if resp:
            return float(resp[0]['lon']), float(resp[0]['lat'])
    except Exception as e:
        print(f"Geocoding failed: {e}")
    return None, None


def _dist_sq(lat1, lon1, lat2, lon2):
    return (lat1 - lat2) ** 2 + (lon1 - lon2) ** 2


def _closest_idx(line, lat, lon):
    return min(range(len(line)), key=lambda i: _dist_sq(line[i][0], line[i][1], lat, lon))


def _chain_one(segments, start_idx, used):
    """Build one connected polyline from segments, starting at start_idx."""
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

# ── OSM line name resolver ────────────────────────────────────────────────────

def _osm_name(user_input):
    key = user_input.lower().replace(" ", "").replace("-", "")
    return {
        "lrt1": "Line 1", "line1": "Line 1",
        "lrt2": "Line 2", "line2": "Line 2",
        "mrt3": "Line 3", "mrt":   "Line 3", "line3": "Line 3",
        "mrt7": "Line 7", "line7": "Line 7",
        "pnr":  "PNR",
        "subway": "Metro Manila Subway",
    }.get(key, user_input)

# ── Station extractor from OSM relation members ───────────────────────────────

_STOP_ROLES = {'stop', 'stop_entry_only', 'stop_exit_only'}
_STATION_RAILWAY_TAGS = {'station', 'stop', 'halt', 'tram_stop', 'subway_entrance'}

def _extract_relation_data(relation):
    """
    Pull ordered stops and way geometry from a single OSM route relation.
    Returns (stops_list, way_segments_list).
    Stops are in OSM member order — which matches the line's physical sequence.
    """
    stops = []
    ways  = []
    seen_stop_refs = set()

    for member in relation.get('members', []):
        mtype = member.get('type')
        role  = member.get('role', '')

        if mtype == 'node':
            tags = member.get('tags', {})
            is_stop = (
                role in _STOP_ROLES or
                tags.get('railway') in _STATION_RAILWAY_TAGS or
                tags.get('public_transport') in ('stop_position', 'station')
            )
            # Skip platforms — they're duplicate positional data
            if role == 'platform' or tags.get('public_transport') == 'platform':
                continue
            ref = member.get('ref') or f"{member.get('lat')},{member.get('lon')}"
            if is_stop and ref not in seen_stop_refs:
                seen_stop_refs.add(ref)
                station_name = (
                    tags.get('name') or
                    tags.get('name:en') or
                    tags.get('ref') or
                    'Station'
                )
                stops.append({
                    'lat':  member['lat'],
                    'lon':  member['lon'],
                    'name': station_name,
                })

        elif mtype == 'way' and 'geometry' in member:
            ways.append([[pt['lat'], pt['lon']] for pt in member['geometry']])

    return stops, ways

# ── Main train routing function ───────────────────────────────────────────────

def get_osm_railway_geometry(user_input, orig_lat, orig_lon, dest_lat, dest_lon):
    """
    1. Fetch OSM route relation(s) for the line.
       Relations contain stops IN ORDER as member nodes — this is authoritative.
    2. Pick the relation (direction) whose stop sequence covers both endpoints.
    3. Snap origin & destination to their nearest station.
    4. Slice the ordered station list between those two snapped stations.
    5. Trim the chained track between the first and last station in that slice.
    6. Return track_segments (for the polyline) + stations (for map pins).
    """
    name = _osm_name(user_input)
    print(f"[railway] Querying OSM route relation for: {name}")

    # ── Step 1: Fetch route relation(s) ──────────────────────────────────────
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

    # ── Step 2: Extract stops & ways from every relation ─────────────────────
    candidates = []
    all_ways = []
    for rel in relations:
        stops, ways = _extract_relation_data(rel)
        all_ways.extend(ways)
        if len(stops) >= 2:
            candidates.append((stops, ways, rel.get('tags', {})))
            print(f"[railway]   Relation '{rel.get('tags', {}).get('name', '?')}' "
                  f"-> {len(stops)} stops, {len(ways)} ways")

    if not candidates:
        print("[railway] No relations with usable stops found.")
        return None

    # ── Step 3: Pick the best relation for this trip ──────────────────────────
    # Score: minimise the distance from origin to its nearest stop  +
    #        distance from dest to its nearest stop.
    # The relation whose stops are physically closest to both endpoints wins.
    def score_candidate(stops):
        o_d = min(_dist_sq(s['lat'], s['lon'], orig_lat, orig_lon) for s in stops)
        d_d = min(_dist_sq(s['lat'], s['lon'], dest_lat, dest_lon) for s in stops)
        return o_d + d_d

    best_stops, _, _ = min(candidates, key=lambda c: score_candidate(c[0]))

    # Merge all ways for a complete track (avoids gaps from one direction only)
    seen_keys = set()
    unique_ways = []
    for seg in all_ways:
        key = (round(seg[0][0], 5), round(seg[0][1], 5),
               round(seg[-1][0], 5), round(seg[-1][1], 5))
        rkey = (key[2], key[3], key[0], key[1])
        if key not in seen_keys and rkey not in seen_keys:
            seen_keys.add(key)
            unique_ways.append(seg)

    print(f"[railway] Using {len(best_stops)} ordered stops, "
          f"{len(unique_ways)} unique way segments.")

    # ── Step 4: Snap origin & destination to nearest station ──────────────────
    def nearest_stop_idx(lat, lon, stops):
        return min(
            range(len(stops)),
            key=lambda i: _dist_sq(stops[i]['lat'], stops[i]['lon'], lat, lon)
        )

    orig_si = nearest_stop_idx(orig_lat, orig_lon, best_stops)
    dest_si = nearest_stop_idx(dest_lat, dest_lon, best_stops)

    print(f"[railway] Origin  snapped -> '{best_stops[orig_si]['name']}' (idx {orig_si})")
    print(f"[railway] Dest    snapped -> '{best_stops[dest_si]['name']}' (idx {dest_si})")

    if orig_si == dest_si:
        print("[railway] Origin and destination snap to the same station.")
        return None

    # ── Step 5: Slice the ordered station list ────────────────────────────────
    si, ei = min(orig_si, dest_si), max(orig_si, dest_si)
    route_stops = best_stops[si: ei + 1]
    print(f"[railway] Route covers {len(route_stops)} stations: "
          f"'{route_stops[0]['name']}' → '{route_stops[-1]['name']}'")

    # ── Step 6: Build track trimmed to first → last station ───────────────────
    track_segments = []
    if unique_ways:
        components = _chain_all(unique_ways)
        main_track = max(components, key=len)

        if len(main_track) >= 2:
            def snap_track(lat, lon):
                return min(
                    range(len(main_track)),
                    key=lambda i: _dist_sq(main_track[i][0], main_track[i][1], lat, lon)
                )
            t_start = snap_track(route_stops[0]['lat'],  route_stops[0]['lon'])
            t_end   = snap_track(route_stops[-1]['lat'], route_stops[-1]['lon'])
            ts, te  = min(t_start, t_end), max(t_start, t_end)
            trimmed = main_track[ts: te + 1]
            if len(trimmed) >= 2:
                track_segments.append(trimmed)
                print(f"[railway] Track trimmed to {len(trimmed)} points.")

    return {
        'track_segments': track_segments,
        'stations': route_stops,       # ordered, snapped to real OSM station nodes
    }

# ── Public API ────────────────────────────────────────────────────────────────

def get_navigation_data(orig_lon, orig_lat, dest_lon, dest_lat, commuter_type, flood_zones):
    is_train = any(x in commuter_type.lower()
                   for x in ["train", "lrt", "mrt", "pnr", "rail", "line"])

    if is_train:
        result = get_osm_railway_geometry(
            commuter_type, orig_lat, orig_lon, dest_lat, dest_lon
        )
        if not result:
            return {"error": (
                f"Could not find route for '{commuter_type}'. "
                "The line may be missing from OSM or both stops may be the same."
            )}
        routes = [{
            "id": 0,
            "name": f"{commuter_type} Route",
            "type": "train",
            "color": "#8e44ad",
            "time": "N/A",
            "distance": "N/A",
            "coords": result['track_segments'],   # list of [lat,lon] lists
            "stations": result['stations'],        # ordered list of {lat,lon,name}
            "safety_score": 95,
            "hazards_flagged": "Clear",
        }]
        return {"routes": routes}

    # ── Road routing via OSRM ─────────────────────────────────────────────────
    osrm = (
        f"https://router.project-osrm.org/route/v1/driving/"
        f"{orig_lon},{orig_lat};{dest_lon},{dest_lat}"
        f"?overview=full&geometries=geojson&alternatives=true&steps=true"
    )
    try:
        r = requests.get(osrm, headers={'User-Agent': 'SafeRouteAI'}, timeout=10).json()
        if r.get("code") != "Ok":
            return {"error": "Could not calculate road route."}
    except Exception:
        return {"error": "Routing server is currently unavailable."}

    colors = ["#3498db", "#f1c40f", "#2ecc71"]
    routes = []
    for i, route in enumerate(r.get("routes", [])[:3]):
        coords = [[pt[1], pt[0]] for pt in route["geometry"]["coordinates"]]
        routes.append({
            "id": i,
            "name": f"Route {i+1} (Road)",
            "type": "road",
            "color": colors[i],
            "time": f"{int(route['duration'] / 60)} mins",
            "distance": f"{round(route['distance'] / 1000, 1)} km",
            "coords": coords,
            "stations": [],
            "safety_score": 80,
            "hazards_flagged": "Clear",
        })

    return {"routes": routes}