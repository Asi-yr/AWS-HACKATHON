import requests, time, json, math, os, concurrent.futures
from collections import defaultdict

print("[DEBUG][INIT] ═══════════════════════════════════════════════════════════════════")
print("[DEBUG][INIT] Loading navigation.py  ·  jeepney.json edition")
print("[DEBUG][INIT] ═══════════════════════════════════════════════════════════════════")
t_nav_init = time.time()

# ── Known locations atlas ────────────────────────────────────────────────────
_KNOWN = {
    "lrt monumento station":(14.654,120.983),"monumento":(14.654,120.983),
    "baclaran church":(14.532,120.993),"baclaran":(14.532,120.993),
    "araneta center":(14.619,121.053),"cubao":(14.619,121.053),
    "sm fairview":(14.734,121.057),"fairview":(14.734,121.057),
    "quiapo church":(14.598,120.983),"quiapo":(14.598,120.983),
    "novaliches public market":(14.723,121.038),
    "divisoria market":(14.603,120.968),"divisoria":(14.603,120.968),
    "alabang town center":(14.425,121.027),"alabang":(14.417,121.043),
    "pitx terminal":(14.511,120.992),"pitx":(14.511,120.992),
    "edsa-taft":(14.537,121.001),"pasay rotunda":(14.537,121.001),
    "antipolo cathedral":(14.587,121.176),"antipolo":(14.587,121.176),
    "marikina public market":(14.633,121.096),
    "las pinas city hall":(14.446,120.993),
    "valenzuela city hall":(14.695,120.973),
    "bocaue public market":(14.796,120.925),
    "valenzuela gateway complex":(14.712,120.989),"vgc":(14.712,120.989),
    "malanday terminal":(14.715,120.954),
    "sm mall of asia":(14.535,120.982),"moa":(14.535,120.982),
    "sm north edsa":(14.656,121.028),"trinoma":(14.653,121.033),
    "market! market!":(14.549,121.055),"bgc":(14.549,121.055),
    "fti terminal":(14.511,121.038),
    "navotas bus terminal":(14.647,120.952),
    "ayala center":(14.550,121.025),"ayala":(14.550,121.025),
    "pacita complex":(14.345,121.056),"starmall alabang":(14.416,121.043),
    "tungkong mangga":(14.778,121.072),"sjdm":(14.814,121.045),
    "sucat interchange":(14.449,121.047),
    "lawton plaza":(14.594,120.980),"lawton":(14.594,120.980),
    "taytay public market":(14.566,121.135),
    "montalban town center":(14.733,121.125),
    "sm megamall":(14.584,121.056),
    "robinsons place antipolo":(14.591,121.173),
    "glorietta":(14.551,121.025),"naia terminal 3":(14.517,121.017),
    "meycauayan public market":(14.736,120.958),"malinta":(14.691,120.967),
    "commonwealth avenue":(14.666,121.066),"shaw boulevard":(14.587,121.045),
    "mall of asia arena":(14.533,120.984),
}

# ── Overpass endpoints ───────────────────────────────────────────────────────
_OVERPASS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]

def _overpass_query(query, max_retries=5, timeout=30):
    fn = "_overpass_query"
    t_start = time.time()
    print(f"[DEBUG][{fn}] ── START ────────────────────────────────────────────────")
    print(f"[DEBUG][{fn}] max_retries={max_retries}  timeout={timeout}s  payload={len(query)}chars")

    for attempt in range(max_retries):
        ep = _OVERPASS[attempt % len(_OVERPASS)]
        print(f"[DEBUG][{fn}] Attempt {attempt+1}/{max_retries} → endpoint: {ep}")
        try:
            t_req = time.time()
            r = requests.post(ep, data=query,
                              headers={'User-Agent': 'SafeRoute/1.0'}, timeout=timeout)
            print(f"[DEBUG][{fn}]   HTTP {r.status_code} in {time.time()-t_req:.3f}s")
            r.raise_for_status()
            res_json = r.json()
            el_count = len(res_json.get('elements', []))
            print(f"[DEBUG][{fn}]   JSON parsed OK  elements={el_count}  total={time.time()-t_start:.3f}s")
            return res_json
        except Exception as e:
            print(f"[DEBUG][{fn}]   !! Exception on attempt {attempt+1}: {e}")
        if attempt < max_retries - 1:
            sleep_s = 2 * (attempt + 1)
            print(f"[DEBUG][{fn}]   Sleeping {sleep_s}s before retry...")
            time.sleep(sleep_s)

    print(f"[DEBUG][{fn}] !! All {max_retries} attempts failed  elapsed={time.time()-t_start:.3f}s")
    return None

# ── Geocoding ─────────────────────────────────────────────────────────────────
_GEOCODE_CACHE = {}
_OSRM_DIST_CACHE = {}

def geocode_location(address):
    fn = "geocode_location"
    t_start = time.time()
    print(f"[DEBUG][{fn}] Geocoding: '{address}'")
    if address in _GEOCODE_CACHE:
        print(f"[DEBUG][{fn}]   Cache HIT → {_GEOCODE_CACHE[address]}")
        return _GEOCODE_CACHE[address]

    clean = address.lower().strip()
    for key, coords in _KNOWN.items():
        if key in clean:
            r = (coords[1], coords[0])
            _GEOCODE_CACHE[address] = r
            print(f"[DEBUG][{fn}]   Atlas match '{key}' → {r}  elapsed={time.time()-t_start:.3f}s")
            return r

    if "," in address:
        print(f"[DEBUG][{fn}]   Attempting raw coordinate parse...")
        try:
            parts = [x.strip() for x in address.split(',')]
            lat, lon = float(parts[0]), float(parts[1])
            r = (lon, lat) if lon > 100 else (lat, lon)
            _GEOCODE_CACHE[address] = r
            print(f"[DEBUG][{fn}]   Raw coords parsed → {r}  elapsed={time.time()-t_start:.3f}s")
            return r
        except (ValueError, TypeError) as e:
            print(f"[DEBUG][{fn}]   Raw parse failed: {e}")

    print(f"[DEBUG][{fn}]   Falling back to Nominatim API (rate-limit sleep 1.1s)...")
    time.sleep(1.1)
    url = (f"https://nominatim.openstreetmap.org/search"
           f"?q={requests.utils.quote(address)}&format=json&limit=1&countrycodes=ph")
    try:
        t_req = time.time()
        r = requests.get(url, headers={'User-Agent': 'SafeRouteAI/1.0'}, timeout=5)
        print(f"[DEBUG][{fn}]   Nominatim responded HTTP {r.status_code} in {time.time()-t_req:.3f}s")
        if r.status_code == 200:
            data = r.json()
            if data:
                result = float(data[0]['lon']), float(data[0]['lat'])
                _GEOCODE_CACHE[address] = result
                print(f"[DEBUG][{fn}]   Nominatim hit → {result}  total={time.time()-t_start:.3f}s")
                return result
            print(f"[DEBUG][{fn}]   Nominatim returned empty array")
    except Exception as e:
        print(f"[DEBUG][{fn}]   Nominatim exception: {e}")

    print(f"[DEBUG][{fn}]   !! Geocoding failed entirely  elapsed={time.time()-t_start:.3f}s")
    _GEOCODE_CACHE[address] = (None, None)
    return None, None

# ════════════════════════════════════════════════════════════════════════════════
#  GEOMETRY UTILITIES
# ════════════════════════════════════════════════════════════════════════════════

def _hav(la1, lo1, la2, lo2):
    """Haversine distance in metres."""
    R = 6_371_000
    f1, f2 = math.radians(la1), math.radians(la2)
    df = math.radians(la2 - la1)
    dl = math.radians(lo2 - lo1)
    a = math.sin(df/2)**2 + math.cos(f1) * math.cos(f2) * math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

_haversine_m = _hav

def _dsq(la1, lo1, la2, lo2):
    return (la1 - la2)**2 + (lo1 - lo2)**2

def _poly_dist(poly):
    if len(poly) < 2:
        return 0.0
    return sum(_hav(poly[i][0], poly[i][1], poly[i+1][0], poly[i+1][1])
               for i in range(len(poly) - 1))

def _closest_idx(line, lat, lon):
    if not line:
        return 0
    return min(range(len(line)), key=lambda i: _dsq(line[i][0], line[i][1], lat, lon))

def _chain_one(segs, start, used):
    ep = {}
    for i, s in enumerate(segs):
        ep[tuple(s[0])] = ('start', i)
        ep[tuple(s[-1])] = ('end', i)
    path = list(segs[start])
    used.add(start)
    while True:
        grew = False
        m = ep.get(tuple(path[-1]))
        if m and m[1] not in used:
            side, idx = m
            s = segs[idx]
            path.extend(s[1:] if side == 'start' else list(reversed(s[:-1])))
            used.add(idx)
            grew = True
        if not grew:
            m = ep.get(tuple(path[0]))
            if m and m[1] not in used:
                side, idx = m
                s = segs[idx]
                path = (s[:-1] + path) if side == 'end' else (list(reversed(s[1:])) + path)
                used.add(idx)
                grew = True
        if not grew:
            break
    return path

def _chain_all(segs):
    fn = "_chain_all"
    t_start = time.time()
    print(f"[DEBUG][{fn}] Chaining {len(segs)} segments...")
    used = set()
    out = []
    for i in range(len(segs)):
        if i not in used:
            out.append(_chain_one(segs, i, used))
    print(f"[DEBUG][{fn}] {len(segs)} segments → {len(out)} chains  elapsed={time.time()-t_start:.3f}s")
    return out

def _proj_point_on_segment(plat, plon, alat, alon, blat, blon):
    """
    Project point P onto segment A→B.
    Returns (t, proj_lat, proj_lon, dist_m).
      t=0  ⟹ closest point is A
      t=1  ⟹ closest point is B
      0<t<1 ⟹ somewhere along the segment
    Uses flat-earth approximation (accurate within ±0.5% for distances < 50 km).
    """
    abx, aby = blon - alon, blat - alat
    apx, apy = plon - alon, plat - alat
    ab_sq = abx * abx + aby * aby
    if ab_sq < 1e-14:                      # degenerate segment (A == B)
        return 0.0, alat, alon, _hav(plat, plon, alat, alon)
    t = (apx * abx + apy * aby) / ab_sq
    t = max(0.0, min(1.0, t))
    proj_lat = alat + t * (blat - alat)
    proj_lon = alon + t * (blon - alon)
    dist = _hav(plat, plon, proj_lat, proj_lon)
    return t, proj_lat, proj_lon, dist

def _osrm_walk_dist(la1, lo1, la2, lo2, timeout=5):
    fn = "_osrm_walk_dist"
    t_start = time.time()
    url = f"https://router.project-osrm.org/route/v1/foot/{lo1},{la1};{lo2},{la2}?overview=false"
    print(f"[DEBUG][{fn}] Fetching walk distance  {la1:.5f},{lo1:.5f} → {la2:.5f},{lo2:.5f}")
    try:
        t_req = time.time()
        resp = requests.get(url, timeout=timeout).json()
        print(f"[DEBUG][{fn}]   OSRM responded in {time.time()-t_req:.3f}s  code={resp.get('code')}")
        if resp.get('code') == 'Ok' and resp.get('routes'):
            d = resp['routes'][0].get('distance')
            if d:
                print(f"[DEBUG][{fn}]   Walk dist={int(d)}m  total={time.time()-t_start:.3f}s")
                return int(d)
    except Exception as e:
        print(f"[DEBUG][{fn}]   !! Exception: {e}")
    print(f"[DEBUG][{fn}]   !! Failed to get walk dist  elapsed={time.time()-t_start:.3f}s")
    return None

def _osrm_walk_dist_cached(la1, lo1, la2, lo2):
    key = (round(la1, 4), round(lo1, 4), round(la2, 4), round(lo2, 4))
    if key not in _OSRM_DIST_CACHE:
        _OSRM_DIST_CACHE[key] = _osrm_walk_dist(la1, lo1, la2, lo2)
    return _OSRM_DIST_CACHE[key]

def _osm_name(s):
    k = s.lower().replace(" ", "").replace("-", "")
    return {"lrt1": "Line 1", "line1": "Line 1", "lrt2": "Line 2", "line2": "Line 2",
            "mrt3": "Line 3", "mrt": "Line 3", "line3": "Line 3",
            "mrt7": "Line 7", "line7": "Line 7",
            "pnr": "PNR", "subway": "Metro Manila Subway"}.get(k, s)

# ── OSRM foot fetcher ─────────────────────────────────────────────────────────
def _fetch_osrm_foot(olon, olat, dlon, dlat):
    fn = "_fetch_osrm_foot"
    t_start = time.time()
    print(f"[DEBUG][{fn}] Pedestrian route  ({olat:.5f},{olon:.5f}) → ({dlat:.5f},{dlon:.5f})")
    hdrs = {'User-Agent': 'SafeRouteAI/1.0'}
    urls = [
        f"https://routing.openstreetmap.de/routed-foot/route/v1/driving/{olon},{olat};{dlon},{dlat}?overview=full&geometries=geojson&alternatives=3",
        f"https://router.project-osrm.org/route/v1/foot/{olon},{olat};{dlon},{dlat}?overview=full&geometries=geojson&alternatives=3",
    ]
    for idx, url in enumerate(urls):
        print(f"[DEBUG][{fn}]   Trying URL {idx+1}/{len(urls)}: {url[:80]}...")
        try:
            t_req = time.time()
            r = requests.get(url, headers=hdrs, timeout=10).json()
            print(f"[DEBUG][{fn}]   URL {idx+1} responded in {time.time()-t_req:.3f}s  code={r.get('code')}")
            if r.get('code') == 'Ok' and r.get('routes'):
                print(f"[DEBUG][{fn}]   OK  routes={len(r['routes'])}  total={time.time()-t_start:.3f}s")
                return r
        except Exception as e:
            print(f"[DEBUG][{fn}]   URL {idx+1} failed: {e}")
    print(f"[DEBUG][{fn}]   !! All OSRM foot URLs failed  elapsed={time.time()-t_start:.3f}s")
    return None

