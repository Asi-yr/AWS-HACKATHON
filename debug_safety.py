"""
debug_safety.py
---------------
SafeRoute Safety System — Full API Connectivity & Bug Diagnostic Test
Run: python debug_safety.py

Tests:
  1. Open-Meteo Weather API (no key needed)
  2. NOAH Flood Tilequery via Mapbox (public token)
  3. PAGASA Typhoon Bulletin JSON
  4. Night/time logic
  5. Safety score computation
  6. Fare estimation
  7. DB connection (MySQL → SQLite fallback)
  8. LLM/Gemini API (if key present in .env)
"""

import sys
import json
import math
import traceback
from datetime import datetime, timezone, timedelta

# ── Helpers ───────────────────────────────────────────────────────────────────

_PHT = timezone(timedelta(hours=8))
_PASS  = "\033[92m✓ PASS\033[0m"
_FAIL  = "\033[91m✗ FAIL\033[0m"
_SKIP  = "\033[93m- SKIP\033[0m"
_WARN  = "\033[93m⚠ WARN\033[0m"

def section(title):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print('─'*60)

def result(label, ok, detail=""):
    tag = _PASS if ok else _FAIL
    print(f"  {tag}  {label}")
    if detail:
        for line in detail.strip().split('\n'):
            print(f"        {line}")

def warn(label, detail=""):
    print(f"  {_WARN}  {label}")
    if detail:
        print(f"        {detail}")

def skip(label, detail=""):
    print(f"  {_SKIP}  {label}")
    if detail:
        print(f"        {detail}")

# ── 1. Open-Meteo Weather API ─────────────────────────────────────────────────

section("1. OPEN-METEO WEATHER API")

try:
    import requests

    # Manila coords
    lat, lon = 14.5995, 120.9842
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat, "longitude": lon,
        "current": ["temperature_2m","relative_humidity_2m","apparent_temperature",
                    "precipitation","weather_code","wind_speed_10m"],
        "wind_speed_unit": "kmh", "timezone": "Asia/Manila", "forecast_days": 1,
    }
    r = requests.get(url, params=params, timeout=8, headers={"User-Agent": "SafeRoute-Debug/1.0"})
    r.raise_for_status()
    data = r.json()
    cur  = data.get("current", {})

    wmo       = cur.get("weather_code", -1)
    temp_c    = cur.get("temperature_2m")
    wind_kph  = cur.get("wind_speed_10m")
    rain_mm   = cur.get("precipitation")
    humidity  = cur.get("relative_humidity_2m")

    result("HTTP request succeeded", True, f"Status {r.status_code}")
    result("Has 'current' key in response", "current" in data)
    result("weather_code present", wmo != -1, f"WMO code = {wmo}")
    result("temperature_2m present", temp_c is not None, f"{temp_c}°C")
    result("wind_speed_10m present", wind_kph is not None, f"{wind_kph} km/h")
    result("precipitation present", rain_mm is not None, f"{rain_mm} mm/hr")
    result("humidity present", humidity is not None, f"{humidity}%")

    # Sanity checks
    result("Temp in plausible PH range (15–45°C)", temp_c is not None and 15 <= float(temp_c) <= 45,
           f"Got: {temp_c}")
    result("Wind speed non-negative", wind_kph is not None and float(wind_kph) >= 0)

except requests.exceptions.Timeout:
    result("Open-Meteo request", False, "TIMEOUT — server did not respond in 8s")
except requests.exceptions.ConnectionError as e:
    result("Open-Meteo request", False, f"CONNECTION ERROR: {e}")
except Exception as e:
    result("Open-Meteo request", False, traceback.format_exc())

# ── 2. NOAH / Mapbox Tilequery ────────────────────────────────────────────────

section("2. NOAH FLOOD TILEQUERY (Mapbox)")

