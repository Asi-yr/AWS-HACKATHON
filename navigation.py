import requests, time, json, math, os, concurrent.futures
from collections import defaultdict

print("[DEBUG][INIT] Loading navigation.py module...")
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
_OVERPASS =[
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]

def _overpass_query(query, max_retries=5, timeout=30):
    t_start = time.time()
    print(f"[DEBUG][_overpass_query] Starting query execution. max_retries={max_retries}, timeout={timeout}s")
    print(f"[DEBUG] [_overpass_query] Query payload length: {len(query)} characters")
    
    for attempt in range(max_retries):
        ep = _OVERPASS[attempt % len(_OVERPASS)]
        print(f"[DEBUG] [_overpass_query] Attempt {attempt+1}/{max_retries} using endpoint: {ep}")
        try:
            t_req = time.time()
            r = requests.post(ep, data=query, headers={'User-Agent':'SafeRoute/1.0'}, timeout=timeout)
            print(f"[DEBUG] [_overpass_query] Request completed in {time.time() - t_req:.4f}s with status code {r.status_code}")
            r.raise_for_status()
            res_json = r.json()
            print(f"[DEBUG] [_overpass_query] Successfully parsed JSON response. Total function time: {time.time() - t_start:.4f}s")
            return res_json
        except Exception as e:
            print(f"[DEBUG] [_overpass_query] Exception on attempt {attempt+1}: {e}")
            pass
            
        if attempt < max_retries-1:
            sleep_time = 2 * (attempt + 1)
            print(f"[DEBUG] [_overpass_query] Sleeping for {sleep_time}s before retrying...")
            time.sleep(sleep_time)
            
    print(f"[DEBUG] [_overpass_query] All {max_retries} attempts failed. Returning None. Time taken: {time.time() - t_start:.4f}s")
    return None

_GEOCODE_CACHE = {}
_OSRM_DIST_CACHE = {}