def _walk_seg(from_lat, from_lon, to_lat, to_lon, label):
    fn = "_walk_seg"
    straight = _hav(from_lat, from_lon, to_lat, to_lon)
    if straight < 5:
        return None, 0, 0
    if straight < 80:
        c = [[from_lat, from_lon], [to_lat, to_lon]]
        return {'type': 'walk', 'coords': c, 'color': '#7f8c8d', 'label': label}, straight, straight / 1.2
    r = _fetch_osrm_foot(from_lon, from_lat, to_lon, to_lat)
    if r:
        rt = r['routes'][0]
        if rt['distance'] <= straight * 2.5 or straight <= 50:
            c = [[p[1], p[0]] for p in rt['geometry']['coordinates']]
            return {'type': 'walk', 'coords': c, 'color': '#7f8c8d', 'label': label}, rt['distance'], rt['duration']
    c = [[from_lat, from_lon], [to_lat, to_lon]]
    return {'type': 'walk', 'coords': c, 'color': '#7f8c8d', 'label': label}, straight, straight / 1.2


# ════════════════════════════════════════════════════════════════════════════════
#  JEEPNEY DATA LOADER  (jeepney.json — Primary Jeepney Data Source)
#
#  Schema:  { "routes": [ { "route_transit": "...", "start": {lat,lon},
#                            "destination": {lat,lon} }, ... ] }
#
#  Philosophy:
#    1. Load JSON + build spatial index → pure Python math, ZERO OSM calls.
#    2. Match user origin/destination to candidate routes → pure lat/lon geometry.
#    3. Only AFTER candidates are selected do we call OSRM for road polylines.
# ════════════════════════════════════════════════════════════════════════════════

_JEEPNEY_READY   = False
_JEEPNEY_ROUTES  = {}           # rid  →  route-dict
_JEEPNEY_PUJ     = []           # ordered list of PUJ_* route IDs

# Spatial index: (lat_cell, lon_cell) → [(rid, point_tag, lat, lon)]
# Indexed at: start, destination, and N intermediate sample points per route.
_JEEPNEY_SPATIAL = defaultdict(list)
_JEEPNEY_CELL    = 0.008        # ~890 m per cell
_JEEPNEY_SAMPLES = 5            # intermediate line-sample points per route

# Distance thresholds (metres)
_JBOARD_LIM  = 1000             # max walk from user to board point on route (was 800)
_JALIGHT_LIM = 1200             # max walk from alight point to user destination (was 950)
_JXFER_LIM   = 800              # max walk for a jeepney→jeepney transfer (was 600)
_JXFER_PEN   = 300              # transfer penalty (added to candidate score)


def _find_file(*names):
    fn = "_find_file"
    t_start = time.time()
    base = os.path.dirname(os.path.abspath(__file__))
    cwd  = os.getcwd()
    search_dirs = [
        os.path.join(base, 'map_transit'), base,
        os.path.join(cwd,  'map_transit'), cwd,
    ]
    print(f"[DEBUG][{fn}] Searching for {names} across {len(search_dirs)} dirs...")
    for name in names:
        for d in search_dirs:
            p = os.path.join(d, name)
            if os.path.exists(p):
                print(f"[DEBUG][{fn}]   Found '{name}' at: {p}  elapsed={time.time()-t_start:.3f}s")
                return p
    print(f"[DEBUG][{fn}]   !! None of {names} found  elapsed={time.time()-t_start:.3f}s")
    return None


def _load_jeepney():
    """
    Load jeepney.json, parse routes, build spatial index.
    Entirely local computation — no network calls.
    """
    fn = "_load_jeepney"
    global _JEEPNEY_READY
    t_start = time.time()
    print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
    print(f"[DEBUG][{fn}] CALL: _load_jeepney()  _JEEPNEY_READY={_JEEPNEY_READY}")

    if _JEEPNEY_READY:
        print(f"[DEBUG][{fn}] Already initialised — skipping  elapsed={time.time()-t_start:.3f}s")
        print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
        return

    # STEP 1 — locate the file
    print(f"[DEBUG][{fn}] STEP 1 · Locating jeepney.json...")
    t1 = time.time()
    jpath = _find_file('jeepney.json')
    print(f"[DEBUG][{fn}] STEP 1 · Done  path={jpath}  elapsed={time.time()-t1:.3f}s")

    if not jpath:
        print(f"[DEBUG][{fn}] !! jeepney.json NOT FOUND — jeepney routing unavailable")
        _JEEPNEY_READY = True
        print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
        return

    # STEP 2 — parse (multithreaded route object construction)
    print(f"[DEBUG][{fn}] STEP 2 · Parsing jeepney.json (multithreaded)...")
    t2 = time.time()
    _parse_jeepney(jpath)
    print(f"[DEBUG][{fn}] STEP 2 · Done  routes_loaded={len(_JEEPNEY_ROUTES)}  elapsed={time.time()-t2:.3f}s")

    # STEP 3 — build spatial index (multithreaded)
    print(f"[DEBUG][{fn}] STEP 3 · Building spatial index (multithreaded)...")
    t3 = time.time()
    _build_jeepney_spatial()
    cells = len(_JEEPNEY_SPATIAL)
    entries = sum(len(v) for v in _JEEPNEY_SPATIAL.values())
    print(f"[DEBUG][{fn}] STEP 3 · Done  cells={cells}  indexed_entries={entries}  elapsed={time.time()-t3:.3f}s")

    _JEEPNEY_READY = True
    print(f"[DEBUG][{fn}] ✓ READY: {len(_JEEPNEY_ROUTES)} jeepney routes indexed "
          f"({len(_JEEPNEY_PUJ)} PUJ IDs)")
    print(f"[DEBUG][{fn}] TOTAL INIT TIME={time.time()-t_start:.3f}s")
    print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")