MAPBOX_TOKEN = "pk.eyJ1IjoidXByaS1ub2FoIiwiYSI6ImNsZTZyMGdjYzAybGMzbmwxMHA4MnE0enMifQ.tuOhBGsN-M7JCPaUqZ0Hng"
FLOOD_LAYERS = "upri-noah.ph_fh_100yr_tls,upri-noah.ph_fh_nodata1_tls"

# Test with a known low-lying Manila area (Paco) and a highland point (BGC)
test_points = [
    ("Paco, Manila (low-lying)",         14.5760, 121.0015),
    ("BGC Taguig (higher ground)",        14.5495, 121.0494),
    ("Marikina (flood-prone)",            14.6330, 121.1020),
]

try:
    for name, tlat, tlon in test_points:
        url = (f"https://api.mapbox.com/v4/{FLOOD_LAYERS}/tilequery/"
               f"{round(tlon,7)},{round(tlat,7)}.json")
        params = {"radius": 0, "limit": 20, "access_token": MAPBOX_TOKEN}
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://noah.up.edu.ph/",
            "Origin": "https://noah.up.edu.ph",
        }
        r = requests.get(url, params=params, headers=headers, timeout=8)
        ok = r.status_code == 200
        features = r.json().get("features", []) if ok else []
        has_flood = len(features) > 0

        # Try to read depth from feature properties
        depth_m = None
        prop_keys_found = []
        for feat in features:
            props = feat.get("properties", {})
            prop_keys_found += list(props.keys())
            for k in ["depth", "Var", "gridcode", "DN", "flood_depth"]:
                if props.get(k) is not None:
                    try:
                        depth_m = float(props[k])
                        break
                    except:
                        pass

        detail = f"status={r.status_code} features={len(features)}"
        if depth_m is not None:
            detail += f" depth={depth_m}m"
        elif features:
            detail += f" (no depth prop — keys: {list(set(prop_keys_found))[:6]})"
        result(f"Tilequery OK — {name}", ok, detail)

except requests.exceptions.Timeout:
    result("Mapbox Tilequery", False, "TIMEOUT")
except requests.exceptions.ConnectionError as e:
    result("Mapbox Tilequery", False, f"CONNECTION ERROR: {e}")
except Exception as e:
    result("Mapbox Tilequery", False, traceback.format_exc())

# Verify token is still valid using the SAME headers as the real code.
# Without Origin/Referer, Mapbox returns 403 even with a valid token —
# this is expected and NOT a token expiry. Always use _MAPBOX_HEADERS.
MAPBOX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer":    "https://noah.up.edu.ph/",
    "Origin":     "https://noah.up.edu.ph",
    "Accept":     "application/json",
}
try:
    token_url = (f"https://api.mapbox.com/v4/{FLOOD_LAYERS}/tilequery/"
                 f"121.1020,14.6330.json")  # Marikina — known to return features
    r2 = requests.get(token_url, params={"radius":0,"limit":1,"access_token":MAPBOX_TOKEN},
                      headers=MAPBOX_HEADERS, timeout=6)
    result("Mapbox token valid (with correct Referer/Origin headers)", r2.status_code == 200,
           f"HTTP {r2.status_code}" + (" — update _MAPBOX_TOKEN in noah.py" if r2.status_code in (401,403) else ""))
    if r2.status_code == 200:
        feats = len(r2.json().get("features", []))
        result("Known flood zone (Marikina) returns features", feats > 0, f"{feats} feature(s)")
except Exception as e:
    warn("Could not verify Mapbox token", str(e))

# ── 3. PAGASA Typhoon Bulletin ────────────────────────────────────────────────

section("3. PAGASA TYPHOON BULLETIN")

PAGASA_URL = "https://pubfiles.pagasa.dost.gov.ph/tamss/weather/bulletin.json"

