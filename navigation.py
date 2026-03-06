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

# ── helpers ───────────────────────────────────────────────────────────────────

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


def _closest_dist_sq(line, lat, lon):
    idx = _closest_idx(line, lat, lon)
    return idx, _dist_sq(line[idx][0], line[idx][1], lat, lon)


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
    """
    Return ALL connected polylines from segments.
    Each disconnected group (e.g. an extension not yet joined in OSM)
    becomes its own entry instead of being silently dropped.
    """
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

# ── main train function ───────────────────────────────────────────────────────

def get_osm_railway_geometry(user_input, orig_lat, orig_lon, dest_lat, dest_lon):
    """
    1. Fetch all track-way geometry for the line.
    2. Chain into connected components (handles gaps in OSM data).
    3. Find which component the origin is on, and which the destination is on.
    4. If same component: trim normally between the two snap points.
       If different components: trim origin-component from snap→its terminus,
       trim dest-component from its terminus→snap, return both segments so
       the full A-to-B path is drawn even across OSM gaps.
    """
    name = _osm_name(user_input)
    print(f"[railway] Fetching track for: {name}")

    query = f"""
[out:json][timeout:25];
(
  way["railway"~"rail|light_rail|subway"]["name"~"{name}",i](14.2,120.9,14.8,121.2);
  way["railway"~"rail|light_rail|subway"]["ref"~"{name}",i](14.2,120.9,14.8,121.2);
);
out geom;
"""
    data = _overpass_query(query)
    if not data:
        print("[railway] Could not reach Overpass after all retries.")
        return None

    segments = [
        [[pt['lat'], pt['lon']] for pt in el['geometry']]
        for el in data.get('elements', [])
        if el.get('type') == 'way' and 'geometry' in el
    ]

    if not segments:
        print("[railway] No track segments returned.")
        return None

    # Build all connected components
    components = _chain_all(segments)

    # For each component, find the closest point to origin and destination
    def best_snap(lat, lon):
        best_comp, best_idx, best_d = 0, 0, float('inf')
        for ci, comp in enumerate(components):
            idx, d = _closest_dist_sq(comp, lat, lon)
            if d < best_d:
                best_comp, best_idx, best_d = ci, idx, d
        return best_comp, best_idx, best_d

    orig_ci, orig_idx, orig_d = best_snap(orig_lat, orig_lon)
    dest_ci, dest_idx, dest_d = best_snap(dest_lat, dest_lon)

    print(f"[railway] Origin  -> component {orig_ci}, idx {orig_idx} "
          f"({orig_d**0.5*111:.2f} km from track)")
    print(f"[railway] Destination -> component {dest_ci}, idx {dest_idx} "
          f"({dest_d**0.5*111:.2f} km from track)")

    result_segments = []

    if orig_ci == dest_ci:
        # Same component — just trim between the two snap points
        comp = components[orig_ci]
        si, ei = orig_idx, dest_idx
        if si > ei:
            si, ei = ei, si
        trimmed = comp[si: ei + 1]
        print(f"[railway] Same component: trimmed idx {si}->{ei} ({len(trimmed)} pts)")
        result_segments.append(trimmed)

    else:
        # Different components — route spans an OSM gap.
        # Draw origin-component from snap to its nearest terminus toward the dest,
        # then dest-component from its nearest terminus toward the origin to snap.
        orig_comp = components[orig_ci]
        dest_comp = components[dest_ci]

        # Pick the terminus of orig_comp that is geographically closest to the dest
        d_orig_start = _dist_sq(orig_comp[0][0],  orig_comp[0][1],  dest_lat, dest_lon)
        d_orig_end   = _dist_sq(orig_comp[-1][0], orig_comp[-1][1], dest_lat, dest_lon)
        if d_orig_end < d_orig_start:
            # dest is toward the end — slice orig_idx..end
            seg1 = orig_comp[orig_idx:]
        else:
            # dest is toward the start — slice start..orig_idx (reversed so it goes away from origin)
            seg1 = orig_comp[:orig_idx + 1]

        # Pick the terminus of dest_comp that is geographically closest to the origin
        d_dest_start = _dist_sq(dest_comp[0][0],  dest_comp[0][1],  orig_lat, orig_lon)
        d_dest_end   = _dist_sq(dest_comp[-1][0], dest_comp[-1][1], orig_lat, orig_lon)
        if d_dest_start < d_dest_end:
            # origin is toward the start — slice start..dest_idx
            seg2 = dest_comp[:dest_idx + 1]
        else:
            # origin is toward the end — slice dest_idx..end
            seg2 = dest_comp[dest_idx:]

        print(f"[railway] Gap route: segment1={len(seg1)} pts, segment2={len(seg2)} pts")

        if len(seg1) >= 2:
            result_segments.append(seg1)
        if len(seg2) >= 2:
            result_segments.append(seg2)

    if not result_segments:
        print("[railway] No valid segments to display.")
        return None

    return result_segments

# ── public API ────────────────────────────────────────────────────────────────

def get_navigation_data(orig_lon, orig_lat, dest_lon, dest_lat, commuter_type, flood_zones):
    is_train = any(x in commuter_type.lower() for x in ["train", "lrt", "mrt", "pnr", "rail"])

    if is_train:
        segs = get_osm_railway_geometry(commuter_type, orig_lat, orig_lon, dest_lat, dest_lon)
        if not segs:
            return {"error": f"Could not find track for '{commuter_type}'. "
                             "The line may be unavailable in OSM right now."}
        routes = [{
            "id": 0, "name": f"{commuter_type} Route", "type": "train",
            "color": "#8e44ad", "time": "N/A", "distance": "N/A",
            "coords": segs, "safety_score": 95, "hazards_flagged": "Clear",
        }]
        return {"routes": routes}

    # ── road routing ──
    osrm = (f"https://router.project-osrm.org/route/v1/driving/"
            f"{orig_lon},{orig_lat};{dest_lon},{dest_lat}"
            f"?overview=full&geometries=geojson&alternatives=true&steps=true")
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
            "id": i, "name": f"Route {i+1} (Road)", "type": "road",
            "color": colors[i],
            "time": f"{int(route['duration'] / 60)} mins",
            "distance": f"{round(route['distance'] / 1000, 1)} km",
            "coords": coords, "safety_score": 80, "hazards_flagged": "Clear",
        })

    return {"routes": routes}