def _parse_jeepney(path):
    """
    Parse jeepney.json into _JEEPNEY_ROUTES.
    Each route gets a synthetic PUJ_NNN route_id.
    Route dict includes a 2-stop list (start & destination) for compatibility
    with _assemble_route / calc_sakay_fare.
    Multithreaded: all route objects are built in parallel.
    """
    fn = "_parse_jeepney"
    t_start = time.time()
    print(f"[DEBUG][{fn}] ── START ────────────────────────────────────────────────")
    print(f"[DEBUG][{fn}] CALL: _parse_jeepney('{path}')")

    # STEP 1 — read JSON
    print(f"[DEBUG][{fn}] STEP 1 · Reading JSON from disk...")
    t1 = time.time()
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        raw_routes = data.get('routes', [])
        print(f"[DEBUG][{fn}] STEP 1 · Loaded  raw_routes={len(raw_routes)}  elapsed={time.time()-t1:.3f}s")
    except Exception as e:
        print(f"[DEBUG][{fn}] STEP 1 · !! JSON read error: {e}")
        return

    # STEP 2 — build route dicts in parallel
    def build_route_obj(idx_and_raw):
        idx, raw = idx_and_raw
        name = raw.get('route_transit', f'Route_{idx}')
        s    = raw.get('start', {})
        d    = raw.get('destination', {})
        slat, slon = s.get('lat'), s.get('lon')
        dlat, dlon = d.get('lat'), d.get('lon')

        if None in (slat, slon, dlat, dlon):
            return None, f"idx={idx} name='{name}' missing lat/lon"

        slat, slon, dlat, dlon = float(slat), float(slon), float(dlat), float(dlon)
        rid   = f"PUJ_{idx:03d}"
        parts = name.split(' - ', 1)
        bname = parts[0].strip()
        aname = parts[-1].strip()

        route = {
            'route_id'        : rid,
            'route_transit'   : name,
            'route_long_name' : name,
            'route_type'      : 3,
            'route_color'     : '#e67e22',
            'agency_id'       : 'LTFRB',
            'shape_id'        : None,
            'start'           : {'lat': slat, 'lon': slon},
            'destination'     : {'lat': dlat, 'lon': dlon},
            # Minimal 2-stop list for compatibility with helpers that iterate stops
            'stops': [
                {'stop_id': f'{rid}_S', 'name': bname, 'lat': slat, 'lon': slon, 'seq': 0},
                {'stop_id': f'{rid}_D', 'name': aname, 'lat': dlat, 'lon': dlon, 'seq': 1},
            ],
        }
        return route, None

    print(f"[DEBUG][{fn}] STEP 2 · Spawning ThreadPoolExecutor for {len(raw_routes)} route objects...")
    t2 = time.time()
    workers = min(32, max(1, len(raw_routes)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(build_route_obj, enumerate(raw_routes)))
    print(f"[DEBUG][{fn}] STEP 2 · ThreadPool done  elapsed={time.time()-t2:.3f}s")

    # STEP 3 — merge results
    t3 = time.time()
    valid = skipped = 0
    for route, err in results:
        if err:
            print(f"[DEBUG][{fn}]   SKIP: {err}")
            skipped += 1
        elif route:
            rid = route['route_id']
            _JEEPNEY_ROUTES[rid] = route
            _JEEPNEY_PUJ.append(rid)
            valid += 1

    print(f"[DEBUG][{fn}] STEP 3 · Merged  valid={valid}  skipped={skipped}  elapsed={time.time()-t3:.3f}s")
    print(f"[DEBUG][{fn}] TOTAL PARSE TIME={time.time()-t_start:.3f}s")
    print(f"[DEBUG][{fn}] ──────────────────────────────────────────────────────────")


def _build_jeepney_spatial():
    """
    Build _JEEPNEY_SPATIAL grid index.
    Each route contributes cells for:
      • its start point
      • its destination point
      • _JEEPNEY_SAMPLES evenly-spaced intermediate points along the straight
        line from start→destination  (no OSM needed — pure linear interpolation)
    All routes processed in parallel.
    """
    fn = "_build_jeepney_spatial"
    t_start = time.time()
    print(f"[DEBUG][{fn}] ── START ────────────────────────────────────────────────")
    print(f"[DEBUG][{fn}] CALL: _build_jeepney_spatial()  routes={len(_JEEPNEY_ROUTES)}  samples_per_route={_JEEPNEY_SAMPLES}")

    _JEEPNEY_SPATIAL.clear()

    def index_one_route(rid):
        """Return list of (cell, entry_tuple) for one route."""
        route = _JEEPNEY_ROUTES[rid]
        s  = route['start']
        d  = route['destination']
        sl, sn = s['lat'], s['lon']
        dl, dn = d['lat'], d['lon']

        cells = []
        # start
        cells.append(((int(sl / _JEEPNEY_CELL), int(sn / _JEEPNEY_CELL)),
                       (rid, 'start', sl, sn)))
        # destination
        cells.append(((int(dl / _JEEPNEY_CELL), int(dn / _JEEPNEY_CELL)),
                       (rid, 'dest', dl, dn)))
        # intermediate sample points (pure linear interpolation — zero network I/O)
        for i in range(1, _JEEPNEY_SAMPLES + 1):
            t = i / (_JEEPNEY_SAMPLES + 1)
            ml = sl + t * (dl - sl)
            mn = sn + t * (dn - sn)
            cells.append(((int(ml / _JEEPNEY_CELL), int(mn / _JEEPNEY_CELL)),
                           (rid, f'mid_{i}', ml, mn)))
        return cells

    workers = min(32, max(1, len(_JEEPNEY_ROUTES)))
    print(f"[DEBUG][{fn}] STEP 1 · Spawning ThreadPoolExecutor  workers={workers}...")
    t1 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        all_cell_lists = list(ex.map(index_one_route, list(_JEEPNEY_ROUTES.keys())))
    print(f"[DEBUG][{fn}] STEP 1 · ThreadPool done  elapsed={time.time()-t1:.3f}s")

    # Merge into shared dict (single-threaded merge to avoid race conditions)
    t2 = time.time()
    total_entries = 0
    for cell_list in all_cell_lists:
        for cell, entry in cell_list:
            _JEEPNEY_SPATIAL[cell].append(entry)
            total_entries += 1

    print(f"[DEBUG][{fn}] STEP 2 · Merge done  "
          f"cells={len(_JEEPNEY_SPATIAL)}  entries={total_entries}  elapsed={time.time()-t2:.3f}s")
    print(f"[DEBUG][{fn}] TOTAL SPATIAL BUILD TIME={time.time()-t_start:.3f}s")
    print(f"[DEBUG][{fn}] ──────────────────────────────────────────────────────────")


# ════════════════════════════════════════════════════════════════════════════════
#  JEEPNEY CANDIDATE FINDER  (PURE GEOMETRY — ZERO OSM CALLS)
#
#  For each jeepney route we compute:
#    • board point   = projection of user origin  onto the route's start→dest line
#    • alight point  = projection of user dest    onto the route's start→dest line
#  A route is a valid DIRECT candidate if both distances are within thresholds
#  and the alight position (t_a) is ahead of the board position (t_b).
#
#  For TRANSFER candidates we additionally require that the first route's line
#  passes within _JXFER_LIM of the second route's start point.
# ════════════════════════════════════════════════════════════════════════════════

def _find_jeepney_candidates(orig_lat, orig_lon, dest_lat, dest_lon):
    """
    Pure-geometry route candidate finder.
    NO network / OSM calls made here.

    Returns:
        direct_cands   : list of (score, rid, board_lat, board_lon, alight_lat, alight_lon)
        transfer_cands : list of (score,
                                  rid1, board1_lat, board1_lon, xfer1_lat, xfer1_lon,
                                  rid2, board2_lat, board2_lon, alight2_lat, alight2_lon)
    Both lists are sorted ascending by score (lower = better).
    """
    fn = "_find_jeepney_candidates"
    t_start = time.time()
    print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
    print(f"[DEBUG][{fn}] CALL: _find_jeepney_candidates()")
    print(f"[DEBUG][{fn}]   Origin  = ({orig_lat:.6f}, {orig_lon:.6f})")
    print(f"[DEBUG][{fn}]   Dest    = ({dest_lat:.6f}, {dest_lon:.6f})")
    print(f"[DEBUG][{fn}]   Crow-flies distance = {_hav(orig_lat,orig_lon,dest_lat,dest_lon):.0f}m")
    print(f"[DEBUG][{fn}]   Thresholds: BOARD={_JBOARD_LIM}m  ALIGHT={_JALIGHT_LIM}m  XFER={_JXFER_LIM}m")

    if not _JEEPNEY_READY:
        print(f"[DEBUG][{fn}]   _JEEPNEY_READY=False → calling _load_jeepney() first")
        _load_jeepney()

    total_routes = len(_JEEPNEY_ROUTES)
    print(f"[DEBUG][{fn}]   Evaluating {total_routes} jeepney routes...")

    # ── STEP 1: Project origin & destination onto every route line ────────────
    print(f"[DEBUG][{fn}] STEP 1 · Computing projections for all {total_routes} routes (multithreaded)...")
    t1 = time.time()

    def compute_projections(rid):
        """Project orig & dest onto route's straight-line corridor. Returns projection tuple."""
        route = _JEEPNEY_ROUTES[rid]
        sl, sn = route['start']['lat'],       route['start']['lon']
        dl, dn = route['destination']['lat'],  route['destination']['lon']

        t_b, blat, blon, bdist = _proj_point_on_segment(orig_lat, orig_lon, sl, sn, dl, dn)
        t_a, alat, alon, adist = _proj_point_on_segment(dest_lat, dest_lon, sl, sn, dl, dn)

        return rid, sl, sn, dl, dn, t_b, blat, blon, bdist, t_a, alat, alon, adist

    workers = min(32, max(1, total_routes))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        proj_results = list(ex.map(compute_projections, list(_JEEPNEY_ROUTES.keys())))

    print(f"[DEBUG][{fn}] STEP 1 · Projections done  elapsed={time.time()-t1:.3f}s")

    # ── STEP 2: Filter direct candidates ──────────────────────────────────────
    print(f"[DEBUG][{fn}] STEP 2 · Filtering direct candidates...")
    t2 = time.time()
    direct_cands = []

    for (rid, sl, sn, dl, dn,
         t_b, blat, blon, bdist,
         t_a, alat, alon, adist) in proj_results:

        rname = _JEEPNEY_ROUTES[rid]['route_transit']

        if bdist > _JBOARD_LIM:
            continue  # origin too far from this route's corridor
        if adist > _JALIGHT_LIM:
            continue  # destination too far from this route's corridor
        if t_a <= t_b:
            continue  # destination is *behind* origin on this route (wrong direction)
        if (t_a - t_b) < 0.05:
            continue  # would ride < 5% of route — not useful

        score = bdist + adist
        direct_cands.append((score, rid, blat, blon, alat, alon))
        print(f"[DEBUG][{fn}]   ✓ DIRECT  {rid} '{rname}'")
        print(f"[DEBUG][{fn}]     board_dist={bdist:.0f}m  t_b={t_b:.3f} → board=({blat:.5f},{blon:.5f})")
        print(f"[DEBUG][{fn}]     alight_dist={adist:.0f}m  t_a={t_a:.3f} → alight=({alat:.5f},{alon:.5f})")
        print(f"[DEBUG][{fn}]     segment_coverage={t_a-t_b:.3f}  score={score:.0f}")

    direct_cands.sort(key=lambda x: x[0])
    print(f"[DEBUG][{fn}] STEP 2 · Done  direct_candidates={len(direct_cands)}  elapsed={time.time()-t2:.3f}s")

    # ── STEP 3: Build route-indexed lookup tables for transfer search ──────────
    print(f"[DEBUG][{fn}] STEP 3 · Building boardable/alightable lookup tables...")
    t3 = time.time()
    # boardable: routes where user can board from origin
    boardable = {}     # rid → (t_b, blat, blon, bdist, sl, sn, dl, dn)
    # alightable: routes where user can alight to destination
    alightable = {}    # rid → (t_a, alat, alon, adist)

    for (rid, sl, sn, dl, dn,
         t_b, blat, blon, bdist,
         t_a, alat, alon, adist) in proj_results:
        if bdist <= _JBOARD_LIM:
            boardable[rid]  = (t_b, blat, blon, bdist, sl, sn, dl, dn)
        if adist <= _JALIGHT_LIM:
            alightable[rid] = (t_a, alat, alon, adist)

    print(f"[DEBUG][{fn}] STEP 3 · boardable={len(boardable)}  alightable={len(alightable)}  elapsed={time.time()-t3:.3f}s")

    # ── STEP 4: Find transfer candidates (multithreaded) ───────────────────────
    print(f"[DEBUG][{fn}] STEP 4 · Searching for transfer candidates (multithreaded)...")
    t4 = time.time()

    def find_transfers_from(rid1):
        """
        For a boardable route1, find all alightable route2 pairs reachable via
        a transfer at the point on route1 closest to route2's start.
        Returns list of transfer candidate tuples.
        """
        if rid1 not in boardable:
            return []
        t_b1, blat1, blon1, bdist1, sl1, sn1, dl1, dn1 = boardable[rid1]
        rname1 = _JEEPNEY_ROUTES[rid1]['route_transit']
        local = []

        for rid2, (t_a2, alat2, alon2, adist2) in alightable.items():
            if rid2 == rid1:
                continue  # same route

            s2 = _JEEPNEY_ROUTES[rid2]['start']
            sl2, sn2 = s2['lat'], s2['lon']
            d2 = _JEEPNEY_ROUTES[rid2]['destination']
            dl2, dn2 = d2['lat'], d2['lon']

            # Find closest point on route1's line to route2's start
            t_xfer1, xlat1, xlon1, xfer_dist = _proj_point_on_segment(
                sl2, sn2,       # point to project = route2 start
                sl1, sn1,       # segment A = route1 start
                dl1, dn1        # segment B = route1 destination
            )
            # xfer_dist = walk distance from that point on route1 to route2 start

            if xfer_dist > _JXFER_LIM:
                continue  # transfer walk too long
            if t_xfer1 <= t_b1:
                continue  # transfer would happen before boarding point on route1
            if t_xfer1 < 0.05:
                continue  # too close to route1 start — not meaningful

            # Board route2 from the transfer walk point — project onto route2
            t_b2, blat2, blon2, bdist2 = _proj_point_on_segment(
                xlat1, xlon1,   # walk arrival point → route2 corridor
                sl2,   sn2,
                dl2,   dn2
            )
            if t_a2 <= t_b2:
                continue  # destination is behind boarding on route2

            score = bdist1 + xfer_dist + adist2 + _JXFER_PEN
            rname2 = _JEEPNEY_ROUTES[rid2]['route_transit']
            local.append((score,
                           rid1, blat1, blon1, xlat1, xlon1,
                           rid2, blat2, blon2, alat2, alon2))
            print(f"[DEBUG][{fn}]   ✓ TRANSFER  {rid1}→{rid2}")
            print(f"[DEBUG][{fn}]     '{rname1}' → '{rname2}'")
            print(f"[DEBUG][{fn}]     board1_dist={bdist1:.0f}m  xfer_dist={xfer_dist:.0f}m  "
                  f"alight2_dist={adist2:.0f}m  score={score:.0f}")
        return local

    workers = min(32, max(1, len(boardable)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        all_transfer_lists = list(ex.map(find_transfers_from, list(boardable.keys())))

    # Flatten + deduplicate by (rid1, rid2) pair
    transfer_cands = []
    seen_pairs = set()
    for transfer_list in all_transfer_lists:
        for item in transfer_list:
            pair = (item[1], item[6])   # (rid1, rid2)
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                transfer_cands.append(item)

    transfer_cands.sort(key=lambda x: x[0])
    print(f"[DEBUG][{fn}] STEP 4 · Done  transfer_candidates={len(transfer_cands)}  elapsed={time.time()-t4:.3f}s")

    print(f"[DEBUG][{fn}] ── SUMMARY ──────────────────────────────────────────────")
    print(f"[DEBUG][{fn}]   Direct candidates    : {len(direct_cands)}")
    print(f"[DEBUG][{fn}]   Transfer candidates  : {len(transfer_cands)}")
    print(f"[DEBUG][{fn}]   TOTAL DURATION       : {time.time()-t_start:.3f}s  (pure geometry — no OSM)")
    print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
    return direct_cands, transfer_cands


# ════════════════════════════════════════════════════════════════════════════════
#  JEEPNEY LEG BUILDER  (OSM / OSRM called HERE — after candidate selection)
# ════════════════════════════════════════════════════════════════════════════════

def _build_jeepney_leg(rid, board_lat, board_lon, alight_lat, alight_lon):
    """
    Given a confirmed jeepney route and its board/alight coordinates,
    call OSRM for the actual road polyline.
    This is the ONLY place in the jeepney pipeline that touches the network.

    Strategies (tried in order, first success wins):
      1. OSRM driving route  (road-accurate polyline + real distance)
      2. Straight-line fallback (crowfly)
    """
    fn = "_build_jeepney_leg"
    t_start = time.time()
    print(f"[DEBUG][{fn}] ── START ────────────────────────────────────────────────")
    print(f"[DEBUG][{fn}] CALL: _build_jeepney_leg({rid})")

    route = _JEEPNEY_ROUTES.get(rid)
    if not route:
        print(f"[DEBUG][{fn}] !! Route {rid} not found in _JEEPNEY_ROUTES")
        return None

    rname     = route['route_transit']
    dist_crow = _hav(board_lat, board_lon, alight_lat, alight_lon)
    print(f"[DEBUG][{fn}]   Route       = '{rname}'")
    print(f"[DEBUG][{fn}]   Board       = ({board_lat:.6f}, {board_lon:.6f})")
    print(f"[DEBUG][{fn}]   Alight      = ({alight_lat:.6f}, {alight_lon:.6f})")
    print(f"[DEBUG][{fn}]   Crow-flies  = {dist_crow:.0f}m")

    ridden_poly = None
    dist_m      = 0.0

    # ── Strategy 1: OSRM driving route ───────────────────────────────────────
    def try_osrm_driving():
        t_s = time.time()
        url = (f"https://router.project-osrm.org/route/v1/driving/"
               f"{board_lon},{board_lat};{alight_lon},{alight_lat}"
               f"?overview=full&geometries=geojson")
        print(f"[DEBUG][{fn}]   STRATEGY 1 (OSRM driving) → {url[:90]}...")
        try:
            t_req = time.time()
            r = requests.get(url, timeout=15, headers={'User-Agent': 'SafeRouteAI/1.0'}).json()
            print(f"[DEBUG][{fn}]   STRATEGY 1 responded in {time.time()-t_req:.3f}s  code={r.get('code')}")
            if r.get('code') == 'Ok' and r.get('routes'):
                coords = [[pt[1], pt[0]] for pt in r['routes'][0]['geometry']['coordinates']]
                dist   = r['routes'][0]['distance']
                # Sanity check: OSRM road dist should not be > 5× crow-flies
                if dist <= dist_crow * 5.0:
                    print(f"[DEBUG][{fn}]   STRATEGY 1 SUCCESS  dist={dist:.0f}m  "
                          f"coords={len(coords)}pts  elapsed={time.time()-t_s:.3f}s")
                    return coords, dist
                else:
                    print(f"[DEBUG][{fn}]   STRATEGY 1 REJECTED (dist {dist:.0f}m > 5×crow {dist_crow*5:.0f}m)")
            else:
                print(f"[DEBUG][{fn}]   STRATEGY 1 bad response: code={r.get('code')}")
        except Exception as e:
            print(f"[DEBUG][{fn}]   STRATEGY 1 EXCEPTION: {e}")
        return None, 0.0

    # ── Strategy 2: Straight-line fallback ────────────────────────────────────
    def try_straight_line():
        t_s = time.time()
        print(f"[DEBUG][{fn}]   STRATEGY 2 (straight line fallback)  dist={dist_crow:.0f}m")
        coords = [[board_lat, board_lon], [alight_lat, alight_lon]]
        print(f"[DEBUG][{fn}]   STRATEGY 2 done  elapsed={time.time()-t_s:.3f}s")
        return coords, dist_crow

    # Run strategies sequentially (OSRM first; straight-line is instant so no benefit to parallelism)
    print(f"[DEBUG][{fn}]   Attempting STRATEGY 1 (OSRM driving)...")
    ridden_poly, dist_m = try_osrm_driving()
    if not ridden_poly:
        print(f"[DEBUG][{fn}]   STRATEGY 1 failed → falling back to STRATEGY 2")
        ridden_poly, dist_m = try_straight_line()

    fare  = calc_sakay_fare(rid, dist_m)
    parts = rname.split(' - ', 1)
    bname = parts[0].strip()
    aname = parts[-1].strip()

    print(f"[DEBUG][{fn}]   Leg built  dist={dist_m:.0f}m  fare={fare['label']}  "
          f"polyline_pts={len(ridden_poly)}  total={time.time()-t_start:.3f}s")
    print(f"[DEBUG][{fn}] ──────────────────────────────────────────────────────────")

    return {
        'route_id'    : rid,
        'route_name'  : rname,
        'rtype'       : 'PUJ',
        'board'       : {'name': bname, 'lat': board_lat,  'lon': board_lon},
        'alight'      : {'name': aname, 'lat': alight_lat, 'lon': alight_lon},
        'ridden_poly' : ridden_poly,
        'ridden_stops': [
            {'name': bname, 'lat': board_lat,  'lon': board_lon},
            {'name': aname, 'lat': alight_lat, 'lon': alight_lon},
        ],
        'dist_m'      : dist_m,
        'fare'        : fare,
        'color'       : '#e67e22',
        'seg_type'    : 'jeepney',
    }


# ════════════════════════════════════════════════════════════════════════════════
#  JEEPNEY JOURNEY PLANNER
# ════════════════════════════════════════════════════════════════════════════════

def plan_jeepney_journey(orig_lat, orig_lon, dest_lat, dest_lon, max_results=3):
    """
    Full jeepney journey planning pipeline:

      Phase A  (no OSM)  — Load JSON data + pure-geometry candidate selection
      Phase B  (OSM)     — OSRM polyline fetch for each confirmed candidate leg
      Phase C            — Assemble final route objects

    Returns list of assembled route dicts (same schema as _assemble_route output).
    """
    fn = "plan_jeepney_journey"
    t_start = time.time()
    print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
    print(f"[DEBUG][{fn}] CALL: plan_jeepney_journey()")
    print(f"[DEBUG][{fn}]   Origin      = ({orig_lat:.6f}, {orig_lon:.6f})")
    print(f"[DEBUG][{fn}]   Destination = ({dest_lat:.6f}, {dest_lon:.6f})")
    print(f"[DEBUG][{fn}]   max_results = {max_results}")

    # ── PHASE A-1: Ensure data is loaded (no OSM) ─────────────────────────────
    print(f"[DEBUG][{fn}] ── PHASE A-1 · Loading jeepney data (no OSM) ──────────")
    t_a1 = time.time()
    _load_jeepney()
    print(f"[DEBUG][{fn}]   routes_loaded={len(_JEEPNEY_ROUTES)}  elapsed={time.time()-t_a1:.3f}s")

    if not _JEEPNEY_ROUTES:
        print(f"[DEBUG][{fn}] !! No jeepney routes available  total={time.time()-t_start:.3f}s")
        print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
        return []

    # ── PHASE A-2: Pure-geometry candidate selection (no OSM) ─────────────────
    print(f"[DEBUG][{fn}] ── PHASE A-2 · Geometry-based candidate selection (no OSM) ─")
    t_a2 = time.time()
    direct_cands, transfer_cands = _find_jeepney_candidates(orig_lat, orig_lon, dest_lat, dest_lon)
    print(f"[DEBUG][{fn}]   direct={len(direct_cands)}  transfer={len(transfer_cands)}  elapsed={time.time()-t_a2:.3f}s")

    if not direct_cands and not transfer_cands:
        print(f"[DEBUG][{fn}] !! No candidates found  total={time.time()-t_start:.3f}s")
        print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
        return []

    # ── PHASE B: Build legs via OSRM (first OSM touch — multithreaded) ────────
    print(f"[DEBUG][{fn}] ── PHASE B · OSRM leg building (multithreaded) ──────────")
    t_b = time.time()

    # Prepare build tasks (direct + transfer), capped at max_results each
    tasks = []
    for item in direct_cands[:max_results]:
        score, rid, blat, blon, alat, alon = item
        tasks.append(('direct', score, rid, blat, blon, alat, alon))
    for item in transfer_cands[:max_results]:
        tasks.append(('transfer',) + item)

    print(f"[DEBUG][{fn}]   Total tasks: {len(tasks)}  "
          f"(direct={sum(1 for t in tasks if t[0]=='direct')}  "
          f"transfer={sum(1 for t in tasks if t[0]=='transfer')})")

    def execute_task(task):
        ttype = task[0]
        if ttype == 'direct':
            _, score, rid, blat, blon, alat, alon = task
            print(f"[DEBUG][{fn}][execute_task] Building DIRECT leg  rid={rid}  score={score:.0f}")
            leg = _build_jeepney_leg(rid, blat, blon, alat, alon)
            if leg:
                return (score, [leg])
            print(f"[DEBUG][{fn}][execute_task] DIRECT leg build FAILED  rid={rid}")
            return None

        elif ttype == 'transfer':
            _, score, rid1, bl1, blo1, xl1, xlo1, rid2, bl2, blo2, al2, alo2 = task
            print(f"[DEBUG][{fn}][execute_task] Building TRANSFER legs  {rid1}→{rid2}  score={score:.0f}")
            # Build both legs concurrently
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as inner_ex:
                f1 = inner_ex.submit(_build_jeepney_leg, rid1, bl1, blo1, xl1, xlo1)
                f2 = inner_ex.submit(_build_jeepney_leg, rid2, bl2, blo2, al2, alo2)
                leg1 = f1.result()
                leg2 = f2.result()
            if leg1 and leg2:
                print(f"[DEBUG][{fn}][execute_task] TRANSFER both legs OK  {rid1}→{rid2}")
                return (score, [leg1, leg2])
            print(f"[DEBUG][{fn}][execute_task] TRANSFER leg build FAILED  {rid1}→{rid2}  "
                  f"leg1_ok={bool(leg1)}  leg2_ok={bool(leg2)}")
            return None
        return None

    outer_workers = min(6, max(1, len(tasks)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=outer_workers) as ex:
        built_results = list(ex.map(execute_task, tasks))

    built_results = [r for r in built_results if r is not None]
    built_results.sort(key=lambda x: x[0])
    print(f"[DEBUG][{fn}]   Built {len(built_results)} valid leg-sets  elapsed={time.time()-t_b:.3f}s")

    # ── PHASE C: Assemble final route objects ─────────────────────────────────
    print(f"[DEBUG][{fn}] ── PHASE C · Route assembly ──────────────────────────────")
    t_c = time.time()
    final    = []
    seen_key = set()

    for score, legs in built_results:
        key = tuple(leg['route_id'] for leg in legs)
        if key in seen_key:
            print(f"[DEBUG][{fn}]   SKIP duplicate key={key}")
            continue
        seen_key.add(key)
        route = _assemble_route(legs, orig_lat, orig_lon, dest_lat, dest_lon, len(final))
        final.append(route)
        print(f"[DEBUG][{fn}]   Added route[{len(final)-1}]  "
              f"legs={len(legs)}  name='{route['name']}'  time={route['time']}")
        if len(final) >= max_results:
            break

    print(f"[DEBUG][{fn}]   Assembly done  routes={len(final)}  elapsed={time.time()-t_c:.3f}s")
    print(f"[DEBUG][{fn}] ── RESULT ────────────────────────────────────────────────")
    for i, r in enumerate(final):
        print(f"[DEBUG][{fn}]   [{i}] '{r['name']}'  {r['time']}  {r['distance']}  fare={r['fare']}")
    print(f"[DEBUG][{fn}] TOTAL DURATION={time.time()-t_start:.3f}s")
    print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
    return final


# ════════════════════════════════════════════════════════════════════════════════
#  SAKAY LOADER  (Bus + Rail ONLY — jeepney now served by jeepney.json above)
# ════════════════════════════════════════════════════════════════════════════════

_SAKAY_READY  = False
_SAKAY_ROUTES = {}
_SAKAY_SHAPES = {}
_SAKAY_PUB    = []      # bus only
_SAKAY_RAIL   = []      # rail only

_STOP_SPATIAL = defaultdict(list)
_SPATIAL_CELL = 0.008


def _load_sakay():
    """Load bus & rail routes from sakay_all_routes.json (jeepney excluded)."""
    fn = "_load_sakay"
    global _SAKAY_READY
    t_start = time.time()
    print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
    print(f"[DEBUG][{fn}] CALL: _load_sakay()  _SAKAY_READY={_SAKAY_READY}")

    if _SAKAY_READY:
        print(f"[DEBUG][{fn}] Already initialised — skipping  elapsed={time.time()-t_start:.3f}s")
        print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
        return

    rp = _find_file('sakay_all_routes.json')
    sp = _find_file('sakay_all_shapes.geojson')
    print(f"[DEBUG][{fn}] File discovery → routes={bool(rp)}  shapes={bool(sp)}")

    def parse_routes_worker(path):
        t0 = time.time()
        print(f"[DEBUG][{fn}][routes_worker] Parsing {path}...")
        _parse_routes(path)
        print(f"[DEBUG][{fn}][routes_worker] Done  elapsed={time.time()-t0:.3f}s")

    def parse_shapes_worker(path):
        t0 = time.time()
        print(f"[DEBUG][{fn}][shapes_worker] Parsing {path}...")
        _parse_shapes(path)
        print(f"[DEBUG][{fn}][shapes_worker] Done  elapsed={time.time()-t0:.3f}s")

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        futures = []
        if rp: futures.append(ex.submit(parse_routes_worker, rp))
        if sp: futures.append(ex.submit(parse_shapes_worker, sp))
        for f in concurrent.futures.as_completed(futures):
            try:
                f.result()
            except Exception as e:
                print(f"[DEBUG][{fn}] Worker error: {e}")

    t_spatial = time.time()
    print(f"[DEBUG][{fn}] Building sakay spatial index...")
    _build_spatial()
    print(f"[DEBUG][{fn}] Spatial index built  elapsed={time.time()-t_spatial:.3f}s")

    _SAKAY_READY = True
    n_stops = sum(len(v) for v in _STOP_SPATIAL.values())
    print(f"[DEBUG][{fn}] ✓ READY: {len(_SAKAY_ROUTES)} routes "
          f"({len(_SAKAY_PUB)} PUB · {len(_SAKAY_RAIL)} rail) · "
          f"{len(_SAKAY_SHAPES)} shapes · {n_stops} indexed stops")
    print(f"[DEBUG][{fn}] TOTAL INIT TIME={time.time()-t_start:.3f}s")
    print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")


def _parse_routes(path):
    """Parse sakay_all_routes.json — BUS and RAIL only (jeepney/PUJ excluded)."""
    fn = "_parse_routes"
    t_start = time.time()
    print(f"[DEBUG][{fn}] ── START  path={path}")
    raw_meta = {}
    stops_map = defaultdict(dict)
    line_count = 0

    with open(path, encoding='utf-8') as f:
        for raw in f:
            line_count += 1
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue

            rid  = str(rec.get('route_id', '')).strip()
            sid  = str(rec.get('stop_id', '')).strip()
            slat = rec.get('stop_lat')
            slon = rec.get('stop_lon')
            seq  = rec.get('stop_sequence', 9999)
            if not rid or not sid or slat is None or slon is None:
                continue

            # ── Exclude jeepney routes (PUJ prefix) — served by jeepney.json ──
            upper = rid.upper()
            rtype = rec.get('route_type', 3)
            is_jeepney = 'PUJ' in upper
            is_rail    = rtype == 2 or upper.startswith('ROUTE_')
            is_bus     = not is_jeepney and not is_rail

            if is_jeepney:
                continue  # jeepney routes now come from jeepney.json

            if rid not in raw_meta:
                raw_meta[rid] = {
                    'route_id'        : rid,
                    'route_long_name' : rec.get('route_long_name') or rid,
                    'route_desc'      : rec.get('route_desc') or '',
                    'route_type'      : rtype,
                    'route_color'     : rec.get('route_color'),
                    'shape_id'        : (str(rec['shape_id']).strip() if rec.get('shape_id') else None),
                    'agency_id'       : rec.get('agency_id', 'LTFRB'),
                }

            entry = stops_map[rid].get(sid)
            if entry is None or seq < entry['seq']:
                stops_map[rid][sid] = {
                    'stop_id': sid,
                    'name'   : rec.get('stop_name') or 'Stop',
                    'lat'    : float(slat),
                    'lon'    : float(slon),
                    'seq'    : seq,
                }

    print(f"[DEBUG][{fn}] File read  lines={line_count}  routes_found={len(stops_map)}")

    valid = 0
    for rid, sd in stops_map.items():
        stops = sorted(sd.values(), key=lambda s: s['seq'])
        stops = [s for s in stops if s['lat'] and s['lon']]
        if len(stops) < 2:
            continue
        valid += 1
        meta = raw_meta.get(rid, {})
        _SAKAY_ROUTES[rid] = {**meta, 'stops': stops}
        upper = rid.upper()
        rtype = meta.get('route_type', 3)
        if rtype == 2 or upper.startswith('ROUTE_'):
            _SAKAY_RAIL.append(rid)
        else:
            _SAKAY_PUB.append(rid)

    print(f"[DEBUG][{fn}] Loaded {valid} valid bus/rail routes  elapsed={time.time()-t_start:.3f}s")


def _parse_shapes(path):
    fn = "_parse_shapes"
    t_start = time.time()
    print(f"[DEBUG][{fn}] ── START  path={path}")
    try:
        with open(path, encoding='utf-8') as f:
            geo = json.load(f)
        features = geo.get('features', [])
        print(f"[DEBUG][{fn}] Processing {len(features)} shape features...")
        count = 0
        for feat in features:
            sid       = feat.get('properties', {}).get('shape_id')
            geom_type = feat.get('geometry', {}).get('type')
            coords    = feat.get('geometry', {}).get('coordinates', [])
            if sid is None or not coords:
                continue
            segments = []
            if (geom_type == 'MultiLineString' or
                    (isinstance(coords, list) and isinstance(coords[0], list)
                     and isinstance(coords[0][0], list))):
                for line in coords:
                    segments.append([[c[1], c[0]] for c in line if len(c) >= 2])
            else:
                segments.append([[c[1], c[0]] for c in coords if len(c) >= 2])
            segments = [s for s in segments if s]
            if not segments:
                continue
            if len(segments) == 1:
                final_poly = segments[0]
            else:
                final_poly = _chain_all(segments)
                if len(final_poly) > 1:
                    final_poly = [pt for seg in final_poly for pt in seg]
                elif len(final_poly) == 1:
                    final_poly = final_poly[0]
                else:
                    final_poly = []
            if not final_poly:
                continue
            _SAKAY_SHAPES[str(sid).strip()] = final_poly
            count += 1
        print(f"[DEBUG][{fn}] Extracted {count} shapes  elapsed={time.time()-t_start:.3f}s")
    except Exception as e:
        print(f"[DEBUG][{fn}] !! ERROR: {e}")


def _build_spatial():
    fn = "_build_spatial"
    t_start = time.time()
    print(f"[DEBUG][{fn}] Building stop spatial index for {len(_SAKAY_ROUTES)} routes...")
    _STOP_SPATIAL.clear()

    def process_route(rid_route):
        rid, route = rid_route
        local = defaultdict(list)
        for idx, stop in enumerate(route.get('stops', [])):
            cell = (int(stop['lat'] / _SPATIAL_CELL), int(stop['lon'] / _SPATIAL_CELL))
            local[cell].append((rid, idx, stop['lat'], stop['lon']))
        return local

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(32, max(1, len(_SAKAY_ROUTES)))) as ex:
        futures = {ex.submit(process_route, (rid, route)): rid
                   for rid, route in _SAKAY_ROUTES.items()}
        for future in concurrent.futures.as_completed(futures):
            try:
                local_cells = future.result()
                for cell, entries in local_cells.items():
                    _STOP_SPATIAL[cell].extend(entries)
            except Exception as e:
                print(f"[DEBUG][{fn}] ERROR processing route {futures[future]}: {e}")

    total_stops = sum(len(v) for v in _STOP_SPATIAL.values())
    print(f"[DEBUG][{fn}] Spatial grid built  cells={len(_STOP_SPATIAL)}  stops={total_stops}  "
          f"elapsed={time.time()-t_start:.3f}s")


def _nearby_stops(lat, lon, radius_m=450):
    cr = math.ceil(radius_m / (_SPATIAL_CELL * 111_000)) + 1
    cx = int(lat / _SPATIAL_CELL)
    cy = int(lon / _SPATIAL_CELL)
    out = []
    for dx in range(-cr, cr + 1):
        for dy in range(-cr, cr + 1):
            for rid, idx, slat, slon in _STOP_SPATIAL.get((cx + dx, cy + dy), []):
                d = _hav(lat, lon, slat, slon)
                if d <= radius_m:
                    out.append((rid, idx, slat, slon, d))
    out.sort(key=lambda x: x[4])
    return out


# ── Fare ─────────────────────────────────────────────────────────────────────
def calc_sakay_fare(route_id, distance_m):
    km = max(0.0, distance_m / 1_000.0)
    upper = route_id.upper()
    if 'PUJ' in upper:
        base, bkm, rate, mode = 13.00, 4.0, 1.80, 'Jeepney'
    elif 'PUB' in upper:
        base, bkm, rate, mode = 15.00, 5.0, 2.20, 'Bus'
    elif 'ROUTE_' in upper or upper.startswith('ROUTE'):
        for lim, f in [(2, 13), (4, 16), (6, 19), (8, 22), (10, 25)]:
            if km <= lim:
                return {'amount': float(f), 'currency': 'PHP',
                        'label': f'PHP {f:.2f}', 'mode': 'Rail'}
        return {'amount': 28.0, 'currency': 'PHP', 'label': 'PHP 28.00', 'mode': 'Rail'}
    else:
        base, bkm, rate, mode = 15.00, 5.0, 2.20, 'Bus'
    fare = base + max(0.0, km - bkm) * rate
    return {'amount': round(fare, 2), 'currency': 'PHP',
            'label': f'PHP {fare:.2f}', 'mode': mode}


# ── Route geometry (for sakay bus/rail shapes) ────────────────────────────────
def _route_poly(route_id):
    route = _SAKAY_ROUTES.get(route_id)
    if not route:
        return None
    sid = route.get('shape_id')
    if sid and str(sid) in _SAKAY_SHAPES:
        return _SAKAY_SHAPES[str(sid)]
    return [[s['lat'], s['lon']] for s in route['stops']]


# ════════════════════════════════════════════════════════════════════════════════
#  MULTI-LEG SURFACE PLANNER  (Bus + Rail via Sakay GTFS)
# ════════════════════════════════════════════════════════════════════════════════

_TYPE_COLOR = {'PUJ': '#e67e22', 'PUB': '#16a085', 'RAIL': '#27ae60'}
_TYPE_LABEL = {'PUJ': 'jeepney', 'PUB': 'bus',     'RAIL': 'train'}
_BOARD_LIM  = 1000
_ALIGHT_LIM = 1200
_XFER_LIM   = 800
_XFER_PEN   = 300


def _rtype(rid):
    u = rid.upper()
    if 'PUJ' in u: return 'PUJ'
    if 'PUB' in u: return 'PUB'
    return 'RAIL'


def _build_leg(rid, board_idx, alight_idx):
    """Build a bus/rail leg from sakay GTFS data using OSRM + shape strategies."""
    fn = "_build_leg"
    t_start = time.time()
    print(f"[DEBUG][{fn}] ── START  rid={rid}  board={board_idx}  alight={alight_idx}")

    route  = _SAKAY_ROUTES[rid]
    stops  = route['stops']
    rtype  = _rtype(rid)
    ridden = []
    dist_m = 0.0

    def osrm_strategy():
        step = max(1, (alight_idx - board_idx) // 10)
        sample_idxs = list(range(board_idx, alight_idx + 1, step))
        if board_idx  not in sample_idxs: sample_idxs.insert(0, board_idx)
        if alight_idx not in sample_idxs: sample_idxs.append(alight_idx)
        sample_pts = [stops[i] for i in sorted(set(sample_idxs))]
        if len(sample_pts) < 2:
            return None, 0
        pts_str = ";".join(f"{p['lon']},{p['lat']}" for p in sample_pts)
        url = f"https://router.project-osrm.org/route/v1/driving/{pts_str}?overview=full&geometries=geojson"
        try:
            t_req = time.time()
            r = requests.get(url, timeout=5, headers={'User-Agent': 'SafeRouteAI'}).json()
            print(f"[DEBUG][{fn}][osrm] responded {time.time()-t_req:.3f}s  code={r.get('code')}")
            if r.get('code') == 'Ok':
                coords = [[pt[1], pt[0]] for pt in r['routes'][0]['geometry']['coordinates']]
                dist   = r['routes'][0]['distance']
                return coords, dist
        except Exception as e:
            print(f"[DEBUG][{fn}][osrm] ERROR: {e}")
        return None, 0

    def shape_strategy():
        poly = _route_poly(rid)
        if not poly or len(poly) < 2:
            return None, 0
        b_poly = _closest_idx(poly, stops[board_idx]['lat'],  stops[board_idx]['lon'])
        a_poly = _closest_idx(poly, stops[alight_idx]['lat'], stops[alight_idx]['lon'])
        if b_poly <= a_poly:
            ridden_poly = poly[b_poly:a_poly + 1]
        else:
            ridden_poly = list(reversed(poly[a_poly:b_poly + 1]))
        poly_d   = _poly_dist(ridden_poly)
        stops_d  = _hav(stops[board_idx]['lat'], stops[board_idx]['lon'],
                        stops[alight_idx]['lat'], stops[alight_idx]['lon'])
        if poly_d > stops_d * 3.0 and poly_d > 2000:
            return None, 0
        return ridden_poly, poly_d

    def fallback_strategy():
        rp  = [[s['lat'], s['lon']] for s in stops[board_idx:alight_idx + 1]]
        return rp, _poly_dist(rp)

    strategies = []
    if rtype in ('PUJ', 'PUB'):
        strategies.append(osrm_strategy)
    strategies += [shape_strategy, fallback_strategy]

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(strategies)) as ex:
        future_map = {ex.submit(fn_s): fn_s.__name__ for fn_s in strategies}
        for future in concurrent.futures.as_completed(future_map):
            sname = future_map[future]
            try:
                poly, d = future.result()
                if poly:
                    ridden, dist_m = poly, d
                    print(f"[DEBUG][{fn}] Strategy '{sname}' won  dist={dist_m:.0f}m")
                    break
            except Exception as e:
                print(f"[DEBUG][{fn}] Strategy '{sname}' raised: {e}")

    if not dist_m:
        dist_m = _poly_dist(ridden)

    fare = calc_sakay_fare(rid, dist_m)
    print(f"[DEBUG][{fn}] Leg built  dist={dist_m:.0f}m  fare={fare['label']}  "
          f"elapsed={time.time()-t_start:.3f}s")

    return {
        'route_id'    : rid,
        'route_name'  : route.get('route_long_name', rid),
        'rtype'       : rtype,
        'board'       : stops[board_idx],
        'alight'      : stops[alight_idx],
        'ridden_poly' : ridden,
        'ridden_stops': stops[board_idx:alight_idx + 1],
        'dist_m'      : dist_m,
        'fare'        : fare,
        'color'       : _TYPE_COLOR.get(rtype, '#2980b9'),
        'seg_type'    : _TYPE_LABEL.get(rtype, 'bus'),
    }


def _assemble_route(legs, orig_lat, orig_lon, dest_lat, dest_lon, route_id=0):
    fn = "_assemble_route"
    t_start = time.time()
    print(f"[DEBUG][{fn}] Assembling route from {len(legs)} legs  route_id={route_id}")
    segments   = []
    total_walk = 0.0
    total_ride = 0.0
    total_time = 0.0
    all_coords = []
    prev_lat   = orig_lat
    prev_lon   = orig_lon

    for i, leg in enumerate(legs):
        board  = leg['board']
        alight = leg['alight']
        lbl    = (f"Walk to {board['name'][:40]}" if i == 0
                  else f"Transfer · walk to {board['name'][:35]}")
        seg_w, wd, wt = _walk_seg(prev_lat, prev_lon, board['lat'], board['lon'], lbl)
        if seg_w:
            segments.append(seg_w)
            total_walk += wd
            total_time += wt
            all_coords.extend(seg_w['coords'])

        spd = {'PUJ': 4.2, 'PUB': 5.6, 'RAIL': 11.1}.get(leg['rtype'], 4.2)
        segments.append({
            'type'    : leg['seg_type'],
            'coords'  : leg['ridden_poly'],
            'color'   : leg['color'],
            'label'   : leg['route_name'],
            'stations': leg['ridden_stops'],
        })
        total_ride += leg['dist_m']
        total_time += leg['dist_m'] / spd
        all_coords.extend(leg['ridden_poly'])
        prev_lat = alight['lat']
        prev_lon = alight['lon']

    seg_w, wd, wt = _walk_seg(prev_lat, prev_lon, dest_lat, dest_lon, "Walk to destination")
    if seg_w:
        segments.append(seg_w)
        total_walk += wd
        total_time += wt
        all_coords.extend(seg_w['coords'])

    total_min = max(1, int(total_time / 60))
    total_km  = round((total_ride + total_walk) / 1000, 1)
    rtypes    = [leg['rtype'] for leg in legs]
    mode_names = []
    if any(t == 'RAIL' for t in rtypes): mode_names.append('Train')
    if any(t == 'PUJ'  for t in rtypes): mode_names.append('Jeepney')
    if any(t == 'PUB'  for t in rtypes): mode_names.append('Bus')
    route_name  = ' + '.join(mode_names) if mode_names else 'Transit'
    fare_total  = sum(leg['fare']['amount'] for leg in legs)
    score       = total_walk + _XFER_PEN * (len(legs) - 1)
    dom         = max(set(rtypes), key=rtypes.count)

    print(f"[DEBUG][{fn}] Route assembled  modes={rtypes}  dist={total_km}km  "
          f"time={total_min}m  fare=PHP{fare_total:.2f}  elapsed={time.time()-t_start:.3f}s")

    return {
        'id'            : route_id,
        'name'          : ' + '.join(leg['route_name'][:30] for leg in legs),
        'route_name'    : route_name,
        'type'          : 'transit',
        'color'         : _TYPE_COLOR.get(dom, '#2980b9'),
        'time'          : f"~{total_min} mins",
        'distance'      : f"{total_km} km",
        'fare'          : f"PHP {fare_total:.2f}",
        'fare_amount'   : fare_total,
        'coords'        : all_coords,
        'segments'      : segments,
        'stations'      : legs[0]['ridden_stops'],
        'safety_score'  : 72,
        'hazards_flagged': ' · '.join(leg['route_name'][:25] for leg in legs),
        'data_source'   : 'jeepney_json' if all('PUJ' in leg['route_id'] for leg in legs)
                          else 'sakay_ltfrb',
        '_score'        : score,
        '_legs'         : len(legs),
    }


def plan_surface_journey(allowed_modes, orig_lat, orig_lon, dest_lat, dest_lon, max_results=3):
    """
    Route surface modes:
      • jeepney  → plan_jeepney_journey()  (jeepney.json, pure-geometry first)
      • bus      → sakay GTFS
      • train    → sakay GTFS rail
    All modes run concurrently; results merged and deduplicated.
    """
    fn = "plan_surface_journey"
    t_start = time.time()
    print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
    print(f"[DEBUG][{fn}] CALL: plan_surface_journey(allowed_modes={allowed_modes})")
    print(f"[DEBUG][{fn}]   Origin={orig_lat:.5f},{orig_lon:.5f}  Dest={dest_lat:.5f},{dest_lon:.5f}")

    # ── Parallel dispatch per mode ───────────────────────────────────────────
    def run_jeepney():
        if 'jeepney' not in allowed_modes:
            return []
        print(f"[DEBUG][{fn}][run_jeepney] → plan_jeepney_journey()")
        return plan_jeepney_journey(orig_lat, orig_lon, dest_lat, dest_lon, max_results)

    def run_bus():
        if 'bus' not in allowed_modes:
            return []
        print(f"[DEBUG][{fn}][run_bus] → sakay bus routes")
        _load_sakay()
        cand_rids = list(_SAKAY_PUB)
        if not cand_rids:
            return []
        return _plan_sakay_modes(cand_rids, orig_lat, orig_lon, dest_lat, dest_lon, max_results)

    def run_train():
        if 'train' not in allowed_modes:
            return []
        print(f"[DEBUG][{fn}][run_train] → sakay rail routes")
        _load_sakay()
        cand_rids = list(_SAKAY_RAIL)
        if not cand_rids:
            return []
        return _plan_sakay_modes(cand_rids, orig_lat, orig_lon, dest_lat, dest_lon, max_results)

    print(f"[DEBUG][{fn}] Dispatching mode workers concurrently...")
    t_dispatch = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        f_jeep  = ex.submit(run_jeepney)
        f_bus   = ex.submit(run_bus)
        f_train = ex.submit(run_train)
        jeep_routes  = f_jeep.result()
        bus_routes   = f_bus.result()
        train_routes = f_train.result()
    print(f"[DEBUG][{fn}] Mode workers done  jeep={len(jeep_routes)}  "
          f"bus={len(bus_routes)}  train={len(train_routes)}  elapsed={time.time()-t_dispatch:.3f}s")

    combined = jeep_routes + bus_routes + train_routes
    combined.sort(key=lambda r: r.get('_score', 9999))

    # Deduplicate by name
    final     = []
    seen_name = set()
    for r in combined:
        if r['name'] not in seen_name:
            seen_name.add(r['name'])
            final.append(r)
        if len(final) >= max_results:
            break

    for i, r in enumerate(final):
        r['id'] = i

    print(f"[DEBUG][{fn}] Merged & deduped  final={len(final)}  total={time.time()-t_start:.3f}s")
    print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
    return final


def _plan_sakay_modes(cand_rids, orig_lat, orig_lon, dest_lat, dest_lon, max_results=3):
    """Internal helper: plan routes using sakay GTFS stop lists (bus/rail)."""
    fn = "_plan_sakay_modes"
    t_start = time.time()
    print(f"[DEBUG][{fn}] Planning sakay routes  candidates={len(cand_rids)}")
    allowed_set = set(cand_rids)

    # Destination reach
    dest_reach = {}
    for rid in cand_rids:
        stops = _SAKAY_ROUTES[rid]['stops']
        ai    = min(range(len(stops)),
                    key=lambda i: _hav(dest_lat, dest_lon, stops[i]['lat'], stops[i]['lon']))
        ad    = _hav(dest_lat, dest_lon, stops[ai]['lat'], stops[ai]['lon'])
        if ad <= _ALIGHT_LIM:
            dest_reach[rid] = (ai, ad)

    # Origin board
    first_legs = []
    for rid in cand_rids:
        stops = _SAKAY_ROUTES[rid]['stops']
        bi    = min(range(len(stops)),
                    key=lambda i: _hav(orig_lat, orig_lon, stops[i]['lat'], stops[i]['lon']))
        bd    = _hav(orig_lat, orig_lon, stops[bi]['lat'], stops[bi]['lon'])
        if bd <= _BOARD_LIM:
            first_legs.append((bd, bi, rid))

    raw = []
    seen_pairs = {}

    # Direct
    def build_direct(args):
        bd, bi, rid = args
        if rid not in dest_reach:
            return None
        ai, ad = dest_reach[rid]
        if bi >= ai or ai - bi < 2:
            return None
        leg = _build_leg(rid, bi, ai)
        return (bd + ad, [leg])

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, max(1, len(first_legs)))) as ex:
        direct_results = list(ex.map(build_direct, first_legs))
    raw += [r for r in direct_results if r]

    # Transfers
    def build_transfer(args):
        bd, bi, rid1 = args
        stops1 = _SAKAY_ROUTES[rid1]['stops']
        local  = []
        for ai1 in range(bi + 2, len(stops1)):
            ts = stops1[ai1]
            for rid2, bi2, _, _, td in _nearby_stops(ts['lat'], ts['lon'], _XFER_LIM):
                if rid2 == rid1 or rid2 not in allowed_set or rid2 not in dest_reach:
                    continue
                ai2, ad = dest_reach[rid2]
                if bi2 >= ai2 or ai2 - bi2 < 2:
                    continue
                score = bd + td + ad + _XFER_PEN
                pair  = (rid1, rid2)
                local.append((score, pair, rid1, bi, ai1, rid2, bi2, ai2))
        return local

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, max(1, len(first_legs)))) as ex:
        all_xfer = list(ex.map(build_transfer, first_legs))

    for xfer_list in all_xfer:
        for score, pair, rid1, bi, ai1, rid2, bi2, ai2 in xfer_list:
            if pair in seen_pairs and seen_pairs[pair] <= score:
                continue
            seen_pairs[pair] = score
            leg1 = _build_leg(rid1, bi, ai1)
            leg2 = _build_leg(rid2, bi2, ai2)
            raw.append((score, [leg1, leg2]))

    if not raw:
        print(f"[DEBUG][{fn}] No routes found  elapsed={time.time()-t_start:.3f}s")
        return []

    raw.sort(key=lambda x: x[0])
    final    = []
    used_key = set()
    for score, legs in raw:
        key = tuple(leg['route_id'] for leg in legs)
        if key in used_key:
            continue
        used_key.add(key)
        final.append(_assemble_route(legs, orig_lat, orig_lon, dest_lat, dest_lon, len(final)))
        if len(final) >= max_results:
            break

    print(f"[DEBUG][{fn}] Done  routes={len(final)}  elapsed={time.time()-t_start:.3f}s")
    return final