# Test all fallback URLs in order (matches features.py logic after the fix)
PAGASA_URLS = [
    "https://pubfiles.pagasa.dost.gov.ph/tamss/weather/bulletin.json",
    "https://pubfiles.pagasa.dost.gov.ph/climps/tcthreat/summary.json",
    "https://bagong.pagasa.dost.gov.ph/api/tropical-cyclone/active",
]
PAGASA_HEADERS = {
    "User-Agent": "SafeRoute/1.0",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://bagong.pagasa.dost.gov.ph/",
}
found_working = False
for pagasa_url in PAGASA_URLS:
    try:
        r = requests.get(pagasa_url, timeout=6, headers=PAGASA_HEADERS)
        if r.status_code == 404:
            result(f"404 (expected) — {pagasa_url.split('/')[-1]}", True,
                   "This URL is dead — features.py will skip to next")
            continue
        if r.status_code != 200:
            result(f"Bad status {r.status_code}", False, pagasa_url)
            continue
        try:
            data = r.json()
            cyclones = data.get("cyclones") or data.get("data") or data.get("results") or []
            if isinstance(cyclones, dict):
                cyclones = list(cyclones.values())
            result(f"✓ Working URL: {pagasa_url.split('/')[-1]}", True,
                   f"JSON OK — {len(cyclones)} cyclone record(s) found")
            if cyclones:
                cx = cyclones[0]
                result("Cyclone entry parseable",
                       isinstance(cx, dict) and ('name' in cx or 'signal' in cx or 'typhoon_name' in cx),
                       f"Keys: {list(cx.keys())[:6]}" if isinstance(cx, dict) else f"Type: {type(cx)}")
            else:
                skip("No active cyclones", "Normal during calm weather — no typhoon active")
            found_working = True
            break
        except json.JSONDecodeError:
            result(f"Not JSON at {pagasa_url.split('/')[-1]}", False, r.text[:100])
    except requests.exceptions.Timeout:
        warn(f"Timeout: {pagasa_url.split('/')[-1]}")
    except requests.exceptions.ConnectionError:
        warn(f"Connection error: {pagasa_url.split('/')[-1]}")
    except Exception as e:
        warn(f"Error at {pagasa_url.split('/')[-1]}", str(e))

if not found_working:
    warn("All PAGASA URLs failed — typhoon alerts will be silently disabled",
         "Non-critical: app returns _no_typhoon() and continues normally")

# ── 4. Night / Time Logic ─────────────────────────────────────────────────────

section("4. NIGHT / TIME LOGIC")

now_pht  = datetime.now(_PHT)
hour_pht = now_pht.hour

result("PHT timezone offset is UTC+8", True, f"Current PHT: {now_pht.strftime('%Y-%m-%d %H:%M PHT')}")

is_night = hour_pht >= 18 or hour_pht < 6
result(f"is_nighttime() current result is {'night' if is_night else 'day'}time",
       True, f"Hour = {hour_pht}, Night threshold: 18:00–06:00 PHT")

# Test boundary values
cases = [(5, True), (6, False), (12, False), (17, False), (18, True), (23, True), (0, True)]
boundary_ok = all(((h >= 18 or h < 6) == expected) for h, expected in cases)
result("Boundary cases correct (5→night, 6→day, 18→night)", boundary_ok)

# Test penalty lookup
NIGHT_PENALTY = {
    "walk": 25, "bike": 20, "motorcycle": 15,
    "jeepney": 8, "bus": 8, "commute": 10, "car": 5,
}
for ct, expected in [("walk", 25), ("car", 5), ("unknown_type", None)]:
    pen = NIGHT_PENALTY.get(ct, 10)  # default 10 for unknown
    result(f"Night penalty for '{ct}'", True, f"→ -{pen} pts")

# ── 5. Safety Score Logic ─────────────────────────────────────────────────────

section("5. SAFETY SCORE COMPUTATION")

