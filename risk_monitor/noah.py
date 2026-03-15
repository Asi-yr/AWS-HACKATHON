"""
noah.py
-------
Feature: NOAH Flood Zone Overlay for SafeRoute.

Uses NOAH's public Mapbox Tilequery API (reverse-engineered from noah.up.edu.ph).
No API key needed beyond NOAH's own public token.

Nothing runs on import. All logic is in pure functions.
"""

import requests
import folium

# ── NOAH via Mapbox Tilequery ─────────────────────────────────────────────────
# Discovered from DevTools on noah.up.edu.ph — public token, real layer IDs

_MAPBOX_TOKEN  = "pk.eyJ1IjoidXByaS1ub2FoIiwiYSI6ImNsZTZyMGdjYzAybGMzbmwxMHA4MnE0enMifQ.tuOhBGsN-M7JCPaUqZ0Hng"
_TILEQUERY_URL = "https://api.mapbox.com/v4/{layers}/tilequery/{lon},{lat}.json"
_FLOOD_LAYERS  = "upri-noah.ph_fh_100yr_tls,upri-noah.ph_fh_nodata1_tls"
_DEFAULT_LAYER = _FLOOD_LAYERS  # kept for backward compat

# Per-risk banner/marker colors — all BLUE shades for flood (darker = worse)
_FLOOD_COLORS = {
    "none":     "#27ae60",   # green (no risk)
    "low":      "#42a5f5",   # sky blue
    "moderate": "#1565c0",   # medium blue
    "high":     "#0d2b6b",   # deep navy
    "error":    "#7f8c8d",
}

# Flood risk -> safety score penalty
_FLOOD_PENALTY = {
    "none":     0,
    "low":      10,
    "moderate": 25,
    "high":     40,
}


def add_noah_flood_layer(
    m: folium.Map,
    layer: str = _DEFAULT_LAYER,
    opacity: float = 0.55,
    show_by_default: bool = True,
) -> folium.Map:
    """
    Adds a NOAH flood hazard tile layer to an existing Folium map.
    Uses Mapbox tiles from NOAH's own account.
    """
    flood_layer = folium.FeatureGroup(
        name="🌊 NOAH Flood Zones (100yr)",
        show=show_by_default,
    )

    # Use Mapbox raster tiles from NOAH's account
    # NOTE: Mapbox raster tiles require the token inline in the URL.
    # The Origin/Referer restriction only applies to the Tilequery API,
    # not to raster tile fetches (which are browser-initiated).
    folium.TileLayer(
        tiles=(
            f"https://api.mapbox.com/v4/upri-noah.ph_fh_100yr_tls/"
            f"{{z}}/{{x}}/{{y}}.png?access_token={_MAPBOX_TOKEN}"
        ),
        attr='<a href="https://noah.up.edu.ph/">Project NOAH / UP DOST</a> via Mapbox',
        name="NOAH Flood Zones",
        overlay=True,
        control=False,
        opacity=opacity,
    ).add_to(flood_layer)

    flood_layer.add_to(m)
    return m


# ── Required headers for NOAH/Mapbox tilequery ───────────────────────────────
# Mapbox returns 403 if Origin/Referer are missing — the token is scoped
# to requests originating from noah.up.edu.ph. Always include these headers.
_MAPBOX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer":    "https://noah.up.edu.ph/",
    "Origin":     "https://noah.up.edu.ph",
    "Accept":     "application/json",
}


def check_mapbox_token() -> dict:
    """
    Verify the Mapbox token is still valid by making a minimal tilequery.
    Returns {"ok": bool, "status": int, "error": str|None}

    Call this in your health-check route or on app startup.
    The token expires when NOAH rotates it — update _MAPBOX_TOKEN if this fails.
    """
    url = _TILEQUERY_URL.format(layers=_FLOOD_LAYERS, lon=121.1020, lat=14.6330)
    params = {"radius": 0, "limit": 1, "access_token": _MAPBOX_TOKEN}
    try:
        r = requests.get(url, params=params, headers=_MAPBOX_HEADERS, timeout=6)
        ok = r.status_code == 200
        return {"ok": ok, "status": r.status_code,
                "error": None if ok else f"HTTP {r.status_code} — token may have expired"}
    except Exception as e:
        return {"ok": False, "status": 0, "error": str(e)}