# ── Public surface entry points ───────────────────────────────────────────────
def get_jeepney_route(orig_lon, orig_lat, dest_lon, dest_lat):
    fn = "get_jeepney_route"
    print(f"[DEBUG][{fn}] ({orig_lat:.5f},{orig_lon:.5f}) → ({dest_lat:.5f},{dest_lon:.5f})")
    routes = plan_jeepney_journey(orig_lat, orig_lon, dest_lat, dest_lon)
    if not routes:
        return {"error": "No jeepney route found near your origin and destination."}
    return {"routes": routes}


def get_bus_route(orig_lon, orig_lat, dest_lon, dest_lat):
    fn = "get_bus_route"
    print(f"[DEBUG][{fn}] ({orig_lat:.5f},{orig_lon:.5f}) → ({dest_lat:.5f},{dest_lon:.5f})")
    routes = plan_surface_journey(['bus'], orig_lat, orig_lon, dest_lat, dest_lon)
    if not routes:
        return {"error": "No bus route found near your origin and destination."}
    _tag_routes(routes, 'bus', 'Bus', '#16a085')
    return {"routes": routes}


def get_jeepney_bus_route(orig_lon, orig_lat, dest_lon, dest_lat):
    fn = "get_jeepney_bus_route"
    print(f"[DEBUG][{fn}] ({orig_lat:.5f},{orig_lon:.5f}) → ({dest_lat:.5f},{dest_lon:.5f})")
    routes = plan_surface_journey(['jeepney', 'bus'], orig_lat, orig_lon, dest_lat, dest_lon)
    if not routes:
        return {"error": "No jeepney or bus route found for this journey."}
    _tag_routes(routes, 'jeepney_bus', 'Jeepney/Bus', '#e67e22')
    return {"routes": routes}