def geocode_location(address):
    t_start = time.time()
    print(f"[DEBUG] [geocode_location] Initiating geocode for address: '{address}'")
    
    if address in _GEOCODE_CACHE:
        print(f"[DEBUG] [geocode_location] Cache hit for '{address}'. Returning cached result: {_GEOCODE_CACHE[address]}")
        return _GEOCODE_CACHE[address]
        
    clean = address.lower().strip()
    print(f"[DEBUG] [geocode_location] Cleaned address string: '{clean}'")
    
    for key, coords in _KNOWN.items():
        if key in clean:
            r = (coords[1], coords[0])
            _GEOCODE_CACHE[address] = r
            print(f"[DEBUG] [geocode_location] Matched local _KNOWN atlas for '{key}'. Result: {r}. Time: {time.time() - t_start:.4f}s")
            return r
            
    if "," in address:
        print("[DEBUG] [geocode_location] Address contains a comma. Attempting coordinate split parsing...")
        try:
            parts = [x.strip() for x in address.split(',')]
            lat, lon = float(parts[0]), float(parts[1])
            r = (lon, lat) if lon > 100 else (lat, lon)
            _GEOCODE_CACHE[address] = r
            print(f"[DEBUG] [geocode_location] Parsed raw coordinates from string. Result: {r}. Time: {time.time() - t_start:.4f}s")
            return r
        except (ValueError, TypeError) as e:
            print(f"[DEBUG] [geocode_location] Failed to parse as coordinates: {e}")
            pass
            
    print("[DEBUG] [geocode_location] Sleeping 1.1s to respect Nominatim rate limits...")
    time.sleep(1.1)
    
    url = (f"https://nominatim.openstreetmap.org/search"
           f"?q={requests.utils.quote(address)}&format=json&limit=1&countrycodes=ph")
    print(f"[DEBUG] [geocode_location] Sending request to Nominatim API: {url}")
    
    try:
        t_req = time.time()
        r = requests.get(url, headers={'User-Agent':'SafeRouteAI/1.0'}, timeout=5)
        print(f"[DEBUG][geocode_location] Nominatim response received in {time.time() - t_req:.4f}s. Status code: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            if data:
                result = float(data[0]['lon']), float(data[0]['lat'])
                _GEOCODE_CACHE[address] = result
                print(f"[DEBUG] [geocode_location] Nominatim parsing success. Result: {result}. Total time: {time.time() - t_start:.4f}s")
                return result
            else:
                print("[DEBUG] [geocode_location] Nominatim returned an empty array (No results found).")
    except Exception as e:
        print(f"[DEBUG] [geocode_location] Exception during Nominatim request: {e}")
        pass
        
    print(f"[DEBUG] [geocode_location] Geocoding failed entirely. Returning (None, None). Time taken: {time.time() - t_start:.4f}s")
    _GEOCODE_CACHE[address] = (None, None)
    return None, None

# ── Geometry ─────────────────────────────────────────────────────────────────
# Note: Intentionally avoiding deep prints inside _hav and _dsq to prevent memory flooding.
def _hav(la1,lo1,la2,lo2):
    R=6_371_000; f1=math.radians(la1); f2=math.radians(la2)
    df=math.radians(la2-la1); dl=math.radians(lo2-lo1)
    a=math.sin(df/2)**2+math.cos(f1)*math.cos(f2)*math.sin(dl/2)**2
    return R*2*math.atan2(math.sqrt(a),math.sqrt(1-a))

_haversine_m = _hav   # public alias

def _dsq(la1,lo1,la2,lo2): return (la1-la2)**2+(lo1-lo2)**2

def _poly_dist(poly):
    # print(f"[DEBUG] [_poly_dist] Calculating distance for polyline with {len(poly)} points.")
    if len(poly) < 2: return 0.0
    return sum(_hav(poly[i][0],poly[i][1],poly[i+1][0],poly[i+1][1]) for i in range(len(poly)-1))

def _closest_idx(line,lat,lon):
    if not line: return 0
    return min(range(len(line)),key=lambda i:_dsq(line[i][0],line[i][1],lat,lon))

def _chain_one(segs,start,used):
    t_start = time.time()
    # print(f"[DEBUG] [_chain_one] Starting chain from segment index {start}")
    ep={}
    for i,s in enumerate(segs):
        ep[tuple(s[0])]=('start',i); ep[tuple(s[-1])]=('end',i)
    path=list(segs[start]); used.add(start)
    
    loops = 0
    while True:
        loops += 1
        grew=False
        m=ep.get(tuple(path[-1]))
        if m and m[1] not in used:
            side,idx=m; s=segs[idx]
            path.extend(s[1:] if side=='start' else list(reversed(s[:-1]))); used.add(idx); grew=True
        if not grew:
            m=ep.get(tuple(path[0]))
            if m and m[1] not in used:
                side,idx=m; s=segs[idx]
                path=(s[:-1]+path) if side=='end' else (list(reversed(s[1:]))+path)
                used.add(idx); grew=True
        if not grew: break
        
    # print(f"[DEBUG] [_chain_one] Chain complete. Path size: {len(path)} points. Loops run: {loops}. Time: {time.time() - t_start:.4f}s")
    return path

def _chain_all(segs):
    t_start = time.time()
    print(f"[DEBUG] [_chain_all] Attempting to chain {len(segs)} segments...")
    used=set(); out=[]
    for i in range(len(segs)):
        if i not in used:
            out.append(_chain_one(segs,i,used))
    print(f"[DEBUG][_chain_all] Reduced {len(segs)} segments to {len(out)} distinct continuous path(s) in {time.time() - t_start:.4f}s")
    return out

def _osrm_walk_dist(la1,lo1,la2,lo2,timeout=5):
    t_start = time.time()
    url=f"https://router.project-osrm.org/route/v1/foot/{lo1},{la1};{lo2},{la2}?overview=false"
    print(f"[DEBUG] [_osrm_walk_dist] Fetching walk distance from OSRM: {url}")
    try:
        t_req = time.time()
        resp=requests.get(url,timeout=timeout).json()
        print(f"[DEBUG] [_osrm_walk_dist] OSRM API responded in {time.time() - t_req:.4f}s")
        if resp.get('code')=='Ok' and resp.get('routes'):
            d=resp['routes'][0].get('distance')
            if d: 
                print(f"[DEBUG][_osrm_walk_dist] Successfully returned distance: {int(d)}m. Total time: {time.time() - t_start:.4f}s")
                return int(d)
    except Exception as e:
        print(f"[DEBUG] [_osrm_walk_dist] Exception occurred during OSRM call: {e}")
        pass
    print(f"[DEBUG] [_osrm_walk_dist] Failed to get valid walk distance. Returning None. Total time: {time.time() - t_start:.4f}s")
    return None

def _osrm_walk_dist_cached(la1,lo1,la2,lo2):
    key=(round(la1,4),round(lo1,4),round(la2,4),round(lo2,4))
    if key not in _OSRM_DIST_CACHE: 
        print(f"[DEBUG] [_osrm_walk_dist_cached] Cache MISS for key: {key}. Calling _osrm_walk_dist.")
        _OSRM_DIST_CACHE[key]=_osrm_walk_dist(la1,lo1,la2,lo2)
    else:
        # Prevent log spam on heavy loops, but track the hit
        pass
    return _OSRM_DIST_CACHE[key]

def _osm_name(s):
    k=s.lower().replace(" ","").replace("-","")
    res = {"lrt1":"Line 1","line1":"Line 1","lrt2":"Line 2","line2":"Line 2",
            "mrt3":"Line 3","mrt":"Line 3","line3":"Line 3",
            "mrt7":"Line 7","line7":"Line 7","pnr":"PNR","subway":"Metro Manila Subway"}.get(k,s)
    # print(f"[DEBUG] [_osm_name] Normalized '{s}' -> '{res}'")
    return res

# ── OSRM foot fetcher ─────────────────────────────────────────────────────────
def _fetch_osrm_foot(olon,olat,dlon,dlat):
    t_start = time.time()
    print(f"[DEBUG] [_fetch_osrm_foot] Requesting foot geometry from {olat},{olon} to {dlat},{dlon}")
    hdrs={'User-Agent':'SafeRouteAI/1.0'}
    urls =[
        f"https://routing.openstreetmap.de/routed-foot/route/v1/driving/{olon},{olat};{dlon},{dlat}?overview=full&geometries=geojson&alternatives=3",
        f"https://router.project-osrm.org/route/v1/foot/{olon},{olat};{dlon},{dlat}?overview=full&geometries=geojson&alternatives=3",
    ]
    
    for idx, url in enumerate(urls):
        print(f"[DEBUG] [_fetch_osrm_foot] Attempting URL {idx+1}/{len(urls)}: {url}")
        try:
            t_req = time.time()
            r=requests.get(url,headers=hdrs,timeout=6).json()
            print(f"[DEBUG][_fetch_osrm_foot] URL {idx+1} responded in {time.time() - t_req:.4f}s with code: {r.get('code')}")
            if r.get('code')=='Ok' and r.get('routes'): 
                print(f"[DEBUG] [_fetch_osrm_foot] Returning {len(r['routes'])} foot routes. Total time: {time.time() - t_start:.4f}s")
                return r
        except Exception as e:
            print(f"[DEBUG][_fetch_osrm_foot] URL {idx+1} failed with exception: {e}")
            pass
            
    print(f"[DEBUG] [_fetch_osrm_foot] All OSRM foot queries failed. Returning None. Time: {time.time() - t_start:.4f}s")
    return None

def _walk_seg(from_lat,from_lon,to_lat,to_lon,label):
    t_start = time.time()
    # print(f"[DEBUG] [_walk_seg] Building walk segment: '{label}' from {from_lat},{from_lon} to {to_lat},{to_lon}")
    straight=_hav(from_lat,from_lon,to_lat,to_lon)
    # print(f"[DEBUG] [_walk_seg] Straight line distance: {straight:.2f}m")
    
    if straight<5: 
        # print(f"[DEBUG] [_walk_seg] Distance < 5m. Returning empty. Time: {time.time() - t_start:.4f}s")
        return None,0,0
        
    if straight<80:
        # print(f"[DEBUG] [_walk_seg] Distance < 80m. Returning straight line. Time: {time.time() - t_start:.4f}s")
        c=[[from_lat,from_lon],[to_lat,to_lon]]
        return {'type':'walk','coords':c,'color':'#7f8c8d','label':label},straight,straight/1.2
        
    # print("[DEBUG][_walk_seg] Distance >= 80m. Attempting OSRM foot fetch...")
    r=_fetch_osrm_foot(from_lon,from_lat,to_lon,to_lat)
    if r:
        rt=r['routes'][0]
        # print(f"[DEBUG] [_walk_seg] OSRM returned path distance {rt['distance']}m vs straight line {straight:.2f}m")
        if rt['distance']<=straight*2.5 or straight<=50:
            c=[[p[1],p[0]] for p in rt['geometry']['coordinates']]
            # print(f"[DEBUG][_walk_seg] Using OSRM polyline. Time: {time.time() - t_start:.4f}s")
            return {'type':'walk','coords':c,'color':'#7f8c8d','label':label},rt['distance'],rt['duration']
            
    # print(f"[DEBUG] [_walk_seg] OSRM failed or path too distorted. Falling back to straight line. Time: {time.time() - t_start:.4f}s")
    c=[[from_lat,from_lon],[to_lat,to_lon]]
    return {'type':'walk','coords':c,'color':'#7f8c8d','label':label},straight,straight/1.2

# ════════════════════════════════════════════════════════════════════════════════
#  SAKAY LOADER + SPATIAL INDEX
# ════════════════════════════════════════════════════════════════════════════════
_SAKAY_READY  = False
_SAKAY_ROUTES = {}
_SAKAY_SHAPES = {}
_SAKAY_PUJ    =[]   # jeepney
_SAKAY_PUB    = []   # bus
_SAKAY_RAIL   =[]   # rail

# Spatial index: (lat_cell, lon_cell) ->[(rid, stop_idx, lat, lon)]
_STOP_SPATIAL = defaultdict(list)
_SPATIAL_CELL = 0.008   # ~890m per cell

def _find_file(*names):
    t_start = time.time()
    base=os.path.dirname(os.path.abspath(__file__)); cwd=os.getcwd()
    print(f"[DEBUG] [_find_file] Searching for files: {names} in dirs: ['map_transit', '{base}', '{cwd}']")
    for name in names:
        for d in[os.path.join(base,'map_transit'),base,os.path.join(cwd,'map_transit'),cwd]:
            p=os.path.join(d,name)
            if os.path.exists(p): 
                print(f"[DEBUG][_find_file] Found file at: {p}. Time: {time.time() - t_start:.4f}s")
                return p
    print(f"[DEBUG] [_find_file] File not found. Time: {time.time() - t_start:.4f}s")
    return None

def _load_sakay(user_lat=None, user_lon=None, max_dist_m=5000):
    func_name = "_load_sakay"
    global _SAKAY_READY
    t_start = time.time()
    print(f"[DEBUG] [{func_name}] START. Current _SAKAY_READY={_SAKAY_READY}")

    if _SAKAY_READY:
        print(f"[DEBUG] [{func_name}] Already initialized. Duration={time.time()-t_start:.4f}s")
        return

    # --- Step 1: Locate files ---
    rp = _find_file('sakay_all_routes.json')
    sp = _find_file('sakay_all_shapes.geojson')
    print(f"[DEBUG] [{func_name}] File discovery complete. Routes={bool(rp)}, Shapes={bool(sp)}")

    # --- Step 2: Define worker functions ---
    def parse_routes_worker(path):
        t0 = time.time()
        print(f"[DEBUG] [{func_name}][parse_routes_worker] Parsing {path}...")
        _parse_routes(path)
        print(f"[DEBUG] [{func_name}][parse_routes_worker] Done in {time.time()-t0:.4f}s")

    def parse_shapes_worker(path):
        t0 = time.time()
        print(f"[DEBUG] [{func_name}][parse_shapes_worker] Parsing {path}...")
        _parse_shapes(path)
        print(f"[DEBUG] [{func_name}][parse_shapes_worker] Done in {time.time()-t0:.4f}s")

    # --- Step 3: Run parsing concurrently ---
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = []
        if rp: futures.append(executor.submit(parse_routes_worker, rp))
        if sp: futures.append(executor.submit(parse_shapes_worker, sp))
        for f in concurrent.futures.as_completed(futures):
            try:
                f.result()
            except Exception as e:
                print(f"[DEBUG] [{func_name}] Worker error: {e}")

    # --- Step 4: Build spatial index ---
    t_spatial = time.time()
    print(f"[DEBUG] [{func_name}] Building spatial index...")
    _build_spatial()
    print(f"[DEBUG] [{func_name}] Spatial index built in {time.time()-t_spatial:.4f}s")

    # --- Step 5: Filter closest stops/routes ---
    if user_lat is not None and user_lon is not None:
        print(f"[DEBUG] [{func_name}] Filtering routes by proximity to user ({user_lat},{user_lon})...")
        nearby_routes = {}
        for rid, route in _SAKAY_ROUTES.items():
            stops = route['stops']
            min_dist = min(
                _hav(user_lat, user_lon, s['lat'], s['lon']) for s in stops
            )
            if min_dist <= max_dist_m:
                nearby_routes[rid] = route
                print(f"[DEBUG] [{func_name}] Route {rid} kept. Closest stop={min_dist:.2f}m")
            else:
                print(f"[DEBUG] [{func_name}] Route {rid} discarded. Closest stop={min_dist:.2f}m")
        _SAKAY_ROUTES.clear()
        _SAKAY_ROUTES.update(nearby_routes)
        print(f"[DEBUG] [{func_name}] Proximity filter complete. Remaining routes={len(_SAKAY_ROUTES)}")

    # --- Step 6: Finalize ---
    _SAKAY_READY = True
    n_stops = sum(len(v) for v in _STOP_SPATIAL.values())
    print(f"[DEBUG] [{func_name}] READY: {len(_SAKAY_ROUTES)} routes "
          f"({len(_SAKAY_PUJ)} PUJ · {len(_SAKAY_PUB)} PUB · {len(_SAKAY_RAIL)} rail) · "
          f"{len(_SAKAY_SHAPES)} shapes · {n_stops} indexed stops")
    print(f"[DEBUG] [{func_name}] TOTAL INIT TIME={time.time()-t_start:.4f}s")

def _parse_routes(path, user_lat=None, user_lon=None, max_dist_m=600):
    func_name = "_parse_routes"
    t_start = time.time()
    print(f"[DEBUG] [{func_name}] START. Parsing routes from {path}...")

    raw_meta = {}
    stops_map = defaultdict(dict)
    line_count = 0

    # --- Step 1: Read file line by line ---
    with open(path, encoding='utf-8') as f:
        for raw in f:
            line_count += 1
            raw = raw.strip()
            if not raw: continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                print(f"[DEBUG] [{func_name}] JSON decode error at line {line_count}")
                continue

            rid = str(rec.get('route_id')).strip()
            sid = str(rec.get('stop_id')).strip()
            slat, slon = rec.get('stop_lat'), rec.get('stop_lon')
            seq = rec.get('stop_sequence', 9999)

            if not rid or not sid or slat is None or slon is None:
                continue

            # --- Step 2: Build metadata ---
            if rid not in raw_meta:
                raw_meta[rid] = {
                    'route_id': rid,
                    'route_long_name': rec.get('route_long_name') or rid,
                    'route_desc': rec.get('route_desc') or '',
                    'route_type': rec.get('route_type', 3),
                    'route_color': rec.get('route_color'),
                    'shape_id': (str(rec['shape_id']).strip() if rec.get('shape_id') else None),
                    'agency_id': rec.get('agency_id', 'LTFRB')
                }

            # --- Step 3: Keep earliest sequence per stop ---
            entry = stops_map[rid].get(sid)
            if entry is None or seq < entry['seq']:
                stops_map[rid][sid] = {
                    'stop_id': sid,
                    'name': rec.get('stop_name') or 'Stop',
                    'lat': float(slat),
                    'lon': float(slon),
                    'seq': seq
                }

    print(f"[DEBUG] [{func_name}] File read complete. Lines={line_count}. Generating valid sequences...")

    # --- Step 4: Build valid routes with OSM proximity filtering ---
    valid_routes = 0
    for rid, sd in stops_map.items():
        stops = sorted(sd.values(), key=lambda s: s['seq'])
        stops = [s for s in stops if s['lat'] and s['lon']]
        if len(stops) < 2:
            continue

        # --- Step 5: OSM nearest point check ---
        if user_lat is not None and user_lon is not None:
            try:
                # Query OSM nearest road point for the first stop
                stop = stops[0]
                url = f"https://router.project-osrm.org/nearest/v1/driving/{stop['lon']},{stop['lat']}?number=1"
                t_osm = time.time()
                r = requests.get(url, timeout=5, headers={'User-Agent': 'SafeRouteAI'}).json()
                print(f"[DEBUG] [{func_name}] OSM nearest query for {rid} responded in {time.time()-t_osm:.4f}s")

                if r.get('code') == 'Ok' and r.get('waypoints'):
                    nearest = r['waypoints'][0]['location']
                    nlon, nlat = nearest
                    dist = _hav(user_lat, user_lon, nlat, nlon)
                    if dist > max_dist_m:
                        print(f"[DEBUG] [{func_name}] Route {rid} discarded. Nearest OSM point={dist:.2f}m away")
                        continue
                    else:
                        print(f"[DEBUG] [{func_name}] Route {rid} kept. Nearest OSM point={dist:.2f}m away")
                else:
                    print(f"[DEBUG] [{func_name}] Route {rid} OSM nearest query failed. Keeping by default.")
            except Exception as e:
                print(f"[DEBUG] [{func_name}] OSM nearest query error for {rid}: {e}. Keeping by default.")

        valid_routes += 1
        meta = raw_meta.get(rid, {})
        _SAKAY_ROUTES[rid] = {**meta, 'stops': stops}

        upper = rid.upper()
        rtype = meta.get('route_type', 3)
        if rtype == 2 or upper.startswith('ROUTE_'):
            _SAKAY_RAIL.append(rid)
        elif 'PUJ' in upper:
            _SAKAY_PUJ.append(rid)
        else:
            _SAKAY_PUB.append(rid)

    print(f"[DEBUG] [{func_name}] Loaded {valid_routes} valid routes in {time.time()-t_start:.4f}s")

def _parse_shapes(path, user_lat=None, user_lon=None, max_dist_m=600):
    func_name = "_parse_shapes"
    t_start = time.time()
    print(f"[DEBUG] [{func_name}] START. Parsing shapes from {path}...")

    try:
        with open(path, encoding='utf-8') as f:
            t_load = time.time()
            geo = json.load(f)
            print(f"[DEBUG] [{func_name}] File loaded into memory in {time.time()-t_load:.4f}s")

        features = geo.get('features', [])
        print(f"[DEBUG] [{func_name}] Processing {len(features)} features...")
        count = 0

        for feat in features:
            sid = feat.get('properties', {}).get('shape_id')
            geom_type = feat.get('geometry', {}).get('type')
            coords = feat.get('geometry', {}).get('coordinates', [])

            if sid is None or not coords:
                continue

            # --- Step 1: Normalize coordinates ---
            segments = []
            if geom_type == 'MultiLineString' or (isinstance(coords, list) and isinstance(coords[0], list) and isinstance(coords[0][0], list)):
                for line in coords:
                    segments.append([[c[1], c[0]] for c in line if len(c) >= 2])
            else:
                segments.append([[c[1], c[0]] for c in coords if len(c) >= 2])

            segments = [s for s in segments if s]
            if not segments:
                continue

            # --- Step 2: Chain segments ---
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

            # --- Step 3: Proximity filter ---
            if user_lat is not None and user_lon is not None:
                min_dist = min(_hav(user_lat, user_lon, pt[0], pt[1]) for pt in final_poly)
                if min_dist > max_dist_m:
                    print(f"[DEBUG] [{func_name}] Shape {sid} discarded. Closest point={min_dist:.2f}m")
                    continue
                else:
                    print(f"[DEBUG] [{func_name}] Shape {sid} kept. Closest point={min_dist:.2f}m")

            _SAKAY_SHAPES[str(sid).strip()] = final_poly
            count += 1

        print(f"[DEBUG] [{func_name}] Successfully extracted {count} shapes. Duration={time.time()-t_start:.4f}s")

    except Exception as e:
        print(f"[DEBUG] [{func_name}] ERROR: {e}")

def _build_spatial(user_lat=None, user_lon=None, max_dist_m=5000):
    func_name = "_build_spatial"
    t_start = time.time()
    print(f"[DEBUG] [{func_name}] START. Iterating {len(_SAKAY_ROUTES)} routes to build spatial grid...")

    # Reset spatial index
    _STOP_SPATIAL.clear()

    def process_route(rid, route):
        t0 = time.time()
        local_cells = defaultdict(list)
        stops = route.get('stops', [])
        print(f"[DEBUG] [{func_name}][process_route] Route={rid}, Stops={len(stops)}")

        for idx, stop in enumerate(stops):
            cell = (int(stop['lat']/_SPATIAL_CELL), int(stop['lon']/_SPATIAL_CELL))
            local_cells[cell].append((rid, idx, stop['lat'], stop['lon']))
        print(f"[DEBUG] [{func_name}][process_route] Route={rid} processed in {time.time()-t0:.4f}s. Cells={len(local_cells)}")
        return local_cells

    # --- Step 1: Parallel route processing ---
    t_parallel = time.time()
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {executor.submit(process_route, rid, route): rid for rid, route in _SAKAY_ROUTES.items()}
        for future in concurrent.futures.as_completed(futures):
            rid = futures[future]
            try:
                local_cells = future.result()
                for cell, entries in local_cells.items():
                    _STOP_SPATIAL[cell].extend(entries)
            except Exception as e:
                print(f"[DEBUG] [{func_name}] ERROR processing route {rid}: {e}")
    print(f"[DEBUG] [{func_name}] Parallel route processing complete in {time.time()-t_parallel:.4f}s")

    # --- Step 2: Grid summary ---
    grid_count = len(_STOP_SPATIAL)
    total_stops = sum(len(v) for v in _STOP_SPATIAL.values())
    print(f"[DEBUG] [{func_name}] Spatial grid built. Cells={grid_count}, Stops={total_stops}")

    # --- Step 3: Optional proximity filtering ---
    if user_lat is not None and user_lon is not None:
        t_filter = time.time()
        print(f"[DEBUG] [{func_name}] Filtering stops by proximity to user ({user_lat},{user_lon})...")
        nearby_count = 0
        for cell, entries in _STOP_SPATIAL.items():
            for rid, idx, lat, lon in entries:
                dist = _hav(user_lat, user_lon, lat, lon)
                if dist <= max_dist_m:
                    nearby_count += 1
                    print(f"[DEBUG] [{func_name}] Stop {rid}[{idx}] at ({lat},{lon}) is {dist:.2f}m away -> KEPT")
                else:
                    print(f"[DEBUG] [{func_name}] Stop {rid}[{idx}] at ({lat},{lon}) is {dist:.2f}m away -> TOO FAR")
        print(f"[DEBUG] [{func_name}] Proximity filter complete. Nearby stops={nearby_count}. Duration={time.time()-t_filter:.4f}s")

    print(f"[DEBUG] [{func_name}] TOTAL duration={time.time()-t_start:.4f}s")

def _nearby_stops(lat,lon,radius_m=450):
    t_start = time.time()
    # print(f"[DEBUG] [_nearby_stops] Searching stops around {lat},{lon} within {radius_m}m...")
    cr=math.ceil(radius_m/(_SPATIAL_CELL*111_000))+1
    cx=int(lat/_SPATIAL_CELL); cy=int(lon/_SPATIAL_CELL)
    out=[]
    cells_checked = 0
    stops_checked = 0
    for dx in range(-cr,cr+1):
        for dy in range(-cr,cr+1):
            cells_checked += 1
            cell_stops = _STOP_SPATIAL.get((cx+dx,cy+dy),[])
            stops_checked += len(cell_stops)
            for rid,idx,slat,slon in cell_stops:
                d=_hav(lat,lon,slat,slon)
                if d<=radius_m: out.append((rid,idx,slat,slon,d))
                
    out.sort(key=lambda x:x[4])
    # print(f"[DEBUG] [_nearby_stops] Checked {cells_checked} cells, {stops_checked} stops. Found {len(out)} matches. Time: {time.time() - t_start:.4f}s")
    return out

# ── Fare ────────────────────────────────────────────────────────────────────
def calc_sakay_fare(route_id,distance_m):
    # Extremely quick, avoiding logs to prevent spam, but noting entry
    km=max(0.0,distance_m/1_000.0); upper=route_id.upper()
    if 'PUJ' in upper: base,bkm,rate,mode=13.00,4.0,1.80,'Jeepney'
    elif 'PUB' in upper: base,bkm,rate,mode=15.00,5.0,2.20,'Bus'
    elif 'ROUTE_' in upper or upper.startswith('ROUTE'):
        for lim,f in[(2,13),(4,16),(6,19),(8,22),(10,25)]:
            if km<=lim: return {'amount':float(f),'currency':'PHP','label':f'PHP {f:.2f}','mode':'Rail'}
        return {'amount':28.0,'currency':'PHP','label':'PHP 28.00','mode':'Rail'}
    else: base,bkm,rate,mode=15.00,5.0,2.20,'Bus'
    fare=base+max(0.0,km-bkm)*rate
    return {'amount':round(fare,2),'currency':'PHP','label':f'PHP {fare:.2f}','mode':mode}

# ── Route geometry ────────────────────────────────────────────────────────────
def _route_poly(route_id):
    t_start = time.time()
    # print(f"[DEBUG] [_route_poly] Extracting geometry for route_id: {route_id}")
    route=_SAKAY_ROUTES.get(route_id)
    if not route: 
        # print(f"[DEBUG] [_route_poly] Route ID {route_id} not found in _SAKAY_ROUTES.")
        return None
        
    sid=route.get('shape_id')
    if sid and str(sid) in _SAKAY_SHAPES: 
        # print(f"[DEBUG] [_route_poly] Returning pre-calculated shape for sid: {sid}. Time: {time.time() - t_start:.4f}s")
        return _SAKAY_SHAPES[str(sid)]
        
    # print(f"[DEBUG] [_route_poly] No exact shape_id found. Generating shape from {len(route['stops'])} stops. Time: {time.time() - t_start:.4f}s")
    return [[s['lat'],s['lon']] for s in route['stops']]

# ════════════════════════════════════════════════════════════════════════════════
#  MULTI-LEG SURFACE PLANNER
# ════════════════════════════════════════════════════════════════════════════════
_TYPE_COLOR ={'PUJ':'#e67e22','PUB':'#16a085','RAIL':'#27ae60'}  
_TYPE_LABEL ={'PUJ':'jeepney','PUB':'bus',    'RAIL':'train'}
_BOARD_LIM   = 800   
_ALIGHT_LIM  = 950   
_XFER_LIM    = 600   
_XFER_PEN    = 300   

def _rtype(rid):
    u=rid.upper()
    if 'PUJ' in u: return 'PUJ'
    if 'PUB' in u: return 'PUB'
    return 'RAIL'

def _build_leg(rid, board_idx, alight_idx):
    func_name = "_build_leg"
    t_start = time.time()
    print(f"[DEBUG] [{func_name}] START: Building leg for route {rid}. Board idx={board_idx}, Alight idx={alight_idx}")

    route = _SAKAY_ROUTES[rid]
    stops = route['stops']
    rtype = _rtype(rid)

    ridden = []
    dist_m = 0
    print(f"[DEBUG] [{func_name}] Route Type={rtype}. Beginning strategy pipeline...")

    # --- STRATEGY 1: OSRM Road-Snapped Routing ---
    def osrm_strategy():
        step = max(1, (alight_idx - board_idx) // 10)
        sample_indices = list(range(board_idx, alight_idx + 1, step))
        if board_idx not in sample_indices: sample_indices.insert(0, board_idx)
        if alight_idx not in sample_indices: sample_indices.append(alight_idx)

        sample_pts = [stops[i] for i in sorted(set(sample_indices))]
        print(f"[DEBUG] [{func_name}][OSRM] Generated {len(sample_pts)} sampling waypoints.")

        if len(sample_pts) < 2:
            print(f"[DEBUG] [{func_name}][OSRM] Not enough points to request routing.")
            return None, 0

        pts_str = ";".join(f"{p['lon']},{p['lat']}" for p in sample_pts)
        url = f"https://router.project-osrm.org/route/v1/driving/{pts_str}?overview=full&geometries=geojson"
        try:
            t_osrm = time.time()
            r = requests.get(url, timeout=5, headers={'User-Agent': 'SafeRouteAI'}).json()
            print(f"[DEBUG] [{func_name}][OSRM] Request duration={time.time()-t_osrm:.4f}s")
            if r.get('code') == 'Ok':
                coords = r['routes'][0]['geometry']['coordinates']
                dist = r['routes'][0]['distance']
                print(f"[DEBUG] [{func_name}][OSRM] SUCCESS. Distance={dist}m, Points={len(coords)}")
                return [[pt[1], pt[0]] for pt in coords], dist
        except Exception as e:
            print(f"[DEBUG] [{func_name}][OSRM] ERROR: {e}")
        return None, 0

    # --- STRATEGY 2: Shape File Slicing ---
    def shape_strategy():
        print(f"[DEBUG] [{func_name}][Shape] Attempting polyline slicing...")
        poly = _route_poly(rid)
        if not poly or len(poly) < 2:
            print(f"[DEBUG] [{func_name}][Shape] No valid polyline found.")
            return None, 0

        b_poly = _closest_idx(poly, stops[board_idx]['lat'], stops[board_idx]['lon'])
        a_poly = _closest_idx(poly, stops[alight_idx]['lat'], stops[alight_idx]['lon'])

        if b_poly <= a_poly:
            ridden_poly = poly[b_poly:a_poly+1]
        else:
            ridden_poly = list(reversed(poly[a_poly:b_poly+1]))

        poly_d = _poly_dist(ridden_poly)
        stops_d = _hav(stops[board_idx]['lat'], stops[board_idx]['lon'],
                       stops[alight_idx]['lat'], stops[alight_idx]['lon'])

        print(f"[DEBUG] [{func_name}][Shape] Poly distance={poly_d:.2f}m vs crow-flies={stops_d:.2f}m")
        if poly_d > stops_d * 3.0 and poly_d > 2000:
            print(f"[DEBUG] [{func_name}][Shape] Geometry flagged haywire. Discarding.")
            return None, 0
        return ridden_poly, poly_d

    # --- STRATEGY 3: Fallback Straight Line ---
    def fallback_strategy():
        print(f"[DEBUG] [{func_name}][Fallback] Using straight line between stops.")
        ridden_poly = [[s['lat'], s['lon']] for s in stops[board_idx:alight_idx+1]]
        poly_d = _poly_dist(ridden_poly)
        print(f"[DEBUG] [{func_name}][Fallback] Distance={poly_d:.2f}m")
        return ridden_poly, poly_d

    # Run strategies concurrently
    strategies = []
    if rtype in ('PUJ', 'PUB'):
        strategies.append(osrm_strategy)
    strategies.append(shape_strategy)
    strategies.append(fallback_strategy)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_strategy = {executor.submit(fn): fn.__name__ for fn in strategies}
        for future in concurrent.futures.as_completed(future_to_strategy):
            strat_name = future_to_strategy[future]
            try:
                result_poly, result_dist = future.result()
                if result_poly:
                    ridden, dist_m = result_poly, result_dist
                    print(f"[DEBUG] [{func_name}] Strategy {strat_name} succeeded. Distance={dist_m:.2f}m")
                    break
                else:
                    print(f"[DEBUG] [{func_name}] Strategy {strat_name} returned no valid route.")
            except Exception as e:
                print(f"[DEBUG] [{func_name}] Strategy {strat_name} raised exception: {e}")

    if not dist_m:
        dist_m = _poly_dist(ridden)
        print(f"[DEBUG] [{func_name}] Final dist_m recalculated={dist_m:.2f}m")

    fare = calc_sakay_fare(rid, dist_m)
    print(f"[DEBUG] [{func_name}] Fare={fare['label']}. Total duration={time.time()-t_start:.4f}s")

    return {
        'route_id': rid,
        'route_name': route.get('route_long_name', rid),
        'rtype': rtype,
        'board': stops[board_idx],
        'alight': stops[alight_idx],
        'ridden_poly': ridden,
        'ridden_stops': stops[board_idx:alight_idx+1],
        'dist_m': dist_m,
        'fare': fare,
        'color': _TYPE_COLOR.get(rtype, '#2980b9'),
        'seg_type': _TYPE_LABEL.get(rtype, 'bus')
    }

def _assemble_route(legs,orig_lat,orig_lon,dest_lat,dest_lon,route_id=0):
    t_start = time.time()
    print(f"[DEBUG] [_assemble_route] Assembling final route from {len(legs)} legs.")
    segments=[]; total_walk=0.0; total_ride=0.0; total_time=0.0; all_coords=[]
    prev_lat=orig_lat; prev_lon=orig_lon
    
    for i,leg in enumerate(legs):
        board=leg['board']; alight=leg['alight']
        lbl=(f"Walk to {board['name'][:40]}" if i==0 else f"Transfer · walk to {board['name'][:35]}")
        print(f"[DEBUG] [_assemble_route] Routing connector walk: '{lbl}'")
        
        seg_w,wd,wt=_walk_seg(prev_lat,prev_lon,board['lat'],board['lon'],lbl)
        if seg_w:
            segments.append(seg_w); total_walk+=wd; total_time+=wt; all_coords.extend(seg_w['coords'])
            
        spd={'PUJ':4.2,'PUB':5.6,'RAIL':11.1}.get(leg['rtype'],4.2)
        segments.append({'type':leg['seg_type'],'coords':leg['ridden_poly'],
                         'color':leg['color'],'label':leg['route_name'],
                         'stations':leg['ridden_stops']})
                         
        total_ride+=leg['dist_m']; total_time+=leg['dist_m']/spd
        all_coords.extend(leg['ridden_poly'])
        prev_lat=alight['lat']; prev_lon=alight['lon']
        
    print("[DEBUG] [_assemble_route] Routing final walk to destination.")
    seg_w,wd,wt=_walk_seg(prev_lat,prev_lon,dest_lat,dest_lon,"Walk to destination")
    if seg_w:
        segments.append(seg_w); total_walk+=wd; total_time+=wt; all_coords.extend(seg_w['coords'])
        
    total_min=max(1,int(total_time/60)); total_km=round((total_ride+total_walk)/1000,1)
    rtypes=[leg['rtype'] for leg in legs]
    mode_names=[]
    if any(t=='RAIL' for t in rtypes): mode_names.append('Train')
    if any(t=='PUJ'  for t in rtypes): mode_names.append('Jeepney')
    if any(t=='PUB'  for t in rtypes): mode_names.append('Bus')
    
    route_name=' + '.join(mode_names) if mode_names else 'Transit'
    fare_total=sum(leg['fare']['amount'] for leg in legs)
    score=total_walk+_XFER_PEN*(len(legs)-1)
    dom=max(set(rtypes),key=rtypes.count)
    
    print(f"[DEBUG] [_assemble_route] Route structured -> Types: {rtypes}, Dist: {total_km}km, Time: {total_min}m. Finalizing response in {time.time() - t_start:.4f}s")
    return {'id':route_id,'name':' + '.join(leg['route_name'][:30] for leg in legs),
            'route_name':route_name,'type':'transit','color':_TYPE_COLOR.get(dom,'#2980b9'),
            'time':f"~{total_min} mins",'distance':f"{total_km} km",
            'fare':f"PHP {fare_total:.2f}",'fare_amount':fare_total,
            'coords':all_coords,'segments':segments,'stations':legs[0]['ridden_stops'],
            'safety_score':72,'hazards_flagged':' · '.join(leg['route_name'][:25] for leg in legs),
            'data_source':'sakay_ltfrb','_score':score,'_legs':len(legs)}

def plan_surface_journey(allowed_modes,orig_lat,orig_lon,dest_lat,dest_lon,max_results=3):
    t_start = time.time()
    print(f"[DEBUG][plan_surface_journey] Allowed modes: {allowed_modes}. Starting journey plan...")
    _load_sakay()
    
    mode_rids={'jeepney':_SAKAY_PUJ, 'bus':_SAKAY_PUB, 'train':_SAKAY_RAIL}
    cand_rids=[]
    for m in allowed_modes: cand_rids.extend(mode_rids.get(m,[]))
    if not cand_rids: 
        print(f"[DEBUG][plan_surface_journey] No candidate routes found for allowed modes. Time: {time.time() - t_start:.4f}s")
        return[]
    allowed_set=set(cand_rids)

    print(f"[DEBUG] [plan_surface_journey] Finding destination reach routes from {len(cand_rids)} candidates...")
    t_reach = time.time()
    dest_reach={}
    for rid in cand_rids:
        stops=_SAKAY_ROUTES[rid]['stops']
        ai=min(range(len(stops)),key=lambda i:_hav(dest_lat,dest_lon,stops[i]['lat'],stops[i]['lon']))
        ad=_hav(dest_lat,dest_lon,stops[ai]['lat'],stops[ai]['lon'])
        if ad<=_ALIGHT_LIM: dest_reach[rid]=(ai,ad)
    print(f"[DEBUG][plan_surface_journey] Found {len(dest_reach)} routes reaching destination in {time.time() - t_reach:.4f}s")

    print("[DEBUG] [plan_surface_journey] Identifying first legs originating near user...")
    t_first = time.time()
    first_legs=[]
    for rid in cand_rids:
        stops=_SAKAY_ROUTES[rid]['stops']
        bi=min(range(len(stops)),key=lambda i:_hav(orig_lat,orig_lon,stops[i]['lat'],stops[i]['lon']))
        bd=_hav(orig_lat,orig_lon,stops[bi]['lat'],stops[bi]['lon'])
        if bd<=_BOARD_LIM: first_legs.append((bd,bi,rid))
    print(f"[DEBUG] [plan_surface_journey] Found {len(first_legs)} possible origin routes in {time.time() - t_first:.4f}s")

    raw=[]  
    seen_pairs={}

    print("[DEBUG] [plan_surface_journey] Step 1: Evaluating direct routes...")
    t_dir = time.time()
    for bd,bi,rid in first_legs:
        if rid not in dest_reach: continue
        ai,ad=dest_reach[rid]
        if bi>=ai: continue
        if ai-bi<2: continue
        leg=_build_leg(rid,bi,ai)
        raw.append((bd+ad,[leg]))
    print(f"[DEBUG] [plan_surface_journey] Found {len(raw)} direct options in {time.time() - t_dir:.4f}s")

    print("[DEBUG][plan_surface_journey] Step 2: Evaluating two-leg transfers...")
    t_trans = time.time()
    for bd,bi,rid1 in first_legs:
        stops1=_SAKAY_ROUTES[rid1]['stops']
        for ai1 in range(bi+2,len(stops1)):
            ts=stops1[ai1]
            for rid2,bi2,_,_,td in _nearby_stops(ts['lat'],ts['lon'],_XFER_LIM):
                if rid2==rid1 or rid2 not in allowed_set or rid2 not in dest_reach: continue
                ai2,ad=dest_reach[rid2]
                if bi2>=ai2: continue
                if ai2-bi2<2: continue
                score=bd+td+ad+_XFER_PEN
                pair=(rid1,rid2)
                if pair in seen_pairs and seen_pairs[pair]<=score: continue
                seen_pairs[pair]=score
                raw.append((score,[_build_leg(rid1,bi,ai1),_build_leg(rid2,bi2,ai2)]))
    print(f"[DEBUG] [plan_surface_journey] Finished transfer evaluation. Total combinations queued: {len(raw)}. Time: {time.time() - t_trans:.4f}s")

    if not raw: 
        print(f"[DEBUG] [plan_surface_journey] No successful legs generated. Returning empty. Time: {time.time() - t_start:.4f}s")
        return[]
        
    raw.sort(key=lambda x:x[0])

    print("[DEBUG][plan_surface_journey] Deduplicating and assembling final route JSONs...")
    t_assem = time.time()
    final=[]; used_keys=set()
    for score,legs in raw:
        key=tuple(leg['route_id'] for leg in legs)
        if key in used_keys: continue
        used_keys.add(key)
        final.append(_assemble_route(legs,orig_lat,orig_lon,dest_lat,dest_lon,len(final)))
        if len(final)>=max_results: break
        
    print(f"[DEBUG] [plan_surface_journey] Assembly complete! Returning {len(final)} compiled routes. Total function time: {time.time() - t_start:.4f}s")
    return final

# ── Public surface entry points ──────────────────────────────────────────────
def get_jeepney_route(orig_lon,orig_lat,dest_lon,dest_lat):
    print(f"[DEBUG][get_jeepney_route] Processing request. Coords: ({orig_lat},{orig_lon}) to ({dest_lat},{dest_lon})")
    routes=plan_surface_journey(['jeepney'],orig_lat,orig_lon,dest_lat,dest_lon)
    if not routes: return {"error":"No jeepney route found near your origin and destination."}
    return {"routes":routes}

def get_bus_route(orig_lon,orig_lat,dest_lon,dest_lat):
    print(f"[DEBUG] [get_bus_route] Processing request. Coords: ({orig_lat},{orig_lon}) to ({dest_lat},{dest_lon})")
    routes=plan_surface_journey(['bus'],orig_lat,orig_lon,dest_lat,dest_lon)
    if not routes: return {"error":"No bus route found near your origin and destination."}
    return {"routes":routes}

def get_jeepney_bus_route(orig_lon,orig_lat,dest_lon,dest_lat):
    print(f"[DEBUG] [get_jeepney_bus_route] Processing request. Coords: ({orig_lat},{orig_lon}) to ({dest_lat},{dest_lon})")
    routes=plan_surface_journey(['jeepney','bus'],orig_lat,orig_lon,dest_lat,dest_lon)
    if not routes: return {"error":"No jeepney or bus route found for this journey."}
    return {"routes":routes}

# ════════════════════════════════════════════════════════════════════════════════
#  TRAIN (OSM Overpass)
# ════════════════════════════════════════════════════════════════════════════════
_STOP_ROLES={'stop','stop_entry_only','stop_exit_only'}
_STATION_TAGS={'station','stop','halt','tram_stop','subway_entrance'}
_TRAIN_META={
    "lrt-1":{"color":"#27ae60","label":"LRT-1","subtitle":"Green Line","emoji":"🚇"},
    "lrt-2":{"color":"#2980b9","label":"LRT-2","subtitle":"Blue Line","emoji":"🚇"},
    "mrt-3":{"color":"#f39c12","label":"MRT-3","subtitle":"Yellow Line","emoji":"🚆"},
    "pnr":  {"color":"#8B4513","label":"PNR","subtitle":"Commuter Rail","emoji":"🚂"},
}
_LINE_CACHE={}
_TRANSFERS=[
    {"id":"L1_L2","from_line":"lrt-1","to_line":"lrt-2",
     "from_station":"Doroteo Jose","to_station":"Recto",
     "from_lat":14.5997,"from_lon":120.9842,"to_lat":14.5994,"to_lon":120.9858,
     "lat":14.6000,"lon":120.9850,"label":"Walk via CM Recto Ave (~5 min)","est_min":5},
    {"id":"L1_M3","from_line":"lrt-1","to_line":"mrt-3",
     "from_station":"EDSA","to_station":"Taft Avenue",
     "from_lat":14.5366,"from_lon":121.0003,"to_lat":14.5369,"to_lon":121.0013,
     "lat":14.5370,"lon":121.0010,"label":"Walk via enclosed walkway (~3 min)","est_min":3},
    {"id":"L2_M3","from_line":"lrt-2","to_line":"mrt-3",
     "from_station":"Araneta Center-Cubao","to_station":"Araneta Center-Cubao",
     "from_lat":14.6235,"from_lon":121.0534,"to_lat":14.6226,"to_lon":121.0528,
     "lat":14.6220,"lon":121.0520,"label":"Walk via Cubao interchange (~8 min)","est_min":8},
]

def _extract_relation(rel):
    t_start = time.time()
    # print("[DEBUG] [_extract_relation] Extracting relation members from Overpass payload...")
    stops=[]; ways=[]; seen=set()
    for m in rel.get('members',[]):
        mtype=m.get('type'); role=m.get('role','')
        if mtype=='node':
            tags=m.get('tags',{})
            is_stop=(role in _STOP_ROLES or tags.get('railway') in _STATION_TAGS
                     or tags.get('public_transport') in ('stop_position','station'))
            if role=='platform' or tags.get('public_transport')=='platform': continue
            ref=m.get('ref') or f"{m.get('lat')},{m.get('lon')}"
            if is_stop and ref not in seen:
                seen.add(ref)
                stops.append({'lat':m['lat'],'lon':m['lon'],
                               'name':(tags.get('name') or tags.get('name:en') or tags.get('ref') or 'Station')})
        elif mtype=='way' and 'geometry' in m:
            ways.append([[pt['lat'],pt['lon']] for pt in m['geometry']])
            
    # print(f"[DEBUG] [_extract_relation] Extracted {len(stops)} stops and {len(ways)} ways. Time: {time.time() - t_start:.4f}s")
    return stops,ways

def _fetch_full_line(lid):
    t_start = time.time()
    print(f"[DEBUG] [_fetch_full_line] Requesting full transit line: {lid}")
    if lid in _LINE_CACHE: 
        print(f"[DEBUG] [_fetch_full_line] Cache hit for {lid}. Time: {time.time() - t_start:.4f}s")
        return _LINE_CACHE[lid]
        
    name=_osm_name(lid)
    query=f"""[out:json][timeout:40];
            (relation["route"~"rail|light_rail|subway"]["name"~"{name}",i](14.2,120.9,14.8,121.2);
             relation["route"~"rail|light_rail|subway"]["ref"~"{name}",i](14.2,120.9,14.8,121.2););
            out geom;"""
    
    data=_overpass_query(query,max_retries=3,timeout=40)
    if not data: 
        print(f"[DEBUG] [_fetch_full_line] Overpass fetch failed. Caching None. Time: {time.time() - t_start:.4f}s")
        _LINE_CACHE[lid]=(None,None); return None,None
        
    rels=[e for e in data.get('elements',[]) if e['type']=='relation']
    if not rels: 
        print(f"[DEBUG] [_fetch_full_line] Overpass payload contained no relation elements. Time: {time.time() - t_start:.4f}s")
        _LINE_CACHE[lid]=(None,None); return None,None
        
    best=max(rels,key=lambda r:sum(1 for mm in r.get('members',[]) if mm.get('role','') in _STOP_ROLES))
    print(f"[DEBUG] [_fetch_full_line] Selected best relation with ID: {best.get('id')}")
    stops,ways=_extract_relation(best)
    
    if len(stops)<2: 
        print(f"[DEBUG] [_fetch_full_line] Relation holds insufficient stops (<2). Discarding. Time: {time.time() - t_start:.4f}s")
        _LINE_CACHE[lid]=(None,None); return None,None
        
    _LINE_CACHE[lid]=(stops,ways)
    print(f"[DEBUG] [_fetch_full_line] Line {lid} fully cached successfully. Time: {time.time() - t_start:.4f}s")
    return stops,ways

def _slice_line(all_st,all_wy,olat,olon,dlat,dlon):
    t_start = time.time()
    # print(f"[DEBUG] [_slice_line] Slicing line connecting origin({olat},{olon}) and dest({dlat},{dlon})")
    if not all_st or len(all_st)<2: return None
    
    oi=min(range(len(all_st)),key=lambda i:_dsq(all_st[i]['lat'],all_st[i]['lon'],olat,olon))
    di=min(range(len(all_st)),key=lambda i:_dsq(all_st[i]['lat'],all_st[i]['lon'],dlat,dlon))
    
    if oi==di: 
        # print(f"[DEBUG] [_slice_line] Nearest station for origin and destination is the same ({oi}). Invalid route. Time: {time.time() - t_start:.4f}s")
        return None
        
    si,ei=min(oi,di),max(oi,di); sliced=all_st[si:ei+1]; tracks=[]
    # print(f"[DEBUG] [_slice_line] Slice spans indices {si} to {ei}. Stations count: {len(sliced)}")
    
    if all_wy:
        comps=_chain_all(all_wy); main=max(comps,key=len)
        if len(main)>=2:
            ts=_closest_idx(main,sliced[0]['lat'],sliced[0]['lon'])
            te=_closest_idx(main,sliced[-1]['lat'],sliced[-1]['lon'])
            ts,te=min(ts,te),max(ts,te); trimmed=main[ts:te+1]
            if len(trimmed)>=2: tracks.append(trimmed)
            
    if not tracks: 
        # print("[DEBUG][_slice_line] Extrapolated tracks empty. Re-generating straight track segments from station nodes.")
        tracks=[[[s['lat'],s['lon']] for s in sliced]]
        
    # print(f"[DEBUG][_slice_line] Slice completed with {len(tracks[0])} polyline track points. Time: {time.time() - t_start:.4f}s")
    return {'stations':sliced,'track_segments':tracks}

def _connector_legs(from_lat,from_lon,to_lat,to_lon,label):
    t_start = time.time()
    # print(f"[DEBUG] [_connector_legs] Generating connector: '{label}'")
    dist=_hav(from_lat,from_lon,to_lat,to_lon)
    if dist<=1500:
        # print(f"[DEBUG][_connector_legs] Short distance ({dist:.1f}m). Trying walk segment.")
        seg,d,t=_walk_seg(from_lat,from_lon,to_lat,to_lon,label)
        # print(f"[DEBUG] [_connector_legs] Walk segment completed in {time.time() - t_start:.4f}s")
        return ([seg] if seg else[]),d,t
        
    # print(f"[DEBUG] [_connector_legs] Distance > 1500m ({dist:.1f}m). Searching for jeepney connector...")
    try:
        jr=get_jeepney_route(from_lon,from_lat,to_lon,to_lat)
        if "error" not in jr and jr.get("routes"):
            r=jr["routes"][0]; segs=r.get("segments",[])
            if segs:
                dtotal=sum(_poly_dist(s['coords']) for s in segs if len(s.get('coords',[]))>=2)
                try: tsec=int(r.get("time","0").replace("~","").replace(" mins",""))*60
                except Exception: tsec=max(60,int(dtotal/5))
                # print(f"[DEBUG] [_connector_legs] Found Jeepney fallback. Total time: {time.time() - t_start:.4f}s")
                return segs,dtotal,tsec
    except Exception as e: 
        # print(f"[DEBUG] [_connector_legs] Jeepney connector exception: {e}")
        pass
        
    # print(f"[DEBUG] [_connector_legs] All connectors failed. Forcing walk fallback. Time: {time.time() - t_start:.4f}s")
    seg,d,t=_walk_seg(from_lat,from_lon,to_lat,to_lon,label)
    return ([seg] if seg else[]),d,t

def _build_train_card(lid,td,meta,olat,olon,dlat,dlon,cid,segs_ov=None,name_ov=None):
    t_start = time.time()
    print(f"[DEBUG] [_build_train_card] Formatting final train card for {lid}. Map CID: {cid}")
    meta=meta or _TRAIN_META.get(lid,{"color":"#8e44ad","label":lid,"subtitle":"","emoji":"🚇"})
    s_s=td['stations'][0]; s_e=td['stations'][-1]
    
    if segs_ov is not None: 
        segs=segs_ov
    else:
        segs=[]
        in_s,_,_=_connector_legs(olat,olon,s_s['lat'],s_s['lon'],f"To {s_s['name']}")
        segs.extend(in_s)
        track=td['track_segments']; flat=[c for sg in track for c in sg]
        segs.append({'type':'train','coords':track,'flat':flat,'color':meta['color'],'label':meta['label'],'stations':td['stations']})
        out_s,_,_=_connector_legs(s_e['lat'],s_e['lon'],dlat,dlon,"To destination")
        segs.extend(out_s)
        
    all_c=[]
    for sg in segs:
        if sg['type']=='train': all_c.extend(sg.get('flat') or[c for t in sg['coords'] for c in t])
        else: all_c.extend(sg['coords'])
        
    tmin=0; tdist=0.0
    for sg in segs:
        if sg['type']=='train':
            d=sum(_poly_dist(s) for s in sg['coords']); tmin+=max(1,int(d/(40_000/60))); tdist+=d
        else:
            d=_poly_dist(sg['coords']) if len(sg['coords'])>=2 else 0; tmin+=max(1,int(d/(1.2*60))); tdist+=d
            
    sc=len(td['stations'])
    print(f"[DEBUG] [_build_train_card] Train card rendered. Output coords length: {len(all_c)}. Time: {time.time() - t_start:.4f}s")
    
    return {"id":cid,"name":name_ov or meta['label'],"subtitle":meta.get('subtitle',''),"type":"transit",
            "color":meta['color'],"emoji":meta.get('emoji','🚇'),"time":f"~{tmin} mins",
            "distance":f"{tdist/1000:.1f} km","coords":all_c,"segments":segs,"stations":td['stations'],
            "station_count":sc,"safety_score":88,
            "hazards_flagged":f"{sc} stops · {s_s['name']} → {s_e['name']}"}

def _build_xfer_card(la,da,ma,lb,db,mb,xfer,olat,olon,dlat,dlon,cid):
    t_start = time.time()
    print(f"[DEBUG] [_build_xfer_card] Building transfer train card {la} -> {lb}")
    sa_s=da['stations'][0]; sa_e=da['stations'][-1]
    sb_s=db['stations'][0]; sb_e=db['stations'][-1]
    segs=[]
    
    w,_,_=_walk_seg(olat,olon,sa_s['lat'],sa_s['lon'],f"Walk to {sa_s['name']}"); (segs.append(w) if w else None)
    ta=da['track_segments']
    segs.append({'type':'train','coords':ta,'flat':[c for s in ta for c in s],'color':ma['color'],'label':ma['label'],'stations':da['stations']})
    
    wx,_,_=_walk_seg(sa_e['lat'],sa_e['lon'],sb_s['lat'],sb_s['lon'],xfer['label'])
    segs.append(wx or {'type':'walk','coords':[[sa_e['lat'],sa_e['lon']],[sb_s['lat'],sb_s['lon']]],'color':'#95a5a6','label':xfer['label']})
    
    tb=db['track_segments']
    segs.append({'type':'train','coords':tb,'flat':[c for s in tb for c in s],'color':mb['color'],'label':mb['label'],'stations':db['stations']})
    
    wo,_,_=_walk_seg(sb_e['lat'],sb_e['lon'],dlat,dlon,"Walk to destination"); (segs.append(wo) if wo else None)
    
    merged={'stations':da['stations']+db['stations'],'track_segments':ta+tb}
    cm={**ma,'label':f"{ma['label']} + {mb['label']}",'subtitle':f"Transfer at {sa_e['name']} → {sb_s['name']}",'emoji':'🔄'}
    
    print(f"[DEBUG][_build_xfer_card] Segment generation complete. Passing to _build_train_card. Time: {time.time() - t_start:.4f}s")
    return _build_train_card(la,merged,cm,olat,olon,dlat,dlon,cid,segs_ov=segs,name_ov=f"{ma['label']} + {mb['label']}")

def plan_transit_journey(orig_lon,orig_lat,dest_lon,dest_lat):
    t_start = time.time()
    print(f"[DEBUG] [plan_transit_journey] Init search for trains between orig:({orig_lat},{orig_lon}) dest:({dest_lat},{dest_lon})")
    MAX_WALK=800; results=[]; cid=0
    direct=[]
    
    for lid in["lrt-1","lrt-2","mrt-3"]:
        st,wy=_fetch_full_line(lid)
        if not st: continue
        td=_slice_line(st,wy,orig_lat,orig_lon,dest_lat,dest_lon)
        if not td: continue
        ws=_osrm_walk_dist_cached(orig_lat,orig_lon,td['stations'][0]['lat'],td['stations'][0]['lon'])
        we=_osrm_walk_dist_cached(dest_lat,dest_lon,td['stations'][-1]['lat'],td['stations'][-1]['lon'])
        if ws and ws<=MAX_WALK and we and we<=MAX_WALK:
            direct.append({'lid':lid,'td':td,'walk':ws+we,'meta':_TRAIN_META[lid]})
            
    print(f"[DEBUG] [plan_transit_journey] Found {len(direct)} potential direct train alignments.")
    xfers=[]
    for xfer in _TRANSFERS:
        l1,l2=xfer['from_line'],xfer['to_line']
        st_a,wy_a=_fetch_full_line(l1); td_a=_slice_line(st_a,wy_a,orig_lat,orig_lon,xfer['lat'],xfer['lon'])
        st_b,wy_b=_fetch_full_line(l2); td_b=_slice_line(st_b,wy_b,xfer['lat'],xfer['lon'],dest_lat,dest_lon)
        if not(td_a and td_b): continue
        ws=_osrm_walk_dist_cached(orig_lat,orig_lon,td_a['stations'][0]['lat'],td_a['stations'][0]['lon'])
        we=_osrm_walk_dist_cached(dest_lat,dest_lon,td_b['stations'][-1]['lat'],td_b['stations'][-1]['lon'])
        if ws and ws<=MAX_WALK and we and we<=MAX_WALK:
            xfers.append({'xfer':xfer,'td_a':td_a,'td_b':td_b,'walk':ws+we,'meta_a':_TRAIN_META[l1],'meta_b':_TRAIN_META[l2]})
            
    print(f"[DEBUG][plan_transit_journey] Found {len(xfers)} potential interchange transit loops.")
    direct.sort(key=lambda x:x['walk']); xfers.sort(key=lambda x:x['walk'])
    
    if direct:
        b=direct[0]
        results.append(_build_train_card(b['lid'],b['td'],b['meta'],orig_lat,orig_lon,dest_lat,dest_lon,0))
    if xfers:
        cid+=1; b=xfers[0]
        results.append(_build_xfer_card(b['meta_a']['label'].lower(),b['td_a'],b['meta_a'],
                                        b['meta_b']['label'].lower(),b['td_b'],b['meta_b'],
                                        b['xfer'],orig_lat,orig_lon,dest_lat,dest_lon,cid))
                                        
    print(f"[DEBUG] [plan_transit_journey] Operations completed in {time.time() - t_start:.4f}s. Routes found: {len(results)}")
    if not results:
        return {"error": "No LRT/MRT station found within walking distance. Try Jeepney, Bus, or Jeepney/Bus mode."}
    return {"routes":results}

# ════════════════════════════════════════════════════════════════════════════════
#  ROAD ROUTES
# ════════════════════════════════════════════════════════════════════════════════
_OSRM_DRIVE="https://router.project-osrm.org/route/v1/driving"

def _osrm_road(olon,olat,dlon,dlat,mode_label,colors):
    t_start = time.time()
    url=f"{_OSRM_DRIVE}/{olon},{olat};{dlon},{dlat}?overview=full&geometries=geojson&alternatives=3&steps=true"
    print(f"[DEBUG] [_osrm_road] Executing road path extraction. Label: {mode_label}")
    print(f"[DEBUG][_osrm_road] Calling endpoint: {url}")
    try:
        t_req = time.time()
        r=requests.get(url,headers={'User-Agent':'SafeRouteAI'},timeout=10).json()
        print(f"[DEBUG] [_osrm_road] OSRM API responded in {time.time() - t_req:.4f}s")
        if r.get("code")!="Ok": 
            print(f"[DEBUG] [_osrm_road] API code error: {r.get('code')}")
            return {"error":"Could not calculate road route."}
    except Exception as e: 
        print(f"[DEBUG] [_osrm_road] Exception: {e}")
        return {"error":"Routing server unavailable."}
        
    routes=[]
    for i,route in enumerate(r.get("routes",[])[:3]):
        coords=[[pt[1],pt[0]] for pt in route["geometry"]["coordinates"]]
        routes.append({"id":i,"name":f"{mode_label} Route {i+1}","type":"road",
                       "color":colors[i%len(colors)],"time":f"{int(route['duration']/60)} mins",
                       "distance":f"{round(route['distance']/1000,1)} km","coords":coords,
                       "segments":[],"stations":[],"safety_score":80,"hazards_flagged":"Clear"})
                       
    print(f"[DEBUG] [_osrm_road] Finalized mapping {len(routes)} variants. Total time: {time.time() - t_start:.4f}s")
    return {"routes":routes}

def get_car_route(olon,olat,dlon,dlat):
    print(f"[DEBUG][get_car_route] Requesting road routes for car...")
    return _osrm_road(olon,olat,dlon,dlat,"Car",["#3498db","#1a6fa3","#0e3d5c"])

def get_motorcycle_route(olon,olat,dlon,dlat):
    print(f"[DEBUG] [get_motorcycle_route] Requesting road routes for motorcycle...")
    return _osrm_road(olon,olat,dlon,dlat,"Motorcycle",["#8e44ad","#9b59b6","#af7ac5"])

def get_walk_route(olon,olat,dlon,dlat):
    t_start = time.time()
    print(f"[DEBUG] [get_walk_route] Fetching pedestrian alternatives...")
    r=_fetch_osrm_foot(olon,olat,dlon,dlat)
    if r:
        names=["Walking Route","Alternative Walk","Scenic Walk"]
        colors=["#2ecc71","#27ae60","#1abc9c"]; out=[]
        for i,route in enumerate(r["routes"][:3]):
            coords=[[pt[1],pt[0]] for pt in route["geometry"]["coordinates"]]
            out.append({"id":i,"name":names[i] if i<len(names) else f"Walk {i+1}","type":"walk",
                        "color":colors[i%len(colors)],"time":f"{int(route['duration']/60)} mins",
                        "distance":f"{round(route['distance']/1000,1)} km","coords":coords,
                        "segments":[],"stations":[],"safety_score":90,"hazards_flagged":"Pedestrian paths only"})
        if out:
            out[0]["mode_label"]="Only Route" if len(out)==1 else "Fastest"
            if len(out)>1: out[1]["mode_label"]="Alternative"
            if len(out)>2: out[2]["mode_label"]="Scenic"
        print(f"[DEBUG][get_walk_route] Fetched {len(out)} paths. Time: {time.time() - t_start:.4f}s")
        return {"routes":out}
    print(f"[DEBUG][get_walk_route] Walk extraction failed. Time: {time.time() - t_start:.4f}s")
    return {"error":"Could not calculate walking route."}

# ════════════════════════════════════════════════════════════════════════════════
#  NEARBY TRANSIT
# ════════════════════════════════════════════════════════════════════════════════
def get_nearby_transit(lat,lon,radius_m=1000):
    t_start = time.time()
    print(f"[DEBUG] [get_nearby_transit] Commencing local area search radius: {radius_m}m")
    _load_sakay(); nearby=[]
    for rid_list,ttype,tcolor,fare_info in[
        (_SAKAY_PUJ,'jeepney','#e67e22','PHP 13 base'),
        (_SAKAY_PUB,'bus',    '#16a085','PHP 15 base'),
        (_SAKAY_RAIL,'train', '#27ae60','LRT/MRT fare') # Enables Sakay robust GTFS definitions targeting mapping stations flawlessly
    ]:
        for rid in rid_list:
            route=_SAKAY_ROUTES.get(rid)
            if not route: continue
            best_s=None; min_d=float('inf')
            for s in route['stops']:
                d=_hav(lat,lon,s['lat'],s['lon'])
                if d<min_d: min_d=d; best_s=s
            if min_d<=radius_m and best_s:
                rn = route.get('route_long_name', rid).replace('LRT-','LRT').replace('MRT-','MRT')
                if not any(x['name']==best_s['name'] and x['type']==ttype for x in nearby):
                    nearby.append({'type':ttype,'color':tcolor,'route_name':rn,
                                   'name':best_s['name'],'lat':best_s['lat'],'lon':best_s['lon'],
                                   'dist':min_d,'fare_info':fare_info})

    # Backup OSML fallback mapping any untargeted structures outside metro routes handling limits smoothly
    for lid,data in _LINE_CACHE.items():
        if not data or not data[0]: continue
        stations,_=data; best_s=None; min_d=float('inf')
        for st in stations:
            d=_hav(lat,lon,st['lat'],st['lon'])
            if d<min_d: min_d=d; best_s=st
        if min_d<=radius_m and best_s:
            if not any(x['name']==best_s['name'] and x['type']=='train' for x in nearby):
                nearby.append({'type':'train','color':'#27ae60','route_name':lid.upper(),
                               'name':best_s['name'],'lat':best_s['lat'],'lon':best_s['lon'],'dist':min_d})
                
    nearby.sort(key=lambda x:x['dist'])
    final_output = nearby[:5]
    print(f"[DEBUG] [get_nearby_transit] Found {len(nearby)} matches. Sliced top {len(final_output)}. Time taken: {time.time() - t_start:.4f}s")
    return final_output

# ════════════════════════════════════════════════════════════════════════════════
#  MAIN ENTRYPOINT
# ════════════════════════════════════════════════════════════════════════════════
def _tag_routes(routes, mode_key, label, color):
    t_start = time.time()
    for r in routes:
        r.setdefault('mode_label',       label)
        r.setdefault('mode_label_color', color)
    # print(f"[DEBUG] [_tag_routes] Applied tags to {len(routes)} routes in {time.time() - t_start:.4f}s")


def get_navigation_data(orig_lon,orig_lat,dest_lon,dest_lat,commuter_type,flood_zones):
    t_start = time.time()
    print(f"[DEBUG][get_navigation_data] Navigating Mode: '{commuter_type}'")
    print(f"[DEBUG][get_navigation_data] Origin: ({orig_lat},{orig_lon}) -> Dest: ({dest_lat},{dest_lon})")
    ctype=commuter_type.lower().strip()
    surface_types=('transit','jeepney','bus','train','jeepney_bus','train_jeepney','train_bus')

    dist_crow = _hav(orig_lat,orig_lon,dest_lat,dest_lon)
    print(f"[DEBUG] [get_navigation_data] Crow-flies distance evaluated as {dist_crow:.2f}m")
    
    if dist_crow<=1000 and ctype in surface_types:
        print(f"[DEBUG] [get_navigation_data] Walk bypass triggered. Target very close.")
        r = get_walk_route(orig_lon,orig_lat,dest_lon,dest_lat)
        print(f"[DEBUG] [get_navigation_data] Output ready in {time.time() - t_start:.4f}s")
        return r

    if ctype=='jeepney':
        print(f"[DEBUG] [get_navigation_data] Branch: Jeepney Only")
        r=get_jeepney_route(orig_lon,orig_lat,dest_lon,dest_lat)
        _tag_routes(r.get('routes',[]),'jeepney','Jeepney','#e67e22')
        print(f"[DEBUG] [get_navigation_data] Output ready in {time.time() - t_start:.4f}s")
        return r

    if ctype=='bus':
        print(f"[DEBUG] [get_navigation_data] Branch: Bus Only")
        r=get_bus_route(orig_lon,orig_lat,dest_lon,dest_lat)
        _tag_routes(r.get('routes',[]),'bus','Bus','#16a085')
        print(f"[DEBUG] [get_navigation_data] Output ready in {time.time() - t_start:.4f}s")
        return r

    if ctype=='jeepney_bus':
        print(f"[DEBUG] [get_navigation_data] Branch: Jeepney + Bus Combination")
        r=get_jeepney_bus_route(orig_lon,orig_lat,dest_lon,dest_lat)
        _tag_routes(r.get('routes',[]),'jeepney_bus','Jeepney/Bus','#e67e22')
        print(f"[DEBUG] [get_navigation_data] Output ready in {time.time() - t_start:.4f}s")
        return r

    if ctype=='train':
        print(f"[DEBUG] [get_navigation_data] Branch: Rail Prioritized")
        r=plan_transit_journey(orig_lon,orig_lat,dest_lon,dest_lat)
        # Adding fully baked internal definitions handling gracefully when mapping misses beautifully nicely efficiently
        native_routes = plan_surface_journey(['train'],orig_lat,orig_lon,dest_lat,dest_lon, max_results=2)
        if not r.get('routes',[]) and native_routes: 
            print("[DEBUG] [get_navigation_data] Default train failed, substituting internal native configurations.")
            r = {'routes': native_routes}
            
        _tag_routes(r.get('routes',[]),'train','Train','#27ae60')
        print(f"[DEBUG] [get_navigation_data] Output ready in {time.time() - t_start:.4f}s")
        return r

    if ctype in ('transit','train_jeepney','train_bus'):
        print(f"[DEBUG] [get_navigation_data] Branch: Multimodal Omnichannel ({ctype})")
        surface_modes=[]
        if ctype in ('transit','train_jeepney'): surface_modes.append('jeepney')
        if ctype in ('transit','train_bus'):     surface_modes.append('bus')
        if 'train' in ctype or ctype == 'transit': surface_modes.append('train')
        
        # Unconditionally deploy all enabled networks intelligently perfectly gracefully combining safely!
        if not surface_modes: surface_modes=['jeepney', 'bus', 'train']

        print(f"[DEBUG][get_navigation_data] Extracting surface layers... {surface_modes}")
        surface_routes=plan_surface_journey(surface_modes,orig_lat,orig_lon,
                                            dest_lat,dest_lon,max_results=3)
        for r in surface_routes:
            segs=[s for s in r.get('segments',[]) if s['type'] not in ('walk',)]
            has_train = any(s['type']=='train' for s in segs)
            has_bus=any(s['type']=='bus' for s in segs)
            has_jeep=any(s['type']=='jeepney' for s in segs)
            
            # Map robust labelling cleanly nicely effectively!
            if has_train:
                if has_bus or has_jeep: 
                    r.setdefault('mode_label', 'Train + Connect'); r.setdefault('mode_label_color', '#27ae60')
                else: 
                    r.setdefault('mode_label', 'Train'); r.setdefault('mode_label_color', '#27ae60')
            elif has_bus and has_jeep:
                r.setdefault('mode_label','Jeepney+Bus'); r.setdefault('mode_label_color','#2980b9')
            elif has_bus:
                r.setdefault('mode_label','Bus'); r.setdefault('mode_label_color','#16a085')
            else:
                r.setdefault('mode_label','Jeepney'); r.setdefault('mode_label_color','#e67e22')

        train_routes =[]
        # Maintain graceful external Overpass validation structure silently securely maintaining robustness intelligently cleanly accurately seamlessly gracefully safely perfectly nicely  
        if 'train' in surface_modes:
            print("[DEBUG] [get_navigation_data] Syncing external macro OSM networks...")
            train_resp=plan_transit_journey(orig_lon,orig_lat,dest_lon,dest_lat)
            if "error" not in train_resp: 
                train_routes=train_resp.get('routes',[])
                _tag_routes(train_routes,'train','Train (OSM)','#27ae60')

        combined=surface_routes+train_routes
        if not combined:
            print(f"[DEBUG] [get_navigation_data] FAILED: Zero routes recovered from pipeline. Time: {time.time() - t_start:.4f}s")
            return {"error":"No route found near your origin/destination."}
        
        # Deduplicate exactly mimicking bounds mapping efficiently safely
        print(f"[DEBUG] [get_navigation_data] Removing logical overlaps within {len(combined)} variants...")
        unique_combinations =[]
        seen = set()
        for r in combined:
            tk = r['name']
            if tk not in seen:
                seen.add(tk)
                unique_combinations.append(r)
                
        for i,r in enumerate(unique_combinations): r['id']=i
        print(f"[DEBUG] [get_navigation_data] Deduplication resolved to {len(unique_combinations)} ultimate routes. Output ready in {time.time() - t_start:.4f}s")
        return {"routes":unique_combinations}
        
    # Final fallback branch if non-transit mode is requested (though earlier checks handle this, this is a safety net)
    print(f"[DEBUG] [get_navigation_data] Reached end of logic gracefully. Returning unhandled type map. Time: {time.time() - t_start:.4f}s")
    return {"error": "Unhandled commuter type mapping"}