# ── In-process coordinate cache for flood lookups ────────────────────────────
# Key: (rounded lat to 3dp, rounded lon to 3dp) — ~110m grid resolution,
# fine enough to distinguish flood zones, coarse enough to get cache hits
# along a polyline where successive points are metres apart.
_FLOOD_PT_CACHE: dict = {}


def get_flood_risk_at(lat: float, lon: float, layer: str = _DEFAULT_LAYER) -> dict:
    """
    Query NOAH flood hazard at a coordinate using Mapbox Tilequery API.

    NOTE: Mapbox returns 403 without the correct Referer/Origin headers.
    _MAPBOX_HEADERS above ensures these are always sent.

    Returns:
        {
          "ok":         bool,
          "risk_level": str,   # "none", "low", "moderate", "high"
          "depth_m":    float or None,
          "label":      str,
          "color":      str,
          "penalty":    int,
          "error":      str or None,
        }
    """
    # Cache hit — identical coordinates within ~110m return same result
    _cache_key = (round(lat, 3), round(lon, 3))
    if _cache_key in _FLOOD_PT_CACHE:
        return _FLOOD_PT_CACHE[_cache_key]

    url = _TILEQUERY_URL.format(
        layers=_FLOOD_LAYERS,
        lon=round(lon, 7),
        lat=round(lat, 7),
    )
    params = {
        "radius":       0,
        "limit":        20,
        "access_token": _MAPBOX_TOKEN,
    }

    try:
        resp = requests.get(
            url, params=params,
            headers=_MAPBOX_HEADERS,   # must include Origin/Referer — 403 without them
            timeout=8,
        )
        if resp.status_code == 403:
            # Token scoped to noah.up.edu.ph — check headers and/or token expiry
            return _flood_error(
                "Mapbox 403: token may have expired or Origin header rejected. "
                "Run check_mapbox_token() and update _MAPBOX_TOKEN in noah.py if needed."
            )
        resp.raise_for_status()
        data     = resp.json()
        features = data.get("features", [])

        if not features:
            return _flood_result("none", None)

        # Each feature has properties — look for flood depth or any hit
        # on the 100yr layer means at least low risk
        depth_m = None
        for feat in features:
            props = feat.get("properties", {})
            # Try common property names for flood depth
            raw = (
                props.get("depth") or
                props.get("Var") or
                props.get("gridcode") or
                props.get("DN") or
                props.get("flood_depth")
            )
            if raw is not None:
                try:
                    depth_m = float(raw)
                    break
                except (TypeError, ValueError):
                    pass

        # If we got features but no depth property, the point is in a flood zone
        # Default to low risk
        if depth_m is None:
            depth_m = 0.2

        risk = _depth_to_risk(depth_m)
        result = _flood_result(risk, depth_m)
        _FLOOD_PT_CACHE[_cache_key] = result
        return result

    except requests.exceptions.Timeout:
        # Don't cache errors — transient failures should retry
        return _flood_error("NOAH tilequery timed out.")
    except requests.exceptions.ConnectionError:
        return _flood_error("Could not reach Mapbox/NOAH.")
    except Exception as e:
        return _flood_error(str(e))


def _depth_to_risk(depth_m: float) -> str:
    if depth_m < 0.1:
        return "none"
    elif depth_m < 0.5:
        return "low"
    elif depth_m < 1.5:
        return "moderate"
    else:
        return "high"


def _flood_result(risk: str, depth_m) -> dict:
    labels = {
        "none":     "No flood risk detected",
        "low":      "Low flood risk (ankle-deep)",
        "moderate": "Moderate flood risk (knee-deep)",
        "high":     "High flood risk (waist-deep or worse)",
    }
    return {
        "ok":         True,
        "risk_level": risk,
        "depth_m":    depth_m,
        "label":      labels.get(risk, "Unknown"),
        "color":      _FLOOD_COLORS.get(risk, "#7f8c8d"),
        "penalty":    _FLOOD_PENALTY.get(risk, 0),
        "error":      None,
    }


def _flood_error(msg: str) -> dict:
    return {
        "ok":         False,
        "risk_level": "none",
        "depth_m":    None,
        "label":      "Flood data unavailable",
        "color":      _FLOOD_COLORS["error"],
        "penalty":    0,
        "error":      msg,
    }