# ════════════════════════════════════════════════════════════════════════════════
#  TRAIN (OSM Overpass)
# ════════════════════════════════════════════════════════════════════════════════

_STOP_ROLES    = {'stop', 'stop_entry_only', 'stop_exit_only'}
_STATION_TAGS  = {'station', 'stop', 'halt', 'tram_stop', 'subway_entrance'}
_TRAIN_META = {
    "lrt-1": {"color": "#27ae60", "label": "LRT-1", "subtitle": "Green Line", "emoji": "🚇"},
    "lrt-2": {"color": "#2980b9", "label": "LRT-2", "subtitle": "Blue Line",  "emoji": "🚇"},
    "mrt-3": {"color": "#f39c12", "label": "MRT-3", "subtitle": "Yellow Line","emoji": "🚆"},
    "pnr":   {"color": "#8B4513", "label": "PNR",   "subtitle": "Commuter Rail","emoji": "🚂"},
}
_LINE_CACHE = {}
_TRANSFERS = [
    {"id": "L1_L2", "from_line": "lrt-1", "to_line": "lrt-2",
     "from_station": "Doroteo Jose", "to_station": "Recto",
     "from_lat": 14.5997, "from_lon": 120.9842, "to_lat": 14.5994, "to_lon": 120.9858,
     "lat": 14.6000, "lon": 120.9850, "label": "Walk via CM Recto Ave (~5 min)", "est_min": 5},
    {"id": "L1_M3", "from_line": "lrt-1", "to_line": "mrt-3",
     "from_station": "EDSA", "to_station": "Taft Avenue",
     "from_lat": 14.5366, "from_lon": 121.0003, "to_lat": 14.5369, "to_lon": 121.0013,
     "lat": 14.5370, "lon": 121.0010, "label": "Walk via enclosed walkway (~3 min)", "est_min": 3},
    {"id": "L2_M3", "from_line": "lrt-2", "to_line": "mrt-3",
     "from_station": "Araneta Center-Cubao", "to_station": "Araneta Center-Cubao",
     "from_lat": 14.6235, "from_lon": 121.0534, "to_lat": 14.6226, "to_lon": 121.0528,
     "lat": 14.6220, "lon": 121.0520, "label": "Walk via Cubao interchange (~8 min)", "est_min": 8},
]


