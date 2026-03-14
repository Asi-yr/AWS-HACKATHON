"""
run_debug.py
============
Drop this file ANYWHERE in your project and run it:

    python run_debug.py

It will test every function in every risk_monitor module and print
exactly what each one is doing, what it calls, how long it takes,
and whether it fails.

NO CHANGES TO YOUR OTHER FILES NEEDED.
No RM_DEBUG env var. No _dbg.py. Just run this.

Requirements: your risk_monitor/ folder must be importable
(i.e. run from the folder that CONTAINS risk_monitor/).
"""

import sys
import os
import time
import traceback
import functools
import threading
from datetime import datetime, timezone, timedelta

# ─────────────────────────────────────────────────────────────────────────────
# COLOUR OUTPUT
# ─────────────────────────────────────────────────────────────────────────────

_TTY = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

def _c(code): return f"\033[{code}m" if _TTY else ""

GREY    = _c("90"); CYAN  = _c("96"); GREEN  = _c("92")
YELLOW  = _c("93"); RED   = _c("91"); BLUE   = _c("94")
MAGENTA = _c("95"); BOLD  = _c("1");  RESET  = _c("0")

_PHT   = timezone(timedelta(hours=8))
_LOCK  = threading.Lock()
_LOG   = []          # every emitted line stored here for the final summary
_ERRORS = []         # (module, fn, error_str)


def _ts():
    n = datetime.now(_PHT)
    return n.strftime("%H:%M:%S.") + f"{n.microsecond // 1000:03d}"


def _short(v, limit=72):
    if v is None:             return "None"
    if isinstance(v, bool):   return str(v)
    if isinstance(v, (int, float)): return repr(v)
    if isinstance(v, str):
        s = v.replace("\n", "↵")
        return f'"{s[:limit]}{"…" if len(s) > limit else ""}"'
    if isinstance(v, list):
        if not v: return "list[]"
        return f"list[{len(v)}]  first={_short(v[0], 40)}"
    if isinstance(v, dict):
        return f"dict{{{len(v)}}}  keys={list(v.keys())[:4]}"
    if isinstance(v, tuple):  return f"tuple({len(v)})"
    return type(v).__name__