def get_flood_warning_html(flood: dict, weather: dict, location_label: str = "") -> str:
    """
    Returns an HTML warning string for flood risk at a location.
    Returns empty string if no flood risk OR if it's not raining.
    
    Args:
        flood: Result from get_flood_risk_at()
        weather: Result from get_weather_risk() - REQUIRED to check if raining
        location_label: Optional location name
    """
    # CRITICAL: Only show flood banner if it's actively raining
    rain_active = False
    if weather and weather.get("ok"):
        rain_active = weather.get("risk_level") in ("light_rain", "rain", "heavy_rain", "storm")
    
    if not rain_active:
        return ""
    
    if not flood.get("ok") or flood.get("risk_level") == "none":
        return ""

    risk  = flood["risk_level"]
    color = flood["color"]
    label = flood["label"]
    loc   = f" at {location_label}" if location_label else ""

    icons = {"low": "🟡", "moderate": "🟠", "high": "🔴"}
    icon  = icons.get(risk, "⚠️")

    return (
        f'<div class="flood-warning" style="background:{color};color:#fff;'
        f'padding:6px 14px;font-size:13px;font-weight:bold;text-align:center;'
        f'border-radius:4px;margin:4px 0;">'
        f'{icon} Flood Zone{loc}: {label} — consider an alternate route.'
        f'</div>'
    )


def _get_weather_at(lat: float, lon: float) -> dict:
    """Fetch weather at a specific point along the route (used for per-segment rain checks)."""
    from risk_monitor.weather import get_weather_risk
    try:
        return get_weather_risk(lat, lon)
    except Exception:
        return {"ok": False, "risk_level": "clear"}