def _extract_relation(rel):
    stops = []
    ways  = []
    seen  = set()
    for m in rel.get('members', []):
        mtype = m.get('type')
        role  = m.get('role', '')
        if mtype == 'node':
            tags    = m.get('tags', {})
            is_stop = (role in _STOP_ROLES
                       or tags.get('railway') in _STATION_TAGS
                       or tags.get('public_transport') in ('stop_position', 'station'))
            if role == 'platform' or tags.get('public_transport') == 'platform':
                continue
            ref = m.get('ref') or f"{m.get('lat')},{m.get('lon')}"
            if is_stop and ref not in seen:
                seen.add(ref)
                stops.append({'lat': m['lat'], 'lon': m['lon'],
                               'name': (tags.get('name') or tags.get('name:en')
                                        or tags.get('ref') or 'Station')})
        elif mtype == 'way' and 'geometry' in m:
            ways.append([[pt['lat'], pt['lon']] for pt in m['geometry']])
    return stops, ways


def _fetch_full_line(lid):
    fn = "_fetch_full_line"
    t_start = time.time()
    print(f"[DEBUG][{fn}] Fetching full line: {lid}")
    if lid in _LINE_CACHE:
        print(f"[DEBUG][{fn}]   Cache HIT  elapsed={time.time()-t_start:.3f}s")
        return _LINE_CACHE[lid]
    name  = _osm_name(lid)
    query = (f'[out:json][timeout:40];\n'
             f'(relation["route"~"rail|light_rail|subway"]["name"~"{name}",i](14.2,120.9,14.8,121.2);\n'
             f' relation["route"~"rail|light_rail|subway"]["ref"~"{name}",i](14.2,120.9,14.8,121.2););\n'
             f'out geom;')
    data = _overpass_query(query, max_retries=3, timeout=40)
    if not data:
        print(f"[DEBUG][{fn}]   Overpass failed  elapsed={time.time()-t_start:.3f}s")
        _LINE_CACHE[lid] = (None, None)
        return None, None
    rels = [e for e in data.get('elements', []) if e['type'] == 'relation']
    if not rels:
        print(f"[DEBUG][{fn}]   No relations found  elapsed={time.time()-t_start:.3f}s")
        _LINE_CACHE[lid] = (None, None)
        return None, None
    best   = max(rels, key=lambda r: sum(1 for m in r.get('members', [])
                                         if m.get('role', '') in _STOP_ROLES))
    stops, ways = _extract_relation(best)
    if len(stops) < 2:
        print(f"[DEBUG][{fn}]   Insufficient stops  elapsed={time.time()-t_start:.3f}s")
        _LINE_CACHE[lid] = (None, None)
        return None, None
    _LINE_CACHE[lid] = (stops, ways)
    print(f"[DEBUG][{fn}]   Cached OK  stops={len(stops)}  elapsed={time.time()-t_start:.3f}s")
    return stops, ways


def _slice_line(all_st, all_wy, olat, olon, dlat, dlon):
    if not all_st or len(all_st) < 2:
        return None
    oi = min(range(len(all_st)), key=lambda i: _dsq(all_st[i]['lat'], all_st[i]['lon'], olat, olon))
    di = min(range(len(all_st)), key=lambda i: _dsq(all_st[i]['lat'], all_st[i]['lon'], dlat, dlon))
    if oi == di:
        return None
    si, ei = min(oi, di), max(oi, di)
    sliced  = all_st[si:ei + 1]
    tracks  = []
    if all_wy:
        comps = _chain_all(all_wy)
        main  = max(comps, key=len)
        if len(main) >= 2:
            ts = _closest_idx(main, sliced[0]['lat'],  sliced[0]['lon'])
            te = _closest_idx(main, sliced[-1]['lat'], sliced[-1]['lon'])
            ts, te = min(ts, te), max(ts, te)
            trimmed = main[ts:te + 1]
            if len(trimmed) >= 2:
                tracks.append(trimmed)
    if not tracks:
        tracks = [[[s['lat'], s['lon']] for s in sliced]]
    return {'stations': sliced, 'track_segments': tracks}


def _connector_legs(from_lat, from_lon, to_lat, to_lon, label):
    dist = _hav(from_lat, from_lon, to_lat, to_lon)
    if dist <= 1500:
        seg, d, t = _walk_seg(from_lat, from_lon, to_lat, to_lon, label)
        return ([seg] if seg else []), d, t
    try:
        jr = get_jeepney_route(from_lon, from_lat, to_lon, to_lat)
        if "error" not in jr and jr.get("routes"):
            r    = jr["routes"][0]
            segs = r.get("segments", [])
            if segs:
                dtotal = sum(_poly_dist(s['coords']) for s in segs
                             if len(s.get('coords', [])) >= 2)
                try:
                    tsec = int(r.get("time", "0").replace("~", "").replace(" mins", "")) * 60
                except Exception:
                    tsec = max(60, int(dtotal / 5))
                return segs, dtotal, tsec
    except Exception:
        pass
    seg, d, t = _walk_seg(from_lat, from_lon, to_lat, to_lon, label)
    return ([seg] if seg else []), d, t


def _build_train_card(lid, td, meta, olat, olon, dlat, dlon, cid,
                      segs_ov=None, name_ov=None):
    fn = "_build_train_card"
    t_start = time.time()
    print(f"[DEBUG][{fn}] Building train card  lid={lid}  cid={cid}")
    meta  = meta or _TRAIN_META.get(lid, {"color": "#8e44ad", "label": lid,
                                          "subtitle": "", "emoji": "🚇"})
    s_s   = td['stations'][0]
    s_e   = td['stations'][-1]

    if segs_ov is not None:
        segs = segs_ov
    else:
        segs   = []
        in_s, _, _ = _connector_legs(olat, olon, s_s['lat'], s_s['lon'], f"To {s_s['name']}")
        segs.extend(in_s)
        track = td['track_segments']
        flat  = [c for sg in track for c in sg]
        segs.append({'type': 'train', 'coords': track, 'flat': flat,
                     'color': meta['color'], 'label': meta['label'],
                     'stations': td['stations']})
        out_s, _, _ = _connector_legs(s_e['lat'], s_e['lon'], dlat, dlon, "To destination")
        segs.extend(out_s)

    all_c = []
    for sg in segs:
        if sg['type'] == 'train':
            all_c.extend(sg.get('flat') or [c for t in sg['coords'] for c in t])
        else:
            all_c.extend(sg['coords'])

    tmin = 0
    tdist = 0.0
    for sg in segs:
        if sg['type'] == 'train':
            d = sum(_poly_dist(s) for s in sg['coords'])
            tmin  += max(1, int(d / (40_000 / 60)))
            tdist += d
        else:
            d = _poly_dist(sg['coords']) if len(sg['coords']) >= 2 else 0
            tmin  += max(1, int(d / (1.2 * 60)))
            tdist += d

    sc = len(td['stations'])
    print(f"[DEBUG][{fn}] Train card done  stops={sc}  dist={tdist/1000:.1f}km  "
          f"time={tmin}m  elapsed={time.time()-t_start:.3f}s")
    return {
        "id"           : cid,
        "name"         : name_ov or meta['label'],
        "subtitle"     : meta.get('subtitle', ''),
        "type"         : "transit",
        "color"        : meta['color'],
        "emoji"        : meta.get('emoji', '🚇'),
        "time"         : f"~{tmin} mins",
        "distance"     : f"{tdist/1000:.1f} km",
        "coords"       : all_c,
        "segments"     : segs,
        "stations"     : td['stations'],
        "station_count": sc,
        "safety_score" : 88,
        "hazards_flagged": f"{sc} stops · {s_s['name']} → {s_e['name']}",
    }


def _build_xfer_card(la, da, ma, lb, db, mb, xfer, olat, olon, dlat, dlon, cid):
    fn = "_build_xfer_card"
    t_start = time.time()
    print(f"[DEBUG][{fn}] Building transfer card  {la}→{lb}  cid={cid}")
    sa_s = da['stations'][0]
    sa_e = da['stations'][-1]
    sb_s = db['stations'][0]
    sb_e = db['stations'][-1]
    segs = []
    w, _, _ = _walk_seg(olat, olon, sa_s['lat'], sa_s['lon'], f"Walk to {sa_s['name']}")
    if w: segs.append(w)
    ta = da['track_segments']
    segs.append({'type': 'train', 'coords': ta, 'flat': [c for s in ta for c in s],
                 'color': ma['color'], 'label': ma['label'], 'stations': da['stations']})
    wx, _, _ = _walk_seg(sa_e['lat'], sa_e['lon'], sb_s['lat'], sb_s['lon'], xfer['label'])
    segs.append(wx or {'type': 'walk', 'coords': [[sa_e['lat'], sa_e['lon']],
                                                    [sb_s['lat'], sb_s['lon']]],
                        'color': '#95a5a6', 'label': xfer['label']})
    tb = db['track_segments']
    segs.append({'type': 'train', 'coords': tb, 'flat': [c for s in tb for c in s],
                 'color': mb['color'], 'label': mb['label'], 'stations': db['stations']})
    wo, _, _ = _walk_seg(sb_e['lat'], sb_e['lon'], dlat, dlon, "Walk to destination")
    if wo: segs.append(wo)
    merged = {'stations': da['stations'] + db['stations'],
              'track_segments': ta + tb}
    cm = {**ma, 'label': f"{ma['label']} + {mb['label']}",
          'subtitle': f"Transfer at {sa_e['name']} → {sb_s['name']}", 'emoji': '🔄'}
    print(f"[DEBUG][{fn}] Transfer card built  elapsed={time.time()-t_start:.3f}s")
    return _build_train_card(la, merged, cm, olat, olon, dlat, dlon, cid,
                             segs_ov=segs, name_ov=f"{ma['label']} + {mb['label']}")


