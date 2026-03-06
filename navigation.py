import requests
import time

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
#  │  5. Road / Bus / Jeepney routing stubs  (line ~330)                 │
#  │  6. [FUTURE] Multi-modal connector hook (line ~400)                 │
#  │  7. Public API — get_navigation_data()  (line ~435)                 │
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

def geocode_location(address):
    if "," in address:
        try:
            parts = [x.strip() for x in address.split(',')]
            lat, lon = float(parts[0]), float(parts[1])
            return (lon, lat) if lon > 100 else (lat, lon)
        except (ValueError, TypeError):
            pass
    url = (
        f"https://nominatim.openstreetmap.org/search"
        f"?q={address}&format=json&limit=1&countrycodes=ph"
    )
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


# ── 5. Road / Bus / Jeepney P2P routing ──────────────────────────────────────
#
#  All road modes currently share the OSRM driving router.
#  Each type has its own wrapper so future mode-specific OSM relation
#  lookups can be added without touching anything above.

_OSRM_BASE    = "https://router.project-osrm.org/route/v1/driving"
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
            "stations":        [],   # road routes carry no station pins
            "safety_score":    80,
            "hazards_flagged": "Clear",
        })
    return {"routes": routes}


def get_car_route(orig_lon, orig_lat, dest_lon, dest_lat):
    """Car / private vehicle — OSRM driving."""
    return _osrm_road_route(orig_lon, orig_lat, dest_lon, dest_lat,
                            "Car", _ROUTE_COLORS["car"])


def get_jeepney_route(orig_lon, orig_lat, dest_lon, dest_lat):
    """
    Jeepney P2P routing.
    STATUS: STUB — falls back to OSRM driving path.

    TODO (next commit):
      • Query OSM relations tagged route=share_taxi / route=jeepney
        within Metro Manila bbox (same pattern as get_osm_railway_geometry)
      • Filter relations whose stops cover both endpoints
      • Snap to nearest jeepney stop nodes, return ordered stop list
    """
    print("[jeepney] STUB: using OSRM fallback")
    return _osrm_road_route(orig_lon, orig_lat, dest_lon, dest_lat,
                            "Jeepney P2P", _ROUTE_COLORS["jeepney"])


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
            "stations":        result['stations'],
            "safety_score":    95,
            "hazards_flagged": "Clear",
        }]}

    # ── Road modes
    if ctype == "jeepney":
        return get_jeepney_route(orig_lon, orig_lat, dest_lon, dest_lat)

    if ctype == "bus":
        return get_bus_route(orig_lon, orig_lat, dest_lon, dest_lat)

    # ── Default: car / unrecognised → OSRM car routing
    return get_car_route(orig_lon, orig_lat, dest_lon, dest_lat)