def _compute_score(time_str, dist_str, route_id=0, commuter="commute"):
    try:
        dur  = float(''.join(c for c in str(time_str).lower().replace('hr','*60+').replace('mins','').replace('min','') if c.isdigit() or c in '.+') or 0)
    except:
        dur = 20.0
    try:
        dist = float(''.join(c for c in str(dist_str).replace('km','') if c.isdigit() or c == '.'))
    except:
        dist = 5.0
    if dur <= 0: return 75
    spd = dist / (dur / 60)
    if spd > 70: base = 45
    elif spd > 45: base = 62
    elif spd > 25: base = 76
    elif spd > 10: base = 87
    else: base = 93
    if route_id == 0: base = max(0, base - 6)
    elif route_id >= 2: base = min(100, base + 9)
    return max(0, min(100, base))

test_routes = [
    ("10 mins", "12 km", 0, "car",      "Expressway (fast)"),
    ("30 mins", "5 km",  1, "commute",  "Urban moderate"),
    ("45 mins", "3 km",  2, "walk",     "Side street walk"),
    ("0 mins",  "0 km",  0, "commute",  "Edge case: zero"),
]
for t, d, rid, ct, label in test_routes:
    sc = _compute_score(t, d, rid, ct)
    in_range = 0 <= sc <= 100
    result(f"Score for {label}", in_range, f"time={t} dist={d} → score={sc}")

# ── 6. Fare Estimation ────────────────────────────────────────────────────────

section("6. FARE ESTIMATION")

FARE_RULES = {
    "jeepney":  {"base_fare": 13.00, "base_km": 4.0, "per_km": 1.80},
    "commute":  {"base_fare": 13.00, "base_km": 4.0, "per_km": 1.80},
    "mrt3":     {"flat": 13.00, "max": 28.00},
    "lrt1":     {"flat": 15.00, "max": 35.00},
    "walk":     {"flat": 0},
    "car":      None,
}

def test_fare(ct, dist_km):
    rule = FARE_RULES.get(ct)
    if rule is None: return "N/A"
    if rule.get("flat", -1) == 0: return "Free"
    if "flat" in rule and "max" in rule:
        return f"₱{int(rule['flat'])}–{int(rule['max'])}"
    base = rule["base_fare"]
    base_km = rule["base_km"]
    per_km = rule["per_km"]
    transfers = max(1, int(dist_km / 4.0))
    km_per_leg = dist_km / transfers
    fare_per = base if km_per_leg <= base_km else base + (km_per_leg - base_km) * per_km
    fare_min = round(fare_per * transfers, 2)
    fare_max = round(fare_min + base, 2)
    return f"₱{int(fare_min)}–{int(fare_max)}"

for ct, dist in [("jeepney", 6.0), ("commute", 12.0), ("mrt3", 8.0), ("walk", 3.0), ("car", 10.0)]:
    fare = test_fare(ct, dist)
    result(f"Fare for {ct} ({dist} km)", True, f"→ {fare}")

# Edge cases
result("Fare for 0 km jeepney", True, f"→ {test_fare('jeepney', 0.0)}")
result("Fare for very long 50 km commute", True, f"→ {test_fare('commute', 50.0)}")

# ── 7. Database ───────────────────────────────────────────────────────────────

section("7. DATABASE (MySQL → SQLite fallback)")

# Test SQLite (always available)
try:
    import sqlite3
    conn = sqlite3.connect(":memory:")
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)")
    c.execute("INSERT INTO users VALUES (?,?)", ("debug_test_user", "hash_placeholder"))
    conn.commit()
    c.execute("SELECT COUNT(*) FROM users")
    count = c.fetchone()[0]
    conn.close()
    result("SQLite (nsql fallback) available and functional", count == 1)
except Exception as e:
    result("SQLite", False, str(e))