def plan_transit_journey(orig_lon, orig_lat, dest_lon, dest_lat):
    """Plan LRT/MRT journey using Overpass data. Fetches all lines in parallel."""
    fn = "plan_transit_journey"
    t_start = time.time()
    print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
    print(f"[DEBUG][{fn}] CALL: plan_transit_journey()")
    print(f"[DEBUG][{fn}]   Origin={orig_lat:.6f},{orig_lon:.6f}  Dest={dest_lat:.6f},{dest_lon:.6f}")
    MAX_WALK = 800
    results  = []
    cid      = 0

    # Fetch all lines concurrently
    print(f"[DEBUG][{fn}] STEP 1 · Fetching all LRT/MRT lines concurrently...")
    t1 = time.time()
    line_ids = ["lrt-1", "lrt-2", "mrt-3"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(line_ids)) as ex:
        line_futures = {ex.submit(_fetch_full_line, lid): lid for lid in line_ids}
        line_data    = {lid: future.result()
                        for future, lid in [(f, line_futures[f])
                                            for f in concurrent.futures.as_completed(line_futures)]}
    print(f"[DEBUG][{fn}] STEP 1 · Lines fetched  elapsed={time.time()-t1:.3f}s")

    # Evaluate direct routes
    print(f"[DEBUG][{fn}] STEP 2 · Evaluating direct line candidates...")
    t2 = time.time()
    direct = []

    def check_direct(lid):
        st, wy = line_data.get(lid, (None, None))
        if not st:
            return None
        td = _slice_line(st, wy, orig_lat, orig_lon, dest_lat, dest_lon)
        if not td:
            return None
        ws = _osrm_walk_dist_cached(orig_lat, orig_lon,
                                    td['stations'][0]['lat'], td['stations'][0]['lon'])
        we = _osrm_walk_dist_cached(dest_lat, dest_lon,
                                    td['stations'][-1]['lat'], td['stations'][-1]['lon'])
        if ws and ws <= MAX_WALK and we and we <= MAX_WALK:
            return {'lid': lid, 'td': td, 'walk': ws + we, 'meta': _TRAIN_META[lid]}
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(line_ids)) as ex:
        direct_results = list(ex.map(check_direct, line_ids))
    direct = [r for r in direct_results if r]
    print(f"[DEBUG][{fn}] STEP 2 · Direct candidates={len(direct)}  elapsed={time.time()-t2:.3f}s")

    # Evaluate transfer routes
    print(f"[DEBUG][{fn}] STEP 3 · Evaluating interchange candidates...")
    t3 = time.time()
    xfers = []

    def check_xfer(xfer):
        l1, l2 = xfer['from_line'], xfer['to_line']
        st_a, wy_a = line_data.get(l1, (None, None))
        st_b, wy_b = line_data.get(l2, (None, None))
        td_a = _slice_line(st_a, wy_a, orig_lat, orig_lon, xfer['lat'], xfer['lon']) if st_a else None
        td_b = _slice_line(st_b, wy_b, xfer['lat'], xfer['lon'], dest_lat, dest_lon) if st_b else None
        if not (td_a and td_b):
            return None
        ws = _osrm_walk_dist_cached(orig_lat, orig_lon,
                                    td_a['stations'][0]['lat'], td_a['stations'][0]['lon'])
        we = _osrm_walk_dist_cached(dest_lat, dest_lon,
                                    td_b['stations'][-1]['lat'], td_b['stations'][-1]['lon'])
        if ws and ws <= MAX_WALK and we and we <= MAX_WALK:
            return {'xfer': xfer, 'td_a': td_a, 'td_b': td_b,
                    'walk': ws + we,
                    'meta_a': _TRAIN_META[l1], 'meta_b': _TRAIN_META[l2]}
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(_TRANSFERS)) as ex:
        xfer_results = list(ex.map(check_xfer, _TRANSFERS))
    xfers = [r for r in xfer_results if r]
    print(f"[DEBUG][{fn}] STEP 3 · Interchange candidates={len(xfers)}  elapsed={time.time()-t3:.3f}s")

    direct.sort(key=lambda x: x['walk'])
    xfers.sort(key=lambda x: x['walk'])

    if direct:
        b = direct[0]
        results.append(_build_train_card(b['lid'], b['td'], b['meta'],
                                         orig_lat, orig_lon, dest_lat, dest_lon, 0))
    if xfers:
        cid += 1
        b = xfers[0]
        results.append(_build_xfer_card(b['meta_a']['label'].lower(), b['td_a'], b['meta_a'],
                                        b['meta_b']['label'].lower(), b['td_b'], b['meta_b'],
                                        b['xfer'], orig_lat, orig_lon, dest_lat, dest_lon, cid))

    print(f"[DEBUG][{fn}] Done  results={len(results)}  total={time.time()-t_start:.3f}s")
    print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
    if not results:
        return {"error": "No LRT/MRT station found within walking distance. "
                         "Try Jeepney, Bus, or Jeepney/Bus mode."}
    return {"routes": results}


# ════════════════════════════════════════════════════════════════════════════════
#  ROAD ROUTES
# ════════════════════════════════════════════════════════════════════════════════

_OSRM_DRIVE = "https://router.project-osrm.org/route/v1/driving"


def _osrm_road(olon, olat, dlon, dlat, mode_label, colors):
    fn = "_osrm_road"
    t_start = time.time()
    url = (f"{_OSRM_DRIVE}/{olon},{olat};{dlon},{dlat}"
           f"?overview=full&geometries=geojson&alternatives=3&steps=true")
    print(f"[DEBUG][{fn}] Requesting road routes  mode={mode_label}")
    print(f"[DEBUG][{fn}]   URL: {url[:100]}...")
    try:
        t_req = time.time()
        r = requests.get(url, headers={'User-Agent': 'SafeRouteAI'}, timeout=10).json()
        print(f"[DEBUG][{fn}]   OSRM responded {time.time()-t_req:.3f}s  code={r.get('code')}")
        if r.get("code") != "Ok":
            return {"error": "Could not calculate road route."}
    except Exception as e:
        print(f"[DEBUG][{fn}]   !! Exception: {e}")
        return {"error": "Routing server unavailable."}

    routes = []
    for i, route in enumerate(r.get("routes", [])[:3]):
        coords = [[pt[1], pt[0]] for pt in route["geometry"]["coordinates"]]
        routes.append({
            "id"            : i,
            "name"          : f"{mode_label} Route {i+1}",
            "type"          : "road",
            "color"         : colors[i % len(colors)],
            "time"          : f"{int(route['duration']/60)} mins",
            "distance"      : f"{round(route['distance']/1000, 1)} km",
            "coords"        : coords,
            "segments"      : [],
            "stations"      : [],
            "safety_score"  : 80,
            "hazards_flagged": "Clear",
        })
    print(f"[DEBUG][{fn}] Done  routes={len(routes)}  elapsed={time.time()-t_start:.3f}s")
    return {"routes": routes}


def get_car_route(olon, olat, dlon, dlat):
    print(f"[DEBUG][get_car_route] ({olat:.5f},{olon:.5f}) → ({dlat:.5f},{dlon:.5f})")
    return _osrm_road(olon, olat, dlon, dlat, "Car",
                      ["#3498db", "#1a6fa3", "#0e3d5c"])


def get_motorcycle_route(olon, olat, dlon, dlat):
    print(f"[DEBUG][get_motorcycle_route] ({olat:.5f},{olon:.5f}) → ({dlat:.5f},{dlon:.5f})")
    return _osrm_road(olon, olat, dlon, dlat, "Motorcycle",
                      ["#8e44ad", "#9b59b6", "#af7ac5"])


def get_walk_route(olon, olat, dlon, dlat):
    fn = "get_walk_route"
    t_start = time.time()
    print(f"[DEBUG][{fn}] ({olat:.5f},{olon:.5f}) → ({dlat:.5f},{dlon:.5f})")
    r = _fetch_osrm_foot(olon, olat, dlon, dlat)
    if r:
        names  = ["Walking Route", "Alternative Walk", "Scenic Walk"]
        colors = ["#2ecc71", "#27ae60", "#1abc9c"]
        out    = []
        for i, route in enumerate(r["routes"][:3]):
            coords = [[pt[1], pt[0]] for pt in route["geometry"]["coordinates"]]
            out.append({
                "id"            : i,
                "name"          : names[i] if i < len(names) else f"Walk {i+1}",
                "type"          : "walk",
                "color"         : colors[i % len(colors)],
                "time"          : f"{int(route['duration']/60)} mins",
                "distance"      : f"{round(route['distance']/1000, 1)} km",
                "coords"        : coords,
                "segments"      : [],
                "stations"      : [],
                "safety_score"  : 90,
                "hazards_flagged": "Pedestrian paths only",
            })
        if out:
            out[0]["mode_label"] = "Only Route" if len(out) == 1 else "Fastest"
            if len(out) > 1: out[1]["mode_label"] = "Alternative"
            if len(out) > 2: out[2]["mode_label"] = "Scenic"
        print(f"[DEBUG][{fn}] Done  routes={len(out)}  elapsed={time.time()-t_start:.3f}s")
        return {"routes": out}
    print(f"[DEBUG][{fn}] !! Walk route failed  elapsed={time.time()-t_start:.3f}s")
    return {"error": "Could not calculate walking route."}


# ════════════════════════════════════════════════════════════════════════════════
#  NEARBY TRANSIT
# ════════════════════════════════════════════════════════════════════════════════

