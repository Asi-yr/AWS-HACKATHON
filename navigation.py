import requests, time, json, math, os, concurrent.futures
from collections import defaultdict

print("[DEBUG][INIT] ═══════════════════════════════════════════════════════════════════")
print("[DEBUG][INIT] Loading navigation.py  ·  jeepney.json edition")
print("[DEBUG][INIT] ═══════════════════════════════════════════════════════════════════")
t_nav_init = time.time()

def _dbg(tag, msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[DEBUG][{tag}] [{ts}] {msg}")

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

# Lightweight in-memory short-term cache to avoid repeating identical heavy queries
_OVERPASS_QUERY_CACHE = {}          # query_text -> (timestamp, parsed_json)
_OVERPASS_CACHE_TTL = 8.0          # seconds to keep a cached response

# Per-endpoint cooldown tracker to avoid hammering endpoints that recently returned 429/errors
_OVERPASS_EP_COOLDOWN = {}         # endpoint -> next_allowed_epoch
_OVERPASS_EP_BASE_COOLDOWN = 8.0   # seconds base cooldown after a failure

def _split_bbox_query(query):
    """
    If the query contains a bbox placeholder pattern like '{{bbox}}' or 'bbox',
    attempt to split into 4 tiles (2x2) by replacing a simple bbox token.
    This is conservative: only used when query is very large and contains an explicit bbox token.
    Returns list of subqueries or None if not splittable.
    """
    fn = "_split_bbox_query"
    if "{{bbox}}" not in query and "bbox" not in query:
        _dbg(fn, "No bbox token found; skipping split")
        return None

    # Try to extract an explicit bbox if present in the form: (south,west,north,east)
    # This is best-effort; if we can't parse, return None.
    import re
    m = re.search(r"\(\s*([-0-9\.]+)\s*,\s*([-0-9\.]+)\s*,\s*([-0-9\.]+)\s*,\s*([-0-9\.]+)\s*\)", query)
    if not m:
        _dbg(fn, "No explicit bbox coords found; will not split")
        return None

    south, west, north, east = map(float, m.groups())
    _dbg(fn, f"Splitting bbox {south},{west},{north},{east} into 4 tiles")

    mid_lat = (south + north) / 2.0
    mid_lon = (west + east) / 2.0

    tiles = [
        (south, west, mid_lat, mid_lon),
        (south, mid_lon, mid_lat, east),
        (mid_lat, west, north, mid_lon),
        (mid_lat, mid_lon, north, east),
    ]

    subqueries = []
    for (s, w, n, e) in tiles:
        bbox_str = f"{s},{w},{n},{e}"
        # Replace common bbox tokens; try both '{{bbox}}' and the explicit original bbox string
        if "{{bbox}}" in query:
            subq = query.replace("{{bbox}}", bbox_str)
        else:
            # replace the first occurrence of the original bbox coords with the tile bbox
            subq = re.sub(r"\(\s*[-0-9\.]+\s*,\s*[-0-9\.]+\s*,\s*[-0-9\.]+\s*,\s*[-0-9\.]+\s*\)",
                          f"({bbox_str})", query, count=1)
        subqueries.append(subq)
    return subqueries

def _overpass_query(query, max_retries=5, timeout=30):
    """
    Robust Overpass query with:
      - short-term caching
      - per-endpoint cooldowns
      - exponential backoff + jitter
      - optional bbox splitting (safe, conservative)
      - bounded parallel endpoint probing (small pool)
    Returns parsed JSON or None on failure.
    """
    fn = "_overpass_query"
    t_start = time.time()
    _dbg(fn, f"START payload={len(query)}chars max_retries={max_retries} timeout={timeout}s")

    # 1) Short-term cache check
    now = time.time()
    cached = _OVERPASS_QUERY_CACHE.get(query)
    if cached:
        ts, data = cached
        if now - ts <= _OVERPASS_CACHE_TTL:
            _dbg(fn, f"CACHE HIT (age={now-ts:.2f}s) returning cached response")
            return data
        else:
            _dbg(fn, f"CACHE EXPIRED (age={now-ts:.2f}s)")

    # 2) If query is huge and contains bbox token, attempt safe split into tiles
    if len(query) > 16000:
        subqs = _split_bbox_query(query)
        if subqs:
            _dbg(fn, f"Large query detected; executing {len(subqs)} subqueries and merging results")
            merged = {'elements': []}
            for i, sq in enumerate(subqs, 1):
                _dbg(fn, f"Subquery {i}/{len(subqs)} length={len(sq)}")
                res = _overpass_query(sq, max_retries=max_retries, timeout=timeout)
                if res and isinstance(res, dict):
                    merged['elements'].extend(res.get('elements', []))
                else:
                    _dbg(fn, f"Subquery {i} failed; aborting merged result")
                    return None
            # cache merged result briefly
            _OVERPASS_QUERY_CACHE[query] = (time.time(), merged)
            _dbg(fn, f"Subqueries merged elements={len(merged['elements'])} total_elapsed={time.time()-t_start:.3f}s")
            return merged
        else:
            _dbg(fn, "Large query but not splittable; proceeding without split")

    # 3) Endpoint probing with cooldowns and backoff
    # Prepare endpoints order rotated by attempt to spread load
    endpoints = list(_OVERPASS)

    # Helper to attempt a single endpoint once
    def _attempt_endpoint(ep):
        # Respect per-endpoint cooldown
        next_allowed = _OVERPASS_EP_COOLDOWN.get(ep, 0.0)
        if time.time() < next_allowed:
            _dbg(fn, f"Skipping {ep} due to cooldown until {next_allowed:.1f}")
            return None, f"cooldown_until_{next_allowed:.1f}"

        try:
            t_req = time.time()
            r = requests.post(ep, data=query, headers={'User-Agent': 'SafeRoute/1.0'}, timeout=timeout)
            _dbg(fn, f"HTTP {r.status_code} from {ep} in {time.time()-t_req:.3f}s")
            # Handle 429 explicitly
            if r.status_code == 429:
                retry_after = r.headers.get('Retry-After')
                cooldown = _OVERPASS_EP_BASE_COOLDOWN
                if retry_after:
                    try:
                        cooldown = max(cooldown, float(retry_after))
                    except Exception:
                        pass
                _OVERPASS_EP_COOLDOWN[ep] = time.time() + cooldown
                _dbg(fn, f"429 from {ep}; setting cooldown {cooldown}s (until {_OVERPASS_EP_COOLDOWN[ep]:.1f})")
                return None, "429"
            r.raise_for_status()
            # Defensive JSON decode
            try:
                res_json = r.json()
            except ValueError as e:
                _dbg(fn, f"JSON decode error from {ep}: {e}")
                # If body empty or invalid, penalize endpoint a bit
                _OVERPASS_EP_COOLDOWN[ep] = time.time() + _OVERPASS_EP_BASE_COOLDOWN
                return None, f"json_error:{e}"
            el_count = len(res_json.get('elements', []))
            _dbg(fn, f"JSON OK from {ep} elements={el_count} total_elapsed={time.time()-t_start:.3f}s")
            return res_json, None
        except requests.exceptions.RequestException as e:
            _dbg(fn, f"RequestException from {ep}: {e}")
            # penalize endpoint on network errors
            _OVERPASS_EP_COOLDOWN[ep] = time.time() + _OVERPASS_EP_BASE_COOLDOWN
            return None, str(e)
        except Exception as e:
            _dbg(fn, f"Unexpected exception from {ep}: {e}")
            _OVERPASS_EP_COOLDOWN[ep] = time.time() + _OVERPASS_EP_BASE_COOLDOWN
            return None, str(e)

    # Try up to max_retries rounds; in each round probe endpoints in rotated order.
    for attempt in range(1, max_retries + 1):
        # rotate endpoints to spread load across servers
        start_idx = (attempt - 1) % len(endpoints)
        eps = endpoints[start_idx:] + endpoints[:start_idx]
        _dbg(fn, f"Attempt {attempt}/{max_retries} probing {len(eps)} endpoints")

        # Probe endpoints sequentially but allow a small parallelism for speed (bounded)
        # We will try up to 2 endpoints in parallel to reduce latency while avoiding flood.
        max_parallel = min(2, len(eps))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_parallel) as ex:
            futures = { ex.submit(_attempt_endpoint, ep): ep for ep in eps }
            # as soon as one returns a valid JSON, cancel remaining
            for fut in concurrent.futures.as_completed(futures):
                ep = futures[fut]
                res, err = fut.result()
                if res is not None:
                    # cache and return
                    _OVERPASS_QUERY_CACHE[query] = (time.time(), res)
                    _dbg(fn, f"SUCCESS from {ep} on attempt {attempt}")
                    return res
                else:
                    _dbg(fn, f"FAIL {ep} on attempt {attempt} err={err}")

        # If we reach here, no endpoint returned valid JSON this round
        # Exponential backoff with jitter before next round
        if attempt < max_retries:
            backoff = min(30, (2 ** attempt))
            # jitter up to 25% of backoff
            import random
            jitter = backoff * 0.15 * (random.random() - 0.5)
            sleep_s = max(1.0, backoff + jitter)
            _dbg(fn, f"No success this round; sleeping {sleep_s:.1f}s before retry")
            time.sleep(sleep_s)

    _dbg(fn, f"ALL {max_retries} attempts failed elapsed={time.time()-t_start:.3f}s")
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
_JEEPNEY_SHAPE_CACHE = {}   # rid -> {'poly': [[lat,lon],...], 'dist': meters}