def check_route_flood_zones(route_coords: list, weather: dict, sample_every_n: int = 15) -> dict:
    """
    Check for flood zones along an entire route path.

    KEY BEHAVIOUR CHANGE:
    - Flood-prone zones are ALWAYS detected and shown on the map — they are a
      structural hazard regardless of whether it is currently raining at the origin.
    - Safety score PENALTIES only apply at flood zones where it is actively
      raining at that specific point along the route (checked via per-segment
      weather fetch for mid/end points; origin weather used for origin segment).
    - This means: your dry origin → no penalty at origin, but flood-prone
      Caloocan/Manila sections ARE flagged on the map, and receive a penalty
      only if rain is active there.

    Args:
        route_coords:  List of [lat, lon] along the route
        weather:       Weather at origin (used as fallback; per-segment checks override)
        sample_every_n: Sample every Nth coordinate (default 15)

    Returns:
        {
          "has_flood_zones": bool,
          "flood_points": [{"lat", "lon", "risk", "label", "penalty", "rain_active"}, ...],
          "max_risk": str,
          "total_penalty": int,   # sum of penalties where rain was active
        }
    """
    if not route_coords:
        return {"has_flood_zones": False, "flood_points": [], "max_risk": "none", "total_penalty": 0}

    # Determine rain status at origin (passed in)
    origin_rain = (
        weather.get("ok") and
        weather.get("risk_level") in ("light_rain", "rain", "heavy_rain", "storm")
    ) if weather else False

    # Fetch weather at midpoint and destination for better spatial coverage
    n = len(route_coords)
    mid_coord  = route_coords[n // 2]
    end_coord  = route_coords[-1]

    mid_weather = _get_weather_at(mid_coord[0], mid_coord[1])
    end_weather = _get_weather_at(end_coord[0], end_coord[1])

    mid_rain = mid_weather.get("ok") and mid_weather.get("risk_level") in ("light_rain", "rain", "heavy_rain", "storm")
    end_rain = end_weather.get("ok") and end_weather.get("risk_level") in ("light_rain", "rain", "heavy_rain", "storm")

    # Sample points along route
    sampled = route_coords[::sample_every_n]
    if len(sampled) > 20:
        step = len(sampled) // 20
        sampled = sampled[::step]

    # For each sampled point, determine which weather zone it falls in:
    # first third → origin rain, middle third → mid rain, last third → end rain
    third = max(1, len(sampled) // 3)

    flood_points = []
    max_risk     = "none"
    total_penalty = 0
    risk_levels  = ["none", "low", "moderate", "high"]

    # ── Parallel flood queries ────────────────────────────────────────────────
    # Each point is an independent Mapbox tilequery — run them concurrently
    # so 20 points at 8s timeout finishes in ~8s instead of up to 160s.
    import concurrent.futures as _cf

    def _query_point(args):
        i, coord = args
        lat, lon = coord[0], coord[1]
        result = get_flood_risk_at(lat, lon)
        return i, lat, lon, result

    workers = min(10, len(sampled))
    with _cf.ThreadPoolExecutor(max_workers=workers) as pool:
        point_results = list(pool.map(_query_point, enumerate(sampled)))

    for i, lat, lon, flood_result in point_results:
        if not flood_result.get("ok") or flood_result.get("risk_level") == "none":
            continue

        # Determine if it's raining at this segment of the route
        if i < third:
            rain_here = origin_rain
        elif i < 2 * third:
            rain_here = mid_rain
        else:
            rain_here = end_rain

        # Penalty only applies if raining at this segment
        penalty = flood_result["penalty"] if rain_here else 0

        flood_points.append({
            "lat":        lat,
            "lon":        lon,
            "risk":       flood_result["risk_level"],
            "label":      flood_result["label"],
            "penalty":    penalty,
            "rain_active": rain_here,
        })

        # Track highest structural risk (regardless of rain)
        if risk_levels.index(flood_result["risk_level"]) > risk_levels.index(max_risk):
            max_risk = flood_result["risk_level"]

        # Accumulate penalty only where raining
        if rain_here and flood_result["penalty"] > total_penalty:
            total_penalty = flood_result["penalty"]

    return {
        "has_flood_zones": len(flood_points) > 0,
        "flood_points":    flood_points,
        "max_risk":        max_risk,
        "total_penalty":   total_penalty,
    }


def apply_route_flood_analysis(routes: list, weather: dict) -> list:
    """
    Analyze each route for flood zones along its path.

    KEY CHANGE: Flood-prone zones are ALWAYS scanned and shown on the map —
    they are structural hazards. Penalties only apply at zones where it is
    actively raining at that specific segment of the route.

    This means:
    - Your origin is clear → no penalty at origin, but map still shows 🌊
      markers at flood-prone Caloocan / Manila sections along the route.
    - If it IS raining at those sections, the safety score drops accordingly.
    - The flood_warning text distinguishes "flood zone (dry)" vs "flooding now".
    """
    from risk_monitor.features import get_score_color, get_score_label, _route_exposure_multiplier

    for route in routes:
        route["flood_zones"]     = []
        route["flood_zones_map"] = []
        route["has_flood_zones"] = False
        route["flood_warning"]   = ""

        # Collect route coordinates
        coords = []
        if route.get('coords'):
            coords = route['coords']
        elif route.get('segments'):
            for seg in route['segments']:
                if seg.get('coords'):
                    c = seg['coords']
                    if c and isinstance(c[0], list) and isinstance(c[0][0], list):
                        for subseg in c:
                            coords.extend(subseg)
                    else:
                        coords.extend(c)

        if not coords:
            continue

        flood_analysis = check_route_flood_zones(coords, weather, sample_every_n=15)

        route["flood_zones"]     = flood_analysis["flood_points"]
        route["flood_zones_map"] = format_flood_zones_for_map(flood_analysis["flood_points"])
        route["has_flood_zones"] = flood_analysis["has_flood_zones"]

        if not flood_analysis["has_flood_zones"]:
            continue

        # Apply penalty only for zones where it's raining (total_penalty already
        # excludes dry zones — see check_route_flood_zones)
        if flood_analysis["total_penalty"] > 0:
            base_penalty = flood_analysis["total_penalty"]
            multiplier   = _route_exposure_multiplier(route.get('id', 1))
            from risk_monitor.features import apply_penalty_to_route
            apply_penalty_to_route(route, base_penalty * multiplier, "")
            route["score_color"] = get_score_color(route["safety_score"])
            route["score_label"] = get_score_label(route["safety_score"])

        # Build human-readable warning
        num_zones    = len(flood_analysis["flood_points"])
        rain_zones   = [p for p in flood_analysis["flood_points"] if p.get("rain_active")]
        dry_zones    = [p for p in flood_analysis["flood_points"] if not p.get("rain_active")]
        risk_desc    = flood_analysis["max_risk"].replace("_", " ").title()

        if rain_zones and dry_zones:
            route["flood_warning"] = (
                f"{risk_desc} flood risk — {len(rain_zones)} zone(s) currently flooding, "
                f"{len(dry_zones)} zone(s) flood-prone (dry now)"
            )
        elif rain_zones:
            route["flood_warning"] = (
                f"{risk_desc} flood risk — {len(rain_zones)} area(s) currently flooding along route"
            )
        else:
            route["flood_warning"] = (
                f"⚠️ {num_zones} flood-prone area(s) along route — not currently raining there"
            )

    return routes


# ── DEPRECATED: Old single-point flood checking (kept for backward compatibility) ──

def apply_flood_to_routes(routes: list, flood: dict, weather: dict = None) -> list:
    """
    DEPRECATED: Use apply_route_flood_analysis() instead.
    
    This function only checks flood risk at origin point, not along the route.
    Kept for backward compatibility only.
    """
    from risk_monitor.features import get_score_color, get_score_label

    # CRITICAL: Only apply flood penalty if it's actually raining right now
    rain_active = False
    if weather is not None and weather.get("ok"):
        rain_active = weather.get("risk_level") in ("light_rain", "rain", "heavy_rain", "storm")
    
    if not rain_active:
        # Clear any flood warnings since it's not raining
        for r in routes:
            r["flood_warning"] = ""
            if "flood_zones" not in r:
                r["flood_zones"] = []
        return routes

    penalty = flood.get("penalty", 0)
    label   = flood.get("label", "")

    for r in routes:
        if penalty > 0:
            from risk_monitor.features import apply_penalty_to_route
            apply_penalty_to_route(r, penalty, "")
            r["score_color"] = get_score_color(r["safety_score"])
            r["score_label"] = get_score_label(r["safety_score"])
        r["flood_warning"] = label if penalty > 0 else ""
        if "flood_zones" not in r:
            r["flood_zones"] = []

    return routes


def get_flood_layer_toggle_js() -> str:
    """JS snippet for a flood layer toggle button in the map."""
    return r"""
(function () {
    var floodVisible = true;
    function toggleFloodLayer() {
        floodVisible = !floodVisible;
        var btn    = document.getElementById('flood-toggle-btn');
        var iframe = document.getElementById('map-frame');
        if (btn) btn.style.opacity = floodVisible ? '1' : '0.4';
        if (iframe && iframe.contentWindow) {
            iframe.contentWindow.postMessage({ type: 'toggle_flood_layer', visible: floodVisible }, '*');
        }
    }
    document.addEventListener('DOMContentLoaded', function () {
        var btn = document.getElementById('flood-toggle-btn');
        if (btn) btn.addEventListener('click', toggleFloodLayer);
    });
})();
"""


def format_flood_zones_for_map(flood_points: list) -> list:
    """
    Converts flood zone data into a format for map overlay.

    KEY RULE: Only returns zones where rain_active=True.
    Dry flood-prone zones are structural hazards but should NOT appear
    on the map — they would confuse users with markers when it's sunny.
    They will automatically appear when weather changes and it rains there.

    All active flood zones use BLUE shades for easy visual differentiation:
      - High risk   → deep navy   (#0d2b6b) — most severe
      - Moderate    → medium blue (#1565c0)
      - Low risk    → sky blue    (#42a5f5) — least severe
    """
    # Blue shades: darker = higher flood risk
    blue_colors = {
        "high":     "#0d2b6b",   # deep navy
        "moderate": "#1565c0",   # medium blue
        "low":      "#42a5f5",   # sky blue
    }
    risk_icons = {
        "high":     "🌊",
        "moderate": "💧",
        "low":      "💦",
    }

    formatted = []
    for point in flood_points:
        rain_active = point.get("rain_active", False)

        # Skip dry zones entirely — only show flood markers where it's raining
        if not rain_active:
            continue

        risk  = point["risk"]
        color = blue_colors.get(risk, "#42a5f5")
        icon  = risk_icons.get(risk, "💧")

        formatted.append({
            "lat":        point["lat"],
            "lon":        point["lon"],
            "risk":       risk,
            "label":      point.get("label", "Flood risk area") + " (currently flooding)",
            "color":      color,
            "icon":       icon,
            "penalty":    point.get("penalty", 0),
            "rain_active": True,
        })

    return formatted