def get_nearby_transit(lat, lon, radius_m=1000):
    fn = "get_nearby_transit"
    t_start = time.time()
    print(f"[DEBUG][{fn}] ── START ────────────────────────────────────────────────")
    print(f"[DEBUG][{fn}] CALL: get_nearby_transit({lat:.6f}, {lon:.6f}, radius={radius_m}m)")

    # Ensure both data sources are loaded
    print(f"[DEBUG][{fn}] STEP 1 · Loading data sources concurrently...")
    t1 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        f_jeep  = ex.submit(_load_jeepney)
        f_sakay = ex.submit(_load_sakay)
        f_jeep.result()
        f_sakay.result()
    print(f"[DEBUG][{fn}] STEP 1 · Data loaded  elapsed={time.time()-t1:.3f}s")

    nearby = []

    # ── Scan jeepney routes from jeepney.json ─────────────────────────────────
    def scan_jeepney_route(rid):
        route = _JEEPNEY_ROUTES.get(rid)
        if not route:
            return None
        best_s = None
        min_d  = float('inf')
        for s in route['stops']:
            d = _hav(lat, lon, s['lat'], s['lon'])
            if d < min_d:
                min_d, best_s = d, s
        if min_d <= radius_m and best_s:
            rname = route.get('route_long_name', rid)
            if not any(x['name'] == best_s['name'] and x['type'] == 'jeepney' for x in nearby):
                return {
                    'type'      : 'jeepney',
                    'color'     : '#e67e22',
                    'route_name': rname,
                    'name'      : best_s['name'],
                    'lat'       : best_s['lat'],
                    'lon'       : best_s['lon'],
                    'dist'      : min_d,
                    'fare_info' : 'PHP 13 base',
                    'source'    : 'jeepney.json',
                }
        return None

    # ── Scan bus/rail from sakay ──────────────────────────────────────────────
    def scan_sakay_route(rid_ttype_tcolor_fare):
        rid, ttype, tcolor, fare_info = rid_ttype_tcolor_fare
        route = _SAKAY_ROUTES.get(rid)
        if not route:
            return None
        best_s = None
        min_d  = float('inf')
        for s in route['stops']:
            d = _hav(lat, lon, s['lat'], s['lon'])
            if d < min_d:
                min_d, best_s = d, s
        if min_d <= radius_m and best_s:
            rname = route.get('route_long_name', rid)
            if not any(x['name'] == best_s['name'] and x['type'] == ttype for x in nearby):
                return {
                    'type'      : ttype,
                    'color'     : tcolor,
                    'route_name': rname,
                    'name'      : best_s['name'],
                    'lat'       : best_s['lat'],
                    'lon'       : best_s['lon'],
                    'dist'      : min_d,
                    'fare_info' : fare_info,
                    'source'    : 'sakay_gtfs',
                }
        return None

    print(f"[DEBUG][{fn}] STEP 2 · Scanning jeepney routes ({len(_JEEPNEY_PUJ)}) concurrently...")
    t2 = time.time()
    workers_j = min(32, max(1, len(_JEEPNEY_PUJ)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers_j) as ex:
        jeep_results = list(ex.map(scan_jeepney_route, _JEEPNEY_PUJ))
    for r in jeep_results:
        if r:
            nearby.append(r)
    print(f"[DEBUG][{fn}] STEP 2 · Jeepney scan done  hits={sum(1 for r in jeep_results if r)}  "
          f"elapsed={time.time()-t2:.3f}s")

    print(f"[DEBUG][{fn}] STEP 3 · Scanning bus/rail routes concurrently...")
    t3 = time.time()
    sakay_tasks = (
        [(rid, 'bus',   '#16a085', 'PHP 15 base') for rid in _SAKAY_PUB] +
        [(rid, 'train', '#27ae60', 'LRT/MRT fare') for rid in _SAKAY_RAIL]
    )
    workers_s = min(32, max(1, len(sakay_tasks)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers_s) as ex:
        sakay_results = list(ex.map(scan_sakay_route, sakay_tasks))
    for r in sakay_results:
        if r:
            nearby.append(r)
    print(f"[DEBUG][{fn}] STEP 3 · Bus/rail scan done  hits={sum(1 for r in sakay_results if r)}  "
          f"elapsed={time.time()-t3:.3f}s")

    # OSM line cache backup
    for lid, data in _LINE_CACHE.items():
        if not data or not data[0]:
            continue
        stations, _ = data
        best_s = None
        min_d  = float('inf')
        for st in stations:
            d = _hav(lat, lon, st['lat'], st['lon'])
            if d < min_d:
                min_d, best_s = d, st
        if min_d <= radius_m and best_s:
            if not any(x['name'] == best_s['name'] and x['type'] == 'train' for x in nearby):
                nearby.append({'type': 'train', 'color': '#27ae60',
                               'route_name': lid.upper(), 'name': best_s['name'],
                               'lat': best_s['lat'], 'lon': best_s['lon'],
                               'dist': min_d, 'source': 'osm_cache'})

    nearby.sort(key=lambda x: x['dist'])
    final = nearby[:5]
    print(f"[DEBUG][{fn}] STEP 4 · Sorted {len(nearby)} hits → returning top {len(final)}")
    for i, x in enumerate(final):
        print(f"[DEBUG][{fn}]   [{i}] {x['type'].upper()} '{x['route_name']}'  "
              f"stop='{x['name']}'  dist={x['dist']:.0f}m  src={x.get('source','')}")
    print(f"[DEBUG][{fn}] TOTAL DURATION={time.time()-t_start:.3f}s")
    print(f"[DEBUG][{fn}] ──────────────────────────────────────────────────────────")
    return final


# ════════════════════════════════════════════════════════════════════════════════
#  MAIN ENTRYPOINT
# ════════════════════════════════════════════════════════════════════════════════

def _tag_routes(routes, mode_key, label, color):
    for r in routes:
        r.setdefault('mode_label',       label)
        r.setdefault('mode_label_color', color)


def get_navigation_data(orig_lon, orig_lat, dest_lon, dest_lat, commuter_type, flood_zones):
    fn = "get_navigation_data"
    t_start = time.time()
    print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
    print(f"[DEBUG][{fn}] CALL: get_navigation_data()")
    print(f"[DEBUG][{fn}]   commuter_type = '{commuter_type}'")
    print(f"[DEBUG][{fn}]   Origin        = ({orig_lat:.6f}, {orig_lon:.6f})")
    print(f"[DEBUG][{fn}]   Destination   = ({dest_lat:.6f}, {dest_lon:.6f})")
    print(f"[DEBUG][{fn}]   flood_zones   = {flood_zones}")

    ctype          = commuter_type.lower().strip()
    surface_types  = ('transit', 'jeepney', 'bus', 'train',
                      'jeepney_bus', 'train_jeepney', 'train_bus')
    dist_crow      = _hav(orig_lat, orig_lon, dest_lat, dest_lon)
    print(f"[DEBUG][{fn}]   Crow-flies distance = {dist_crow:.0f}m")

    # Walk bypass for very short distances in transit modes
    if dist_crow <= 1000 and ctype in surface_types:
        print(f"[DEBUG][{fn}]   Walk bypass triggered (dist ≤ 1000m)")
        r = get_walk_route(orig_lon, orig_lat, dest_lon, dest_lat)
        print(f"[DEBUG][{fn}] Done (walk bypass)  elapsed={time.time()-t_start:.3f}s")
        print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
        return r

    # ── Jeepney only ──────────────────────────────────────────────────────────
    if ctype == 'jeepney':
        print(f"[DEBUG][{fn}] Branch: JEEPNEY ONLY → plan_jeepney_journey()")
        r = get_jeepney_route(orig_lon, orig_lat, dest_lon, dest_lat)
        _tag_routes(r.get('routes', []), 'jeepney', 'Jeepney', '#e67e22')
        print(f"[DEBUG][{fn}] Done  elapsed={time.time()-t_start:.3f}s")
        print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
        return r

    # ── Bus only ──────────────────────────────────────────────────────────────
    if ctype == 'bus':
        print(f"[DEBUG][{fn}] Branch: BUS ONLY → plan_surface_journey(['bus'])")
        r = get_bus_route(orig_lon, orig_lat, dest_lon, dest_lat)
        print(f"[DEBUG][{fn}] Done  elapsed={time.time()-t_start:.3f}s")
        print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
        return r

    # ── Jeepney + Bus ─────────────────────────────────────────────────────────
    if ctype == 'jeepney_bus':
        print(f"[DEBUG][{fn}] Branch: JEEPNEY + BUS → plan_surface_journey(['jeepney','bus'])")
        r = get_jeepney_bus_route(orig_lon, orig_lat, dest_lon, dest_lat)
        print(f"[DEBUG][{fn}] Done  elapsed={time.time()-t_start:.3f}s")
        print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
        return r

    # ── Train only ────────────────────────────────────────────────────────────
    if ctype == 'train':
        print(f"[DEBUG][{fn}] Branch: TRAIN ONLY → plan_transit_journey() + plan_surface_journey(['train'])")
        r = plan_transit_journey(orig_lon, orig_lat, dest_lon, dest_lat)
        # Fallback to sakay rail if overpass returned nothing
        if not r.get('routes'):
            print(f"[DEBUG][{fn}]   Overpass train failed → trying sakay rail...")
            native = plan_surface_journey(['train'], orig_lat, orig_lon,
                                          dest_lat, dest_lon, max_results=2)
            if native:
                r = {'routes': native}
        _tag_routes(r.get('routes', []), 'train', 'Train', '#27ae60')
        print(f"[DEBUG][{fn}] Done  elapsed={time.time()-t_start:.3f}s")
        print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
        return r

    # ── Walk ──────────────────────────────────────────────────────────────────────
    if ctype in ('walk', 'walking', 'foot', 'pedestrian'):
        print(f"[DEBUG][{fn}] Branch: WALK → get_walk_route()")
        r = get_walk_route(orig_lon, orig_lat, dest_lon, dest_lat)
        _tag_routes(r.get('routes', []), 'walk', 'Walking', '#2ecc71')
        print(f"[DEBUG][{fn}] Done  elapsed={time.time()-t_start:.3f}s")
        print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
        return r

    # ── Car / driving ─────────────────────────────────────────────────────────────
    if ctype in ('car', 'drive', 'driving', 'auto'):
        print(f"[DEBUG][{fn}] Branch: CAR → get_car_route()")
        r = get_car_route(orig_lon, orig_lat, dest_lon, dest_lat)
        _tag_routes(r.get('routes', []), 'car', 'Car', '#3498db')
        print(f"[DEBUG][{fn}] Done  elapsed={time.time()-t_start:.3f}s")
        print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
        return r

    # ── Motorcycle ────────────────────────────────────────────────────────────────
    if ctype in ('motorcycle', 'motor', 'motorbike', 'bike', 'moto'):
        print(f"[DEBUG][{fn}] Branch: MOTORCYCLE → get_motorcycle_route()")
        r = get_motorcycle_route(orig_lon, orig_lat, dest_lon, dest_lat)
        _tag_routes(r.get('routes', []), 'motorcycle', 'Motorcycle', '#8e44ad')
        print(f"[DEBUG][{fn}] Done  elapsed={time.time()-t_start:.3f}s")
        print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
        return r

    # ── Generic commute (alias for transit) ───────────────────────────────────────
    if ctype == 'commute':
        print(f"[DEBUG][{fn}] Branch: COMMUTE (alias → transit)")
        ctype = 'transit'
        # fall-through intentional — handled by the multimodal block below
    # Multimodal fall-through for commute↓

    # ── Multimodal (transit / train_jeepney / train_bus / commute) ───────────────
    if ctype in ('transit', 'train_jeepney', 'train_bus', 'commute'):
        print(f"[DEBUG][{fn}] Branch: MULTIMODAL ({ctype})")
        surface_modes = []
        if ctype in ('transit', 'train_jeepney', 'commute'): surface_modes.append('jeepney')
        if ctype in ('transit', 'train_bus', 'commute'):     surface_modes.append('bus')
        surface_modes.append('train')
        if not surface_modes:
            surface_modes = ['jeepney', 'bus', 'train']

        print(f"[DEBUG][{fn}]   Surface modes to plan: {surface_modes}")

        # Run surface + OSM train concurrently
        def run_surface():
            print(f"[DEBUG][{fn}][run_surface] → plan_surface_journey({surface_modes})")
            return plan_surface_journey(surface_modes, orig_lat, orig_lon,
                                        dest_lat, dest_lon, max_results=3)

        def run_osm_train():
            if 'train' not in surface_modes:
                return []
            print(f"[DEBUG][{fn}][run_osm_train] → plan_transit_journey()")
            tr = plan_transit_journey(orig_lon, orig_lat, dest_lon, dest_lat)
            if "error" not in tr:
                routes = tr.get('routes', [])
                _tag_routes(routes, 'train', 'Train (OSM)', '#27ae60')
                return routes
            return []

        print(f"[DEBUG][{fn}]   Dispatching surface + OSM train concurrently...")
        t_dispatch = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            f_surf  = ex.submit(run_surface)
            f_train = ex.submit(run_osm_train)
            surface_routes = f_surf.result()
            train_routes   = f_train.result()
        print(f"[DEBUG][{fn}]   Dispatch done  surface={len(surface_routes)}  "
              f"osm_train={len(train_routes)}  elapsed={time.time()-t_dispatch:.3f}s")

        # Label surface routes by dominant mode
        for r in surface_routes:
            segs      = [s for s in r.get('segments', []) if s['type'] not in ('walk',)]
            has_train = any(s['type'] == 'train'   for s in segs)
            has_bus   = any(s['type'] == 'bus'     for s in segs)
            has_jeep  = any(s['type'] == 'jeepney' for s in segs)
            num_jeep_segs = sum(1 for s in segs if s['type'] == 'jeepney')
            if has_train:
                label = 'Train + Connect' if (has_bus or has_jeep) else 'Train'
                r.setdefault('mode_label', label)
                r.setdefault('mode_label_color', '#27ae60')
            elif has_bus and has_jeep:
                r.setdefault('mode_label', 'Jeepney + Bus')
                r.setdefault('mode_label_color', '#2980b9')
            elif has_bus:
                r.setdefault('mode_label', 'Bus')
                r.setdefault('mode_label_color', '#16a085')
            elif num_jeep_segs >= 2:
                # Two-jeepney transfer route — label clearly to distinguish from direct
                r.setdefault('mode_label', 'Jeepney (Transfer)')
                r.setdefault('mode_label_color', '#d35400')
            else:
                r.setdefault('mode_label', 'Jeepney')
                r.setdefault('mode_label_color', '#e67e22')

        combined = surface_routes + train_routes
        if not combined:
            print(f"[DEBUG][{fn}] !! Zero routes recovered from all pipelines")
            print(f"[DEBUG][{fn}] Attempting OSRM road fallback for transit...")
            try:
                osrm_url = (
                    f"https://router.project-osrm.org/route/v1/driving/"
                    f"{orig_lon},{orig_lat};{dest_lon},{dest_lat}"
                    f"?overview=full&geometries=geojson&alternatives=true&steps=true"
                )
                resp = requests.get(osrm_url, timeout=15)
                osrm = resp.json()
                if osrm.get('code') == 'Ok' and osrm.get('routes'):
                    fallback = []
                    labels = ['Fastest', 'Balanced', 'Alternate']
                    colors = ['#2980b9', '#27ae60', '#7f8c8d']
                    for fi, rt in enumerate(osrm['routes'][:3]):
                        dur_min = int(rt['duration'] / 60)
                        dist_km = round(rt['distance'] / 1000, 1)
                        all_coords = [[c[1], c[0]] for c in rt['geometry']['coordinates']]

                        # Build segments from OSRM legs/steps for per-segment coloring
                        segments = []
                        for leg in rt.get('legs', []):
                            for step in leg.get('steps', []):
                                step_geom = step.get('geometry', {})
                                step_coords = [[c[1], c[0]] for c in step_geom.get('coordinates', [])]
                                if len(step_coords) < 2:
                                    continue
                                mode_hint = step.get('mode', 'driving')
                                seg_type = 'walk' if mode_hint == 'walking' else 'transit'
                                segments.append({
                                    'type': seg_type,
                                    'coords': step_coords,
                                    'label': step.get('name', 'Transit route'),
                                    'duration': int(step.get('duration', 0) / 60),
                                })

                        # Fall back to single segment if steps not available
                        if not segments:
                            segments = [{'type': 'transit', 'coords': all_coords,
                                         'label': 'Transit Route', 'duration': dur_min}]

                        fallback.append({
                            'id': fi,
                            'name': f"Transit Route {fi+1}",
                            'time': f"{dur_min} mins",
                            'distance': f"{dist_km} km",
                            'mode_label': labels[fi] if fi < len(labels) else f"Route {fi+1}",
                            'mode_label_color': colors[fi] if fi < len(colors) else '#7f8c8d',
                            'coords': all_coords,
                            'segments': segments,
                        })
                    if fallback:
                        print(f"[DEBUG][{fn}] OSRM fallback succeeded: {len(fallback)} routes")
                        combined = fallback
            except Exception as fe:
                print(f"[DEBUG][{fn}] OSRM fallback failed: {fe}")

        if not combined:
            print(f"[DEBUG][{fn}] !! All pipelines exhausted — no route found")
            print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
            return {"error": "No route found near your origin/destination."}

        # Deduplicate by route name
        unique = []
        seen   = set()
        for r in combined:
            if r['name'] not in seen:
                seen.add(r['name'])
                unique.append(r)
        for i, r in enumerate(unique):
            r['id'] = i

        print(f"[DEBUG][{fn}]   Final unique routes = {len(unique)}")
        for i, r in enumerate(unique):
            print(f"[DEBUG][{fn}]   [{i}] '{r['name']}'  {r['time']}  "
                  f"{r['distance']}  label={r.get('mode_label','')}")
        print(f"[DEBUG][{fn}] Done  total={time.time()-t_start:.3f}s")
        print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
        return {"routes": unique}

    print(f"[DEBUG][{fn}] !! Unhandled commuter_type='{ctype}'  elapsed={time.time()-t_start:.3f}s")
    print(f"[DEBUG][{fn}] ══════════════════════════════════════════════════════════")
    return {"error": f"Unhandled commuter type: '{commuter_type}'"}


print(f"[DEBUG][INIT] navigation.py loaded successfully in {time.time()-t_nav_init:.3f}s")
print(f"[DEBUG][INIT] Data sources: jeepney.json (jeepney) · sakay_all_routes.json (bus/rail)")
print(f"[DEBUG][INIT] Pipeline: geometry-only candidate selection → OSRM leg building")
print(f"[DEBUG][INIT] ═══════════════════════════════════════════════════════════════════")