# Spatial index: (lat_cell, lon_cell) → [(rid, point_tag, lat, lon)]
# Indexed at: start, destination, and N intermediate sample points per route.
_JEEPNEY_SPATIAL = defaultdict(list)
_JEEPNEY_CELL    = 0.008        # ~890 m per cell
_JEEPNEY_SAMPLES = 12           # intermediate line-sample points per route (more = better spatial coverage)

# Distance thresholds (metres)
_JBOARD_LIM  = 800              # max walk from user to board point on route
_JALIGHT_LIM = 1000             # max walk from alight point to user destination
_JXFER_LIM   = 800              # max walk for a jeepney→jeepney transfer (was 600)
_JXFER_PEN   = 300              # transfer penalty (added to candidate score)

_OSRM_HDRS = {'User-Agent': 'SafeRouteAI/1.0'}

def _snip_poly(poly, i0, i1):
    if not poly:
        return []
    if i0 == i1:
        return [poly[i0]]
    if i0 < i1:
        return poly[i0:i1+1]
    return list(reversed(poly[i1:i0+1]))

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
    global _JEEPNEY_ROUTES
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    raw_routes = data.get("routes", [])

    def build(idx_raw):
        idx, raw = idx_raw
        name = raw.get("route_transit", f"Route_{idx}")
        s = raw.get("start", {})
        d = raw.get("destination", {})
        slat, slon = s.get("lat"), s.get("lon")
        dlat, dlon = d.get("lat"), d.get("lon")
        if None in (slat, slon, dlat, dlon):
            return None

        rid = f"PUJ_{idx:03d}"
        parts = name.split(" - ", 1)
        bname = parts[0].strip()
        aname = parts[-1].strip()

        return {
            "route_id":        rid,
            "route_transit":   name,
            "route_long_name": name,
            "route_type":      3,
            "route_color":     "#e67e22",
            "agency_id":       "LTFRB",
            "start":       {"lat": float(slat), "lon": float(slon), "name": bname},
            "destination": {"lat": float(dlat), "lon": float(dlon), "name": aname},
            "stops": [
                {"stop_id": f"{rid}_S", "name": bname,
                 "lat": float(slat), "lon": float(slon), "seq": 0},
                {"stop_id": f"{rid}_D", "name": aname,
                 "lat": float(dlat), "lon": float(dlon), "seq": 1},
            ],
        }

    routes = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        built = list(ex.map(build, enumerate(raw_routes)))

    for r in built:
        if r:
            routes[r["route_id"]] = r
            _JEEPNEY_PUJ.append(r["route_id"])

    _JEEPNEY_ROUTES = routes