def _emit(colour, tag, mod, fn, msg):
    line = (
        f"{GREY}[{_ts()}]{RESET} "
        f"{colour}{BOLD}{tag:<9}{RESET} "
        f"{CYAN}{mod}.{fn}{RESET}  "
        f"{msg}"
    )
    with _LOCK:
        _LOG.append(line)
        print(line, flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# EMIT HELPERS  (same API as _dbg.py so you can swap later)
# ─────────────────────────────────────────────────────────────────────────────

def dbg_enter(mod, fn, **kw):
    parts = "  ".join(f"{YELLOW}{k}{RESET}={_short(v)}" for k, v in kw.items())
    _emit(GREEN,   ">>>ENTER", mod, fn, parts or "(no args)")
    return time.perf_counter()

def dbg_step(mod, fn, msg, **kw):
    extra = "  ".join(f"{YELLOW}{k}{RESET}={_short(v)}" for k, v in kw.items())
    _emit(BLUE,    "   STEP ", mod, fn, f"{msg}  {extra}" if extra else msg)

def dbg_call(mod, fn, callee, **kw):
    parts = "  ".join(f"{k}={_short(v)}" for k, v in kw.items())
    _emit(MAGENTA, "  →CALL ", mod, fn, f"{BOLD}{callee}{RESET}({parts})")

def dbg_cache(mod, fn, hit, key):
    tag = "💾 HIT " if hit else "💾 MISS"
    col = GREEN if hit else YELLOW
    _emit(col, tag, mod, fn, f"key={BOLD}{key}{RESET}")

def dbg_exit(mod, fn, t0, val):
    ms = (time.perf_counter() - t0) * 1000
    _emit(GREEN, "<<<EXIT ", mod, fn,
          f"{BOLD}{ms:.2f}ms{RESET}  return={_short(val)}")

def dbg_err(mod, fn, t0, exc):
    ms = (time.perf_counter() - t0) * 1000
    _emit(RED, "!!!ERROR", mod, fn,
          f"{BOLD}{ms:.2f}ms{RESET}  {type(exc).__name__}: {exc}")
    tb = traceback.format_exc().splitlines()
    for ln in tb[-6:]:
        print(f"          {RED}↳{RESET} {ln}", flush=True)
    _ERRORS.append(f"{mod}.{fn}: {type(exc).__name__}: {exc}")

def dbg_warn(mod, fn, msg):
    _emit(YELLOW, "  WARN  ", mod, fn, msg)


# ─────────────────────────────────────────────────────────────────────────────
# DECORATOR — wraps any function with full enter/exit/error logging
# ─────────────────────────────────────────────────────────────────────────────

def traced(mod):
    """Usage:  @traced("weather")  above any def"""
    def decorator(func):
        fn = func.__name__
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # build a short arg summary — skip db/conn/self
            import inspect
            try:   sig = inspect.signature(func)
            except Exception: sig = None
            params = list(sig.parameters.keys()) if sig else []
            kw_show = {}
            for i, a in enumerate(args):
                name = params[i] if i < len(params) else f"arg{i}"
                if name in ("self", "db", "c", "conn"): continue
                if isinstance(a, (int, float, str, bool)) or a is None:
                    kw_show[name] = a
                elif isinstance(a, list):   kw_show[name] = f"list[{len(a)}]"
                elif isinstance(a, dict):   kw_show[name] = f"dict{{{len(a)}}}"
                else:                       kw_show[name] = type(a).__name__
            for k, v in kwargs.items():
                if k in ("self", "db", "c", "conn"): continue
                kw_show[k] = v
            t0 = dbg_enter(mod, fn, **kw_show)
            try:
                result = func(*args, **kwargs)
                dbg_exit(mod, fn, t0, result)
                return result
            except Exception as exc:
                dbg_err(mod, fn, t0, exc)
                raise
        return wrapper
    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# PATCH — monkey-patch every public function in a module at runtime
# ─────────────────────────────────────────────────────────────────────────────

def patch_module(module, label):
    """Wrap every callable in `module` with the traced decorator."""
    import inspect
    patched = 0
    for name in dir(module):
        if name.startswith("_"):      continue   # skip private
        obj = getattr(module, name)
        if not callable(obj):         continue
        if not inspect.isfunction(obj): continue  # skip classes, etc.
        try:
            setattr(module, name, traced(label)(obj))
            patched += 1
        except Exception:
            pass
    print(f"{GREEN}✓{RESET} Patched {BOLD}{label}{RESET} ({patched} functions)")
    return patched


# ─────────────────────────────────────────────────────────────────────────────
# IMPORT & PATCH ALL MODULES
# ─────────────────────────────────────────────────────────────────────────────

def load_and_patch():
    modules = {}
    targets = [
        ("risk_monitor.weather",             "weather"),
        ("risk_monitor.phivolcs",            "phivolcs"),
        ("risk_monitor.safe_spots",          "safe_spots"),
        ("risk_monitor.vulnerable_profiles", "vuln_profiles"),
        ("risk_monitor.features",            "features"),
        ("risk_monitor.noah",                "noah"),
        ("risk_monitor.community_reports",   "community_reports"),
        ("risk_monitor.crime_data",          "crime_data"),
        ("risk_monitor.incidents",           "incidents"),
        ("risk_monitor.mmda",                "mmda"),
        ("risk_monitor.sos",                 "sos"),
        ("risk_monitor.user_data",           "user_data"),
        ("risk_monitor.network_utils",       "network_utils"),
    ]

    print(f"\n{BOLD}{'─'*60}{RESET}")
    print(f"{BOLD}  SafeRoute — Patching all risk_monitor modules{RESET}")
    print(f"{BOLD}{'─'*60}{RESET}\n")

    for import_path, label in targets:
        try:
            import importlib
            mod = importlib.import_module(import_path)
            patch_module(mod, label)
            modules[label] = mod
        except ImportError as e:
            print(f"{YELLOW}⚠ Could not import {import_path}: {e}{RESET}")
        except Exception as e:
            print(f"{RED}✗ Failed patching {import_path}: {e}{RESET}")

    print()
    return modules


# ─────────────────────────────────────────────────────────────────────────────
# TEST RUNNERS — one per module, using fake/mock data so no real network needed
# ─────────────────────────────────────────────────────────────────────────────

def _section(title):
    print(f"\n{BOLD}{CYAN}{'═'*60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'═'*60}{RESET}\n")


# ── Shared fake data ──────────────────────────────────────────────────────────

FAKE_WEATHER_CLEAR = {
    "ok": True, "risk_level": "clear", "wmo_code": 0,
    "description": "Clear sky", "temp_c": 30.0,
    "feels_like_c": 33.0, "humidity_pct": 65,
    "wind_kph": 10.0, "rain_mm": 0.0,
    "color": "#27ae60", "fetched_at": "TEST", "error": None,
}
FAKE_WEATHER_RAIN = {
    "ok": True, "risk_level": "heavy_rain", "wmo_code": 65,
    "description": "Heavy rain", "temp_c": 25.0,
    "feels_like_c": 27.0, "humidity_pct": 92,
    "wind_kph": 38.0, "rain_mm": 14.5,
    "color": "#c0392b", "fetched_at": "TEST", "error": None,
}
FAKE_ROUTE = {
    "id": 0, "commuter_type": "walk",
    "safety_score": 80.0,
    "time": "25 mins", "distance": "4.2 km",
    "has_flood_zones": True,
    "crime_warning": "Snatching reported near Divisoria",
    "seismic_warning": "",
    "flood_warning": "Moderate flood risk",
    "coords": [
        [14.5995, 120.9842],
        [14.6020, 120.9860],
        [14.6050, 120.9890],
        [14.6080, 120.9920],
        [14.6100, 120.9950],
    ],
    "segments": [],
}
FAKE_ROUTE_2 = {
    "id": 1, "commuter_type": "commute",
    "safety_score": 75.0,
    "time": "35 mins", "distance": "6.8 km",
    "has_flood_zones": False,
    "crime_warning": "",
    "seismic_warning": "",
    "flood_warning": "",
    "coords": [[14.5995, 120.9842], [14.6200, 121.0100]],
    "segments": [],
}
FAKE_ROUTES    = [dict(FAKE_ROUTE), dict(FAKE_ROUTE_2)]
FAKE_EARTHQUAKES = [
    {
        "id": "us7000fake1", "magnitude": 5.2, "depth_km": 12.0,
        "place": "25 km NE of Manila, Philippines",
        "lat": 14.75, "lon": 121.05,
        "time_pht": "2025-07-10 08:30 PHT",
        "severity": "high", "color": "#e74c3c",
        "radius_km": 80.0, "tsunami": False,
        "url": "https://earthquake.usgs.gov/",
    },
    {
        "id": "us7000fake2", "magnitude": 4.1, "depth_km": 35.0,
        "place": "Batangas Province, Philippines",
        "lat": 13.90, "lon": 121.10,
        "time_pht": "2025-07-10 06:15 PHT",
        "severity": "moderate", "color": "#e67e22",
        "radius_km": 20.0, "tsunami": False,
        "url": "https://earthquake.usgs.gov/",
    },
]


# ── weather ───────────────────────────────────────────────────────────────────

def test_weather(mods):
    _section("weather.py")
    m = mods.get("weather")
    if not m: print(f"{YELLOW}weather not loaded — skipping{RESET}"); return

    dbg_step("TEST", "weather", "Testing get_weather_warning with heavy_rain + walk")
    m.get_weather_warning(FAKE_WEATHER_RAIN, "walk")

    dbg_step("TEST", "weather", "Testing get_weather_warning with clear + motorcycle")
    m.get_weather_warning(FAKE_WEATHER_CLEAR, "motorcycle")

    dbg_step("TEST", "weather", "Testing get_weather_risk_penalty  heavy_rain + walk")
    m.get_weather_risk_penalty(FAKE_WEATHER_RAIN, "walk")

    dbg_step("TEST", "weather", "Testing get_weather_risk_penalty  clear + car")
    m.get_weather_risk_penalty(FAKE_WEATHER_CLEAR, "car")

    dbg_step("TEST", "weather", "Testing get_weather_banner_html  heavy_rain")
    m.get_weather_banner_html(FAKE_WEATHER_RAIN, "commute")

    dbg_step("TEST", "weather", "Testing get_weather_banner_html  clear (should return empty)")
    m.get_weather_banner_html(FAKE_WEATHER_CLEAR, "walk")

    dbg_step("TEST", "weather", "Testing apply_weather_to_routes")
    routes_copy = [dict(r) for r in FAKE_ROUTES]
    # features must exist for apply_weather_to_routes
    try:
        m.apply_weather_to_routes(routes_copy, FAKE_WEATHER_RAIN, "walk")
    except Exception as e:
        dbg_warn("TEST", "weather", f"apply_weather_to_routes needs features module: {e}")

    dbg_step("TEST", "weather", "Testing get_weather_risk  (REAL network call to Open-Meteo)")
    try:
        m.get_weather_risk(14.5995, 120.9842)
    except Exception as e:
        dbg_warn("TEST", "weather", f"Network call failed (expected offline): {e}")


# ── phivolcs ──────────────────────────────────────────────────────────────────

def test_phivolcs(mods):
    _section("phivolcs.py")
    m = mods.get("phivolcs")
    if not m: print(f"{YELLOW}phivolcs not loaded — skipping{RESET}"); return

    dbg_step("TEST", "phivolcs", "Testing get_seismic_banner_html  with fake earthquakes")
    m.get_seismic_banner_html(FAKE_EARTHQUAKES)

    dbg_step("TEST", "phivolcs", "Testing get_seismic_banner_html  empty list")
    m.get_seismic_banner_html([])

    dbg_step("TEST", "phivolcs", "Testing check_route_seismic_risk  route near Manila quake")
    m.check_route_seismic_risk(FAKE_ROUTE["coords"], FAKE_EARTHQUAKES)

    dbg_step("TEST", "phivolcs", "Testing check_route_seismic_risk  empty inputs")
    m.check_route_seismic_risk([], [])

    dbg_step("TEST", "phivolcs", "Testing apply_seismic_to_routes")
    routes_copy = [dict(r) for r in FAKE_ROUTES]
    try:
        m.apply_seismic_to_routes(routes_copy, FAKE_EARTHQUAKES)
    except Exception as e:
        dbg_warn("TEST", "phivolcs", f"apply_seismic_to_routes needs features module: {e}")

    dbg_step("TEST", "phivolcs", "Testing get_epicenter_map_js  with fake earthquakes")
    js = m.get_epicenter_map_js(FAKE_EARTHQUAKES)
    dbg_step("TEST", "phivolcs", f"JS output length: {len(js)} chars")

    dbg_step("TEST", "phivolcs", "Testing get_recent_earthquakes  (REAL network call to USGS)")
    try:
        m.get_recent_earthquakes(hours_back=12)
    except Exception as e:
        dbg_warn("TEST", "phivolcs", f"Network call failed (expected offline): {e}")


# ── safe_spots ────────────────────────────────────────────────────────────────

def test_safe_spots(mods):
    _section("safe_spots.py")
    m = mods.get("safe_spots")
    if not m: print(f"{YELLOW}safe_spots not loaded — skipping{RESET}"); return

    dbg_step("TEST", "safe_spots", "Testing get_flat_route_coords  with coords")
    m.get_flat_route_coords(FAKE_ROUTE)

    dbg_step("TEST", "safe_spots", "Testing get_flat_route_coords  with segments")
    route_with_segs = {
        "segments": [
            {"coords": [[14.5995, 120.9842], [14.6020, 120.9860]]},
            {"coords": [[14.6020, 120.9860], [14.6050, 120.9890]]},
        ]
    }
    m.get_flat_route_coords(route_with_segs)

    dbg_step("TEST", "safe_spots", "Testing get_safe_spots_js  with fake spots")
    fake_spots = [
        {
            "id": "1", "name": "Quezon City Police Station",
            "type": "police", "label": "Police Station",
            "icon": "👮", "color": "#2980b9",
            "lat": 14.6042, "lon": 121.0002,
            "address": "Example St, QC", "priority": 1,
            "dist_m": 250, "open_24h": True,
        },
        {
            "id": "2", "name": "Philippine General Hospital",
            "type": "hospital", "label": "Hospital",
            "icon": "🏥", "color": "#e74c3c",
            "lat": 14.5768, "lon": 120.9838,
            "address": "Taft Ave, Manila", "priority": 1,
            "dist_m": 800, "open_24h": True,
        },
    ]
    js = m.get_safe_spots_js(fake_spots)
    dbg_step("TEST", "safe_spots", f"JS output: {len(js)} chars")

    dbg_step("TEST", "safe_spots", "Testing get_safe_spots_js  empty list")
    m.get_safe_spots_js([])

    dbg_step("TEST", "safe_spots",
             "Testing get_safe_spots_near  (REAL Overpass API call — may be slow)")
    try:
        m.get_safe_spots_near(14.5995, 120.9842, radius_m=500)
    except Exception as e:
        dbg_warn("TEST", "safe_spots", f"Network call failed (expected offline): {e}")


# ── vulnerable_profiles ───────────────────────────────────────────────────────

def test_vulnerable_profiles(mods):
    _section("vulnerable_profiles.py")
    m = mods.get("vuln_profiles")
    if not m: print(f"{YELLOW}vulnerable_profiles not loaded — skipping{RESET}"); return

    for profile in ("senior", "pwd", "women", "child"):
        dbg_step("TEST", "vuln_profiles",
                 f"Testing get_profile_penalty  profile={profile}")
        m.get_profile_penalty(profile, FAKE_ROUTE, FAKE_WEATHER_RAIN)

        dbg_step("TEST", "vuln_profiles",
                 f"Testing get_profile_warnings  profile={profile}")
        m.get_profile_warnings(profile, FAKE_ROUTE, FAKE_WEATHER_RAIN)

        dbg_step("TEST", "vuln_profiles",
                 f"Testing get_profile_badge_html  profile={profile}")
        m.get_profile_badge_html(profile)

    dbg_step("TEST", "vuln_profiles", "Testing invalid profile  (should warn + return 0)")
    m.get_profile_penalty("alien", FAKE_ROUTE, None)
    m.get_profile_badge_html("alien")

    dbg_step("TEST", "vuln_profiles",
             "Testing apply_vulnerable_profile_to_routes  women + rain")
    routes_copy = [dict(r) for r in FAKE_ROUTES]
    try:
        m.apply_vulnerable_profile_to_routes(routes_copy, "women", FAKE_WEATHER_RAIN)
    except Exception as e:
        dbg_warn("TEST", "vuln_profiles",
                 f"apply_vulnerable_profile_to_routes needs features: {e}")

    dbg_step("TEST", "vuln_profiles",
             "Testing get_infrastructure_warnings  senior (REAL Overpass API call)")
    try:
        m.get_infrastructure_warnings("senior", FAKE_ROUTE["coords"])
    except Exception as e:
        dbg_warn("TEST", "vuln_profiles", f"Network call failed (expected offline): {e}")


# ── features ──────────────────────────────────────────────────────────────────

def test_features(mods):
    _section("features.py")
    m = mods.get("features")
    if not m: print(f"{YELLOW}features not loaded — skipping{RESET}"); return

    dbg_step("TEST", "features", "Testing get_score_color  across range")
    for score in (95, 70, 55, 42, 25):
        m.get_score_color(score)

    dbg_step("TEST", "features", "Testing get_score_label  across range")
    for score in (95, 70, 55, 42, 25):
        m.get_score_label(score)

    dbg_step("TEST", "features", "Testing is_nighttime  current time")
    m.is_nighttime()

    dbg_step("TEST", "features", "Testing get_night_warning  walk")
    m.get_night_warning("walk")

    dbg_step("TEST", "features", "Testing get_night_safety_penalty  motorcycle")
    m.get_night_safety_penalty("motorcycle")

    dbg_step("TEST", "features", "Testing estimate_fare  commute 8km")
    m.estimate_fare("commute", 8.0)

    dbg_step("TEST", "features", "Testing estimate_fare  walk 3km  (should be free)")
    m.estimate_fare("walk", 3.0)

    dbg_step("TEST", "features", "Testing apply_penalty_to_route  12.5 pts")
    r = dict(FAKE_ROUTE)
    m.apply_penalty_to_route(r, 12.5, "walk")

    dbg_step("TEST", "features", "Testing rank_routes  3 routes")
    routes_copy = [dict(r) for r in FAKE_ROUTES]
    m.rank_routes(routes_copy, "walk")

    dbg_step("TEST", "features", "Testing enrich_routes_with_scores")
    routes_copy = [dict(r) for r in FAKE_ROUTES]
    m.enrich_routes_with_scores(routes_copy, "commute")

    dbg_step("TEST", "features", "Testing apply_night_safety")
    routes_copy = [dict(r) for r in FAKE_ROUTES]
    m.apply_night_safety(routes_copy, "walk")

    dbg_step("TEST", "features",
             "Testing get_typhoon_signal  (REAL network call to PAGASA)")
    try:
        m.get_typhoon_signal()
    except Exception as e:
        dbg_warn("TEST", "features", f"Network call failed (expected offline): {e}")


# ── noah ──────────────────────────────────────────────────────────────────────

def test_noah(mods):
    _section("noah.py")
    m = mods.get("noah")
    if not m: print(f"{YELLOW}noah not loaded — skipping{RESET}"); return

    dbg_step("TEST", "noah",
             "Testing get_flood_risk_at  (REAL Mapbox/NOAH API call)")
    try:
        m.get_flood_risk_at(14.5995, 120.9842)
    except Exception as e:
        dbg_warn("TEST", "noah", f"Network call failed (expected offline): {e}")

    dbg_step("TEST", "noah", "Testing get_flood_warning_html  with rain active")
    fake_flood = {
        "ok": True, "risk_level": "moderate",
        "depth_m": 0.8, "label": "Moderate flood risk (knee-deep)",
        "color": "#1565c0", "penalty": 25, "error": None,
    }
    m.get_flood_warning_html(fake_flood, FAKE_WEATHER_RAIN, "Quezon City")

    dbg_step("TEST", "noah", "Testing get_flood_warning_html  no rain  (should return empty)")
    m.get_flood_warning_html(fake_flood, FAKE_WEATHER_CLEAR, "Quezon City")

    dbg_step("TEST", "noah", "Testing format_flood_zones_for_map")
    fake_points = [
        {"lat": 14.60, "lon": 121.00, "risk": "moderate",
         "label": "Moderate flood", "penalty": 25, "rain_active": True},
        {"lat": 14.61, "lon": 121.01, "risk": "low",
         "label": "Low flood", "penalty": 10, "rain_active": False},
    ]
    m.format_flood_zones_for_map(fake_points)


# ── community_reports ─────────────────────────────────────────────────────────

def test_community_reports(mods):
    _section("community_reports.py")
    m = mods.get("community_reports")
    if not m: print(f"{YELLOW}community_reports not loaded — skipping{RESET}"); return

    dbg_step("TEST", "community_reports",
             "Testing get_report_type_options_for_api")
    try:
        m.get_report_type_options_for_api()
    except Exception as e:
        dbg_warn("TEST", "community_reports", str(e))

    dbg_step("TEST", "community_reports",
             "Testing _calc_penalty_from_reports  with fake reports")
    fake_reports = [
        {
            "id": 1, "report_type": "flooding", "confirmations": 3,
            "verified": True, "lat": 14.60, "lon": 121.00,
            "category": "hazard",
        },
        {
            "id": 2, "report_type": "crime", "confirmations": 1,
            "verified": False, "lat": 14.61, "lon": 121.01,
            "category": "safety",
        },
    ]
    try:
        m._calc_penalty_from_reports(fake_reports)
    except Exception as e:
        dbg_warn("TEST", "community_reports", str(e))

    dbg_step("TEST", "community_reports",
             "Testing _report_hits_route  flooding near Manila route")
    try:
        waypoints = [(14.5995, 120.9842), (14.6020, 120.9860), (14.6050, 120.9890)]
        m._report_hits_route(14.600, 120.985, "flooding", waypoints)
    except Exception as e:
        dbg_warn("TEST", "community_reports", str(e))

    dbg_step("TEST", "community_reports", "Testing get_report_panel_html")
    try:
        html = m.get_report_panel_html()
        dbg_step("TEST", "community_reports", f"Panel HTML: {len(html)} chars")
    except Exception as e:
        dbg_warn("TEST", "community_reports", str(e))


# ── crime_data ────────────────────────────────────────────────────────────────

def test_crime_data(mods):
    _section("crime_data.py")
    m = mods.get("crime_data")
    if not m: print(f"{YELLOW}crime_data not loaded — skipping{RESET}"); return

    dbg_step("TEST", "crime_data",
             "Testing _static_crime_lookup  Quiapo Manila")
    try:
        m._static_crime_lookup("Quiapo, Manila")
    except Exception as e:
        dbg_warn("TEST", "crime_data", str(e))

    dbg_step("TEST", "crime_data",
             "Testing _coord_zone_lookup  Quiapo coords")
    try:
        m._coord_zone_lookup(14.5980, 120.9840)
    except Exception as e:
        dbg_warn("TEST", "crime_data", str(e))

    dbg_step("TEST", "crime_data",
             "Testing scan_route_crime_zones  with route coords")
    try:
        m.scan_route_crime_zones(FAKE_ROUTE["coords"])
    except Exception as e:
        dbg_warn("TEST", "crime_data", str(e))

    dbg_step("TEST", "crime_data",
             "Testing get_crime_warning  high risk + walk")
    try:
        fake_crime = {
            "ok": True, "risk_level": "high",
            "area": "Quiapo, Manila",
            "label": "High crime risk",
            "color": "#e74c3c", "penalty": 10,
        }
        m.get_crime_warning(fake_crime, "walk")
    except Exception as e:
        dbg_warn("TEST", "crime_data", str(e))

    dbg_step("TEST", "crime_data",
             "Testing get_crime_risk_for_area  (may hit LLM / cache)")
    try:
        m.get_crime_risk_for_area(14.5980, 120.9840, "Quiapo")
    except Exception as e:
        dbg_warn("TEST", "crime_data",
                 f"get_crime_risk_for_area failed (LLM/network): {e}")


# ── incidents ─────────────────────────────────────────────────────────────────

def test_incidents(mods):
    _section("incidents.py")
    m = mods.get("incidents")
    if not m: print(f"{YELLOW}incidents not loaded — skipping{RESET}"); return

    dbg_step("TEST", "incidents", "Testing get_incidents_map_data  with fake incidents")
    fake_incidents = [
        {
            "id": "test_1", "type": "flood", "title": "Flood on EDSA",
            "description": "Waist-deep flooding reported",
            "lat": 14.6100, "lon": 121.0000,
            "radius_m": 800, "severity": "high",
            "color": "#e74c3c", "source": "TEST",
            "source_url": "https://example.com",
            "reported_at": "2025-07-10 10:00 PHT",
        },
    ]
    m.get_incidents_map_data(fake_incidents)

    dbg_step("TEST", "incidents", "Testing apply_incidents_to_routes  with fake data")
    routes_copy = [dict(r) for r in FAKE_ROUTES]
    try:
        m.apply_incidents_to_routes(
            routes_copy, fake_incidents,
            14.5995, 120.9842, 14.6100, 121.0000
        )
    except Exception as e:
        dbg_warn("TEST", "incidents", str(e))

    dbg_step("TEST", "incidents",
             "Testing get_active_incidents  (REAL network — RSS feeds)")
    try:
        m.get_active_incidents(ph_only=True)
    except Exception as e:
        dbg_warn("TEST", "incidents",
                 f"Network call failed (expected offline): {e}")


# ── mmda ──────────────────────────────────────────────────────────────────────

def test_mmda(mods):
    _section("mmda.py")
    m = mods.get("mmda")
    if not m: print(f"{YELLOW}mmda not loaded — skipping{RESET}"); return

    dbg_step("TEST", "mmda", "Testing get_number_coding  Monday plate 1")
    from datetime import datetime
    mon_9am = datetime(2025, 7, 7, 9, 0, tzinfo=timezone(timedelta(hours=8)))
    m.get_number_coding(1, dt=mon_9am)

    dbg_step("TEST", "mmda", "Testing get_number_coding  Saturday  (no coding)")
    sat_9am = datetime(2025, 7, 12, 9, 0, tzinfo=timezone(timedelta(hours=8)))
    m.get_number_coding(5, dt=sat_9am)

    dbg_step("TEST", "mmda", "Testing get_number_coding  Monday plate 3  (not coded)")
    m.get_number_coding(3, dt=mon_9am)

    dbg_step("TEST", "mmda", "Testing apply_mmda_to_routes  plate_last_digit=1 on Monday")
    routes_copy = [dict(r) for r in FAKE_ROUTES]
    for r in routes_copy:
        r["commuter_type"] = "car"
    try:
        m.apply_mmda_to_routes(routes_copy, plate_last_digit=1)
    except Exception as e:
        dbg_warn("TEST", "mmda", str(e))

    dbg_step("TEST", "mmda",
             "Testing get_road_closures  (REAL Overpass/GDACS network call)")
    try:
        m.get_road_closures()
    except Exception as e:
        dbg_warn("TEST", "mmda",
                 f"Network call failed (expected offline): {e}")


# ── network_utils ─────────────────────────────────────────────────────────────

def test_network_utils(mods):
    _section("network_utils.py")
    m = mods.get("network_utils")
    if not m: print(f"{YELLOW}network_utils not loaded — skipping{RESET}"); return

    dbg_step("TEST", "network_utils", "Testing is_network_error  DNS failure")
    m.is_network_error(Exception("getaddrinfo failed"))

    dbg_step("TEST", "network_utils", "Testing is_network_error  normal error")
    m.is_network_error(ValueError("some other error"))

    dbg_step("TEST", "network_utils",
             "Testing safe_get  (REAL network call to Open-Meteo)")
    try:
        m.safe_get("https://api.open-meteo.com/v1/forecast",
                   params={"latitude": 14.5995, "longitude": 120.9842,
                            "current": "weather_code", "forecast_days": 1})
    except Exception as e:
        dbg_warn("TEST", "network_utils",
                 f"Network call failed (expected offline): {e}")


# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

def print_summary():
    print(f"\n{BOLD}{'═'*60}{RESET}")
    print(f"{BOLD}  FINAL SUMMARY{RESET}")
    print(f"{BOLD}{'═'*60}{RESET}")

    total_calls  = sum(1 for l in _LOG if ">>>ENTER" in l)
    total_exits  = sum(1 for l in _LOG if "<<<EXIT"  in l)
    total_errors = len(_ERRORS)
    cache_hits   = sum(1 for l in _LOG if "💾 HIT"   in l)
    cache_misses = sum(1 for l in _LOG if "💾 MISS"  in l)
    warnings     = sum(1 for l in _LOG if "WARN"     in l)

    print(f"  {GREEN}✓{RESET} Function calls tracked : {BOLD}{total_calls}{RESET}")
    print(f"  {GREEN}✓{RESET} Clean exits            : {BOLD}{total_exits}{RESET}")
    print(f"  {'💾'} Cache hits / misses     : {GREEN}{cache_hits}{RESET} / {YELLOW}{cache_misses}{RESET}")
    print(f"  {'⚠'} Warnings               : {YELLOW}{warnings}{RESET}")

    if _ERRORS:
        print(f"\n  {RED}{BOLD}✗ Errors ({len(_ERRORS)}){RESET}")
        for e in _ERRORS:
            print(f"    {RED}• {e}{RESET}")
    else:
        print(f"\n  {GREEN}{BOLD}✓ No errors{RESET}")

    print(f"{BOLD}{'═'*60}{RESET}\n")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Make sure risk_monitor is importable from wherever this script lives
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    mods = load_and_patch()

    test_weather(mods)
    test_phivolcs(mods)
    test_safe_spots(mods)
    test_vulnerable_profiles(mods)
    test_features(mods)
    test_noah(mods)
    test_community_reports(mods)
    test_crime_data(mods)
    test_incidents(mods)
    test_mmda(mods)
    test_network_utils(mods)

    print_summary()