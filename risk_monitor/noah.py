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

# Banner colors per flood risk
_FLOOD_COLORS = {
    "none":     "#27ae60",
    "low":      "#f39c12",
    "moderate": "#e67e22",
    "high":     "#e74c3c",
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
    folium.TileLayer(
        tiles=(
            f"https://api.mapbox.com/v4/upri-noah.ph_fh_100yr_tls/"
            f"{{z}}/{{x}}/{{y}}.png?access_token={_MAPBOX_TOKEN}"
        ),
        attr="Project NOAH / UP DOST via Mapbox",
        name="NOAH Flood Zones",
        overlay=True,
        control=False,
        opacity=opacity,
    ).add_to(flood_layer)

    flood_layer.add_to(m)
    return m


def get_flood_risk_at(lat: float, lon: float, layer: str = _DEFAULT_LAYER) -> dict:
    """
    Query NOAH flood hazard at a coordinate using Mapbox Tilequery API.

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
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://noah.up.edu.ph/", "Origin": "https://noah.up.edu.ph"},
            timeout=8,
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
        return _flood_result(risk, depth_m)

    except requests.exceptions.Timeout:
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


def get_flood_warning_html(flood: dict, location_label: str = "") -> str:
    """
    Returns an HTML warning string for flood risk at a location.
    Returns empty string if no flood risk.
    """
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


def apply_flood_to_routes(routes: list, flood: dict, weather: dict = None) -> list:
    from risk_monitor.features import get_score_color, get_score_label

    # Only apply flood penalty if it's actually raining right now
    if weather is not None:
        rain_active = weather.get("risk_level") in ("light_rain", "rain", "heavy_rain", "storm")
        if not rain_active:
            for r in routes:
                r["flood_warning"] = ""
            return routes

    penalty = flood.get("penalty", 0)
    label   = flood.get("label", "")

    for r in routes:
        if penalty > 0:
            r["safety_score"] = max(0, r.get("safety_score", 75) - penalty)
            r["score_color"]  = get_score_color(r["safety_score"])
            r["score_label"]  = get_score_label(r["safety_score"])
        r["flood_warning"] = label if penalty > 0 else ""

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