# ── Canonical jeepney polyline cache ─────────────────────────────────────────




def _build_jeepney_spatial():
    """
    Build _JEEPNEY_SPATIAL grid index.
    Each route contributes cells for its start, destination, and
    _JEEPNEY_SAMPLES linearly-interpolated points between them.
    """
    fn = "_build_jeepney_spatial"
    t_start = time.time()
    print(f"[DEBUG][{fn}] ── START ────────────────────────────────────────────────")
    print(f"[DEBUG][{fn}] routes={len(_JEEPNEY_ROUTES)}  samples_per_route={_JEEPNEY_SAMPLES}")

    _JEEPNEY_SPATIAL.clear()

    def index_one_route(rid):
        route = _JEEPNEY_ROUTES[rid]
        s  = route['start']
        d  = route['destination']
        sl, sn = s['lat'], s['lon']
        dl, dn = d['lat'], d['lon']

        cells = [
            ((int(sl / _JEEPNEY_CELL), int(sn / _JEEPNEY_CELL)), (rid, 'start', sl, sn)),
            ((int(dl / _JEEPNEY_CELL), int(dn / _JEEPNEY_CELL)), (rid, 'dest',  dl, dn)),
        ]
        for i in range(1, _JEEPNEY_SAMPLES + 1):
            t  = i / (_JEEPNEY_SAMPLES + 1)
            ml = sl + t * (dl - sl)
            mn = sn + t * (dn - sn)
            cells.append(((int(ml / _JEEPNEY_CELL), int(mn / _JEEPNEY_CELL)),
                           (rid, f'mid_{i}', ml, mn)))
        return cells

    workers = min(32, max(1, len(_JEEPNEY_ROUTES)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        all_cell_lists = list(ex.map(index_one_route, list(_JEEPNEY_ROUTES.keys())))

    total_entries = 0
    for cell_list in all_cell_lists:
        for cell, entry in cell_list:
            _JEEPNEY_SPATIAL[cell].append(entry)
            total_entries += 1

    print(f"[DEBUG][{fn}] cells={len(_JEEPNEY_SPATIAL)}  entries={total_entries}  "
          f"elapsed={time.time()-t_start:.3f}s")
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

def _prefilter_routes_by_spatial(orig_lat, orig_lon, dest_lat, dest_lon, cell_radius=1):
    fn = "_prefilter_routes_by_spatial"
    t0 = time.time()
    if not _JEEPNEY_SPATIAL:
        _dbg(fn, "Spatial index empty; returning all routes")
        return set(_JEEPNEY_ROUTES.keys())

    def cell_for(lat, lon):
        return int(lat / _JEEPNEY_CELL), int(lon / _JEEPNEY_CELL)

    ocell = cell_for(orig_lat, orig_lon)
    dcell = cell_for(dest_lat, dest_lon)

    candidates = set()
    for base in (ocell, dcell):
        for di in range(-cell_radius, cell_radius + 1):
            for dj in range(-cell_radius, cell_radius + 1):
                c = (base[0] + di, base[1] + dj)
                entries = _JEEPNEY_SPATIAL.get(c)
                if entries:
                    for entry in entries:
                        candidates.add(entry[0])
    _dbg(fn, f"Prefiltered routes={len(candidates)} from cells {ocell} & {dcell} elapsed={time.time()-t0:.3f}s")
    if not candidates:
        _dbg(fn, "Prefilter empty — falling back to all routes")
        return set(_JEEPNEY_ROUTES.keys())
    return candidates

def _find_jeepney_candidates(orig_lat, orig_lon, dest_lat, dest_lon, topk=1):
    fn = "_find_jeepney_candidates"
    t_start = time.time()
    _dbg(fn, f"CALL origin=({orig_lat:.6f},{orig_lon:.6f}) dest=({dest_lat:.6f},{dest_lon:.6f})")

    if not _JEEPNEY_READY:
        _dbg(fn, "Jeepney DB not ready → loading")
        _load_jeepney()

    candidate_rids = list(_prefilter_routes_by_spatial(orig_lat, orig_lon, dest_lat, dest_lon, cell_radius=2))
    _dbg(fn, f"Prefiltered candidate count={len(candidate_rids)} (topk={topk})")

    if not candidate_rids:
        _dbg(fn, "No candidate routes after prefilter")
        return [], []

    def _proj_worker(rid):
        try:
            route = _JEEPNEY_ROUTES[rid]
            sl, sn = route['start']['lat'], route['start']['lon']
            dl, dn = route['destination']['lat'], route['destination']['lon']

            t_b, bplat, bplon, bdist = _proj_point_on_segment(orig_lat, orig_lon, sl, sn, dl, dn)
            t_a, aplat, aplon, adist = _proj_point_on_segment(dest_lat, dest_lon, sl, sn, dl, dn)

            ok_board  = bdist is not None and bdist  <= _JBOARD_LIM
            ok_alight = adist is not None and adist  <= _JALIGHT_LIM
            ok_order  = t_a >= t_b + 1e-6

            # Score = total walking only.
            # Weight board-walk 2x: getting to the route is the user's first obstacle.
            # No progress penalty — it was backwards (penalising mid-route boards,
            # rewarding terminal boards even when the terminal is far away).
            score = bdist * 2.0 + adist

            _dbg(fn, f"{rid} tb={t_b:.4f} ta={t_a:.4f} bdist={int(bdist)} adist={int(adist)} ok={ok_board and ok_alight and ok_order} score={score:.1f}")

            if ok_board and ok_alight and ok_order:
                return (score, rid, bplat, bplon, aplat, aplon)
            return None
        except Exception as e:
            _dbg(fn, f"WORKER_EXCEPTION rid={rid} err={e}")
            return None

    workers = min(32, max(1, len(candidate_rids)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(_proj_worker, candidate_rids))

    direct = [r for r in results if r]
    direct.sort(key=lambda x: (x[0], x[1]))

    _dbg(fn, f"Direct candidates found={len(direct)} elapsed={time.time()-t_start:.3f}s")
    if direct:
        for i, d in enumerate(direct[:min(3, len(direct))]):
            _dbg(fn, f"TOP#{i+1} rid={d[1]} score={d[0]:.1f} board=({d[2]:.5f},{d[3]:.5f}) alight=({d[4]:.5f},{d[5]:.5f})")

    return direct[:topk], []

# ════════════════════════════════════════════════════════════════════════════════
#  JEEPNEY LEG BUILDER  (OSM / OSRM called HERE — after candidate selection)
# ════════════════════════════════════════════════════════════════════════════════

def _build_jeepney_shape_once(rid):
    """
    Fetch and cache the road-following polyline for a jeepney route.
    Calls OSRM once (start → destination) and caches the result.
    Falls back to a straight-line approximation if OSRM is unavailable.
    """
    if rid in _JEEPNEY_SHAPE_CACHE:
        return _JEEPNEY_SHAPE_CACHE[rid]['poly']

    route = _JEEPNEY_ROUTES.get(rid)
    if not route:
        return None

    s = route['start']
    d = route['destination']
    url = (f"https://router.project-osrm.org/route/v1/driving/"
           f"{s['lon']},{s['lat']};{d['lon']},{d['lat']}"
           f"?overview=full&geometries=geojson")
    try:
        r = requests.get(url, timeout=20, headers=_OSRM_HDRS)
        r.raise_for_status()
        js = r.json()
        if js.get('code') == 'Ok' and js.get('routes'):
            coords = [[pt[1], pt[0]] for pt in js['routes'][0]['geometry']['coordinates']]
            dist   = js['routes'][0]['distance']
            _JEEPNEY_SHAPE_CACHE[rid] = {'poly': coords, 'dist': dist}
            _dbg("_build_jeepney_shape_once",
                 f"OSRM OK rid={rid} pts={len(coords)} dist={int(dist)}")
            return coords
    except Exception as e:
        _dbg("_build_jeepney_shape_once", f"OSRM failed rid={rid}: {e}")

    # Fallback: straight-line approximation (40 samples)
    sl, sn, dl, dn = s['lat'], s['lon'], d['lat'], d['lon']
    fallback = [[sl + i/40*(dl-sl), sn + i/40*(dn-sn)] for i in range(41)]
    _JEEPNEY_SHAPE_CACHE[rid] = {'poly': fallback, 'dist': _poly_dist(fallback)}
    return fallback

def _build_jeepney_leg(rid, orig_lat, orig_lon, dest_lat, dest_lon):
    """
    Build a single jeepney leg, snipping the OSRM road polyline precisely
    at the closest segment-projected points to orig and dest.
    """
    route = _JEEPNEY_ROUTES.get(rid)
    if not route:
        return None

    poly = _build_jeepney_shape_once(rid)
    if not poly or len(poly) < 2:
        return None

    # --- Snap user points to nearest segment of the shape poly ---
    def snap_to_poly(lat, lon):
        best_t, best_idx, best_lat, best_lon, best_d = 0.0, 0, poly[0][0], poly[0][1], float('inf')
        for i in range(len(poly) - 1):
            t, plat, plon, d = _proj_point_on_segment(
                lat, lon,
                poly[i][0], poly[i][1],
                poly[i+1][0], poly[i+1][1]
            )
            if d < best_d:
                best_d = d
                best_t = t
                best_idx = i if t < 1.0 else i + 1
                best_lat, best_lon = plat, plon
        # If the projection lands exactly between two vertices, insert the proj pt
        return best_idx, best_lat, best_lon

    i_board,  blat, blon = snap_to_poly(orig_lat, orig_lon)
    i_alight, alat, alon = snap_to_poly(dest_lat, dest_lon)

    if i_board == i_alight and abs(blat - alat) < 1e-6 and abs(blon - alon) < 1e-6:
        return None

    # Build ridden segment: snip poly and prepend/append exact snap points
    if i_board <= i_alight:
        ridden = [[blat, blon]] + poly[i_board + 1:i_alight + 1]
        if [alat, alon] not in ridden:
            ridden.append([alat, alon])
    else:
        # Route runs in reverse on this poly — reverse so ride goes forward
        ridden = [[alat, alon]] + poly[i_alight + 1:i_board + 1]
        if [blat, blon] not in ridden:
            ridden.append([blat, blon])
        ridden = list(reversed(ridden))

    if len(ridden) < 2:
        return None

    dist_m = _poly_dist(ridden)
    fare   = calc_sakay_fare(rid, dist_m)

    parts = route['route_transit'].split(' - ', 1)
    bname = parts[0].strip()
    aname = parts[-1].strip()

    return {
        'route_id':    rid,
        'route_name':  route['route_transit'],
        'rtype':       'PUJ',
        'board':       {'name': bname, 'lat': ridden[0][0],  'lon': ridden[0][1]},
        'alight':      {'name': aname, 'lat': ridden[-1][0], 'lon': ridden[-1][1]},
        'ridden_poly': ridden,
        'ridden_stops': [
            {'name': bname, 'lat': ridden[0][0],  'lon': ridden[0][1]},
            {'name': aname, 'lat': ridden[-1][0], 'lon': ridden[-1][1]},
        ],
        'dist_m':   dist_m,
        'fare':     fare,
        'color':    '#e67e22',
        'seg_type': 'jeepney',
    }
    
# ════════════════════════════════════════════════════════════════════════════════
#  JEEPNEY JOURNEY PLANNER
# ════════════════════════════════════════════════════════════════════════════════

_JEEPNEY_GRAPH = defaultdict(list)  # rid -> [(other_rid, transfer_dist_m)]

def _build_jeepney_graph(max_transfer_dist=600):
    _JEEPNEY_GRAPH.clear()

    rids = list(_JEEPNEY_ROUTES.keys())
    shapes = {}

    # Ensure all shapes exist
    for rid in rids:
        poly = _build_jeepney_shape_once(rid)
        if poly:
            shapes[rid] = poly

    for i, rid1 in enumerate(rids):
        p1 = shapes.get(rid1)
        if not p1:
            continue

        for rid2 in rids[i+1:]:
            p2 = shapes.get(rid2)
            if not p2:
                continue

            # Check minimum distance between polylines
            min_d = float("inf")
            for a in p1[::10]:
                for b in p2[::10]:
                    d = _hav(a[0], a[1], b[0], b[1])
                    if d < min_d:
                        min_d = d
                    if min_d <= max_transfer_dist:
                        break
                if min_d <= max_transfer_dist:
                    break

            if min_d <= max_transfer_dist:
                _JEEPNEY_GRAPH[rid1].append((rid2, min_d))
                _JEEPNEY_GRAPH[rid2].append((rid1, min_d))

def _snap_user_to_routes(lat, lon, max_dist=900):
    hits = []
    for rid, route in _JEEPNEY_ROUTES.items():
        poly = _build_jeepney_shape_once(rid)
        if not poly:
            continue
        idx = _closest_idx(poly, lat, lon)
        d = _hav(lat, lon, poly[idx][0], poly[idx][1])
        if d <= max_dist:
            hits.append((rid, idx, d))
    return hits

def _find_jeepney_chain(orig_lat, orig_lon, dest_lat, dest_lon, max_hops=3):
    start_hits = _snap_user_to_routes(orig_lat, orig_lon)
    end_hits   = _snap_user_to_routes(dest_lat, dest_lon)

    end_rids = {rid for rid, _, _ in end_hits}

    # BFS over jeepney graph
    from collections import deque
    q = deque()
    visited = set()

    for rid, idx, d in start_hits:
        q.append((rid, [rid]))
        visited.add(rid)

    while q:
        rid, path = q.popleft()

        if rid in end_rids:
            return path

        if len(path) >= max_hops:
            continue

        for nxt, _ in _JEEPNEY_GRAPH.get(rid, []):
            if nxt in path:
                continue  # prevent overlap / reuse
            q.append((nxt, path + [nxt]))

    return None

def _build_jeepney_chain_legs(chain, orig_lat, orig_lon, dest_lat, dest_lon):
    """
    Build legs for a multi-hop jeepney chain.
    Each leg is snipped correctly:
      - Leg 0  board: closest point on shape to user origin
      - Leg i>0 board: closest point on shape to previous leg's alight position
      - Last leg alight: closest point on shape to user destination
      - Mid-leg alight: where this route is closest to the next route's shape
    """
    legs = []

    for i, rid in enumerate(chain):
        poly = _build_jeepney_shape_once(rid)
        if not poly:
            return None

        # ── Determine board index ────────────────────────────────────────────
        if i == 0:
            board_lat, board_lon = orig_lat, orig_lon
        else:
            # Use the actual alight position of the previous leg
            prev_alight = legs[-1]['alight']
            board_lat, board_lon = prev_alight['lat'], prev_alight['lon']

        i0 = _closest_idx(poly, board_lat, board_lon)

        # ── Determine alight index ───────────────────────────────────────────
        if i == len(chain) - 1:
            alight_lat, alight_lon = dest_lat, dest_lon
        else:
            # Find where this route is closest to the next route's shape
            next_poly = _build_jeepney_shape_once(chain[i + 1])
            if not next_poly:
                return None
            # Find the pair of points (one on each poly) with minimum distance
            best_d = float('inf')
            best_i, best_j = len(poly) - 1, 0
            # Sample both polys to keep it fast
            step_a = max(1, len(poly) // 40)
            step_b = max(1, len(next_poly) // 40)
            for a_idx in range(i0, len(poly), step_a):
                for b_idx in range(0, len(next_poly), step_b):
                    d = _hav(poly[a_idx][0], poly[a_idx][1],
                             next_poly[b_idx][0], next_poly[b_idx][1])
                    if d < best_d:
                        best_d = d
                        best_i = a_idx
            alight_lat, alight_lon = poly[best_i][0], poly[best_i][1]
        i1 = _closest_idx(poly, alight_lat, alight_lon)

        # ── Snip ──────────────────────────────────────────────────────────────
        ridden = _snip_poly(poly, i0, i1)
        if len(ridden) < 2:
            return None

        route = _JEEPNEY_ROUTES[rid]
        parts = route['route_transit'].split(' - ', 1)

        legs.append({
            'route_id':    rid,
            'route_name':  route['route_transit'],
            'rtype':       'PUJ',
            'board':       {'name': parts[0], 'lat': ridden[0][0],  'lon': ridden[0][1]},
            'alight':      {'name': parts[-1], 'lat': ridden[-1][0], 'lon': ridden[-1][1]},
            'ridden_poly': ridden,
            'dist_m':      _poly_dist(ridden),
            'fare':        calc_sakay_fare(rid, _poly_dist(ridden)),
            'color':       '#e67e22',
            'seg_type':    'jeepney',
        })

    return legs

def plan_jeepney_journey(orig_lat, orig_lon, dest_lat, dest_lon, max_results=1):
    """
    Plan a jeepney journey from orig to dest.
    Always returns at most 1 route — the closest/best-scoring match.
    Priority:
      1. Direct candidate from _find_jeepney_candidates (pure geometry, fast).
      2. Fall back to BFS graph search for multi-hop transfers.
    """
    _load_jeepney()

    # ── 1. Direct single-route candidate (best geometry match) ──────────────
    direct_candidates, _ = _find_jeepney_candidates(orig_lat, orig_lon, dest_lat, dest_lon, topk=1)
    if direct_candidates:
        score, rid, bplat, bplon, aplat, aplon = direct_candidates[0]
        leg = _build_jeepney_leg(rid, bplat, bplon, aplat, aplon)
        if leg:
            return [_assemble_route([leg], orig_lat, orig_lon, dest_lat, dest_lon, 0)]

    # ── 2. BFS multi-hop graph search ────────────────────────────────────────
    _build_jeepney_graph()
    chain = _find_jeepney_chain(orig_lat, orig_lon, dest_lat, dest_lon)
    if not chain:
        return []

    legs = _build_jeepney_chain_legs(chain, orig_lat, orig_lon, dest_lat, dest_lon)
    if not legs:
        return []

    return [_assemble_route(legs, orig_lat, orig_lon, dest_lat, dest_lon, 0)]

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
        return plan_jeepney_journey(orig_lat, orig_lon, dest_lat, dest_lon, max_results=1)

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