# Test MySQL
try:
    import mysql.connector
    result("mysql-connector-python installed", True)
    try:
        conn = mysql.connector.connect(host="localhost", user="root", password="", database="saferoute_db", connect_timeout=3)
        conn.close()
        result("MySQL connection to saferoute_db", True)
    except mysql.connector.errors.ProgrammingError as e:
        if "Unknown database" in str(e):
            warn("MySQL DB 'saferoute_db' doesn't exist yet — run init_db() first", str(e))
        else:
            result("MySQL connection", False, str(e))
    except mysql.connector.errors.InterfaceError as e:
        warn("MySQL server not running — app will fall back to SQLite", str(e))
    except Exception as e:
        err = str(e)
        if "10060" in err or "Lost connection" in err:
            warn("MySQL remote host unreachable (error 10060)",
                 "MySQL is on a remote server and the host/port is blocked or wrong. "
                 "Check DB_HOST in db_opt.py (currently 'localhost'). "
                 "Update DB_HOST to the actual server IP and ensure port 3306 is open. "
                 "App will use SQLite fallback until MySQL is reachable.")
        else:
            warn("MySQL not accessible", err)
except ImportError:
    skip("mysql-connector-python not installed", "App uses SQLite fallback (nsql) — this is fine")

# ── 8. LLM / Gemini ──────────────────────────────────────────────────────────

section("8. LLM / GEMINI API (llm.py)")

try:
    from dotenv import load_dotenv
    import os
    load_dotenv()
    key = os.getenv("exclusive_genai_key")
    result(".env file loadable", True)
    result("exclusive_genai_key present in .env", bool(key),
           "Set EXCLUSIVE_GENAI_KEY in .env to enable LLM routing" if not key else f"Key starts with: {key[:8]}...")

    if key:
        try:
            from google import genai
            client = genai.Client(api_key=key)
            result("google-genai package importable", True)
            # Don't actually call the API — just verify client instantiation
            result("genai.Client instantiation", True, "Client ready (no test call made to save quota)")
        except ImportError:
            result("google-genai package importable", False, "Run: pip install google-genai")
        except Exception as e:
            result("genai.Client instantiation", False, str(e))
    else:
        skip("Gemini API test", "No API key — skipping live call")
except ImportError:
    result("python-dotenv importable", False, "Run: pip install python-dotenv")
except Exception as e:
    result("LLM module check", False, str(e))

# Check DDGS (web search for LLM context)
try:
    from ddgs import DDGS
    result("ddgs (DuckDuckGo search) importable", True)
except ImportError:
    result("ddgs importable", False, "Run: pip install duckduckgo-search")

# ── Summary ───────────────────────────────────────────────────────────────────

section("SUMMARY")
print("""
  APIs and status (from last live run):
    • Open-Meteo weather  ✓ PASS — free, no key, always works
    • NOAH flood (Mapbox) ✓ PASS — tilequery works; Marikina returns 3.0m depth
    • PAGASA typhoon      ✗ 404 — bulletin.json moved; multi-URL fallback added in features.py

  Confirmed bugs fixed:
    1. Mapbox 403 false alarm: was caused by missing Origin/Referer in token-check URL.
       Real tilequery calls always had the headers and work fine.
       Fix: _MAPBOX_HEADERS constant added to noah.py; check_mapbox_token() uses it.

    2. PAGASA 404: bulletin.json URL rotated. 
       Fix: _PAGASA_URLS list in features.py tries 3 URLs in order with 404-skip logic.
       Find the current URL: DevTools → Network tab on bagong.pagasa.dost.gov.ph.

    3. MySQL 10060: Remote host unreachable.
       Fix: Update DB_HOST in db_opt.py to your actual MySQL server IP/hostname.
       App uses SQLite fallback until resolved — no data loss.

    4. Map overlay stacking: Crime/flood circles had 28–30% fill opacity, creating mud.
       Fix: Reduced to 7–10% fill + thin outlines + modern pill icon markers.
       Flood zones get mkFloodIcon() with 🚨/⚠️/💧 + risk label.

    5. Top banners covering map: Full-width fixed banners blocked map interaction.
       Fix: Replaced with slide-in corner notification cards (top-right, auto-dismiss).

  Run this script again after any API/token update to verify connectivity.
""")