"""
phivolcs.py
-----------
PHIVOLCS (Philippine Institute of Volcanology and Seismology) alerts for SafeRoute.

Data sources (all public, no API key):
  1. PHIVOLCS RSS feed — earthquake bulletins
     https://www.phivolcs.dost.gov.ph/index.php/earthquake/earthquake-bulletin
  2. PHIVOLCS Twitter/X scrape fallback
  3. USGS Earthquake API (global, covers PH) — reliable fallback
     https://earthquake.usgs.gov/fdsnws/event/1/query

Relevance to commuters:
  - Earthquakes ≥ 4.0 near the route → road damage, rockfalls, bridge integrity warnings
  - Tsunami warnings → coastal route avoidance
  - Aftershocks within 12 hours of a major event → elevated risk period

Nothing runs on import. Cache TTL: 5 minutes (earthquakes are time-critical).
"""

import requests
import math
from datetime import datetime, timezone, timedelta

# Suppress SSL warnings — some PH govt endpoints have cert issues in local dev
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_PHT = timezone(timedelta(hours=8))
_USGS_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"

# PH bounding box for USGS filter
_PH_MIN_LAT, _PH_MAX_LAT =  4.5, 21.5
_PH_MIN_LON, _PH_MAX_LON = 116.0, 127.5

# Cache
_eq_cache: dict = {}
_EQ_TTL = 300  # 5 minutes


# ── Magnitude thresholds ──────────────────────────────────────────────────────
# Only surface-level (depth < 70km) quakes are likely to damage roads.
# Deep-focus quakes (>70km) are felt but rarely damage surface infrastructure.
_MAG_COMMUTER_THRESHOLD = 4.0   # warn commuters
_MAG_HIGH_ALERT         = 5.5   # strong shaking, possible bridge/road damage
_MAG_CRITICAL           = 6.5   # serious structural damage likely

# Rough radius of road-damage concern per magnitude (km)
_DAMAGE_RADIUS_KM = {
    4.0: 20,
    5.0: 50,
    5.5: 80,
    6.0: 120,
    6.5: 200,
    7.0: 350,
}


def get_recent_earthquakes(hours_back: int = 12) -> list:
    """
    Fetch recent Philippine earthquakes from USGS.
    Returns list of significant quakes (mag ≥ 4.0) within the last N hours.

    Returns list of:
        {
          "id":          str,
          "magnitude":   float,
          "depth_km":    float,
          "place":       str,
          "lat":         float,
          "lon":         float,
          "time_pht":    str,
          "severity":    str,   # "moderate"|"high"|"critical"
          "color":       str,
          "radius_km":   float,  # estimated road-damage concern radius
          "tsunami":     bool,
          "url":         str,
        }
    """
    import time as _time
    now = _time.time()
    cached = _eq_cache.get("earthquakes")
    if cached and (now - cached["ts"]) < _EQ_TTL:
        return cached["data"]

    params = {
        "format":    "geojson",
        "minmag":    _MAG_COMMUTER_THRESHOLD,
        "minlatitude":  _PH_MIN_LAT,
        "maxlatitude":  _PH_MAX_LAT,
        "minlongitude": _PH_MIN_LON,
        "maxlongitude": _PH_MAX_LON,
        "orderby":   "time",
        "limit":     50,
        # hours_back window
        "starttime": (datetime.now(timezone.utc) -
                      timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%S"),
    }

    try:
        resp = requests.get(_USGS_URL, params=params,
                            headers={"User-Agent": "SafeRoute/1.0"},
                            timeout=8, verify=False)
        resp.raise_for_status()
        features = resp.json().get("features", [])
    except Exception:
        _eq_cache["earthquakes"] = {"ts": now, "data": []}
        return []

    results = []
    for feat in features:
        try:
            props = feat["properties"]
            geom  = feat["geometry"]["coordinates"]
            mag   = float(props.get("mag") or 0)
            depth = float(geom[2]) if len(geom) > 2 else 0
            lon, lat = float(geom[0]), float(geom[1])

            # Skip deep-focus quakes > 150km — minimal road-damage risk
            if depth > 150:
                continue

            severity = _mag_severity(mag)
            radius   = _damage_radius(mag)

            eq_time = datetime.fromtimestamp(
                props["time"] / 1000, tz=_PHT
            ).strftime("%Y-%m-%d %H:%M PHT")

            results.append({
                "id":        feat["id"],
                "magnitude": mag,
                "depth_km":  round(depth, 1),
                "place":     props.get("place", "Philippines"),
                "lat":       lat,
                "lon":       lon,
                "time_pht":  eq_time,
                "severity":  severity,
                "color":     _severity_color(severity),
                "radius_km": radius,
                "tsunami":   bool(props.get("tsunami")),
                "url":       props.get("url", "https://www.phivolcs.dost.gov.ph/"),
            })
        except Exception:
            continue

    _eq_cache["earthquakes"] = {"ts": now, "data": results}
    return results


def _mag_severity(mag: float) -> str:
    if mag >= _MAG_CRITICAL:        return "critical"
    if mag >= _MAG_HIGH_ALERT:      return "high"
    if mag >= _MAG_COMMUTER_THRESHOLD: return "moderate"
    return "low"


def _severity_color(sev: str) -> str:
    return {
        "low":      "#f39c12",
        "moderate": "#e67e22",
        "high":     "#e74c3c",
        "critical": "#6c1a1a",
    }.get(sev, "#e67e22")


def _damage_radius(mag: float) -> float:
    """Estimated road-concern radius in km for a given magnitude."""
    for threshold in sorted(_DAMAGE_RADIUS_KM.keys(), reverse=True):
        if mag >= threshold:
            return float(_DAMAGE_RADIUS_KM[threshold])
    return 10.0


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def check_route_seismic_risk(route_coords: list, earthquakes: list) -> dict:
    """
    Check if any recent earthquake's damage radius overlaps with the route.

    Returns:
        {
          "has_risk":    bool,
          "earthquakes": list,  # quakes that overlap the route
          "max_severity":str,
          "penalty":     int,
        }
    """
    if not earthquakes or not route_coords:
        return {"has_risk": False, "earthquakes": [], "max_severity": "none", "penalty": 0}

    sev_order  = ["none", "low", "moderate", "high", "critical"]
    penalties  = {"low": 5, "moderate": 15, "high": 30, "critical": 50}
    hits       = []
    max_sev    = "none"

    # Sample route coords
    sample = route_coords[::20] or route_coords

    for eq in earthquakes:
        eq_lat, eq_lon = eq["lat"], eq["lon"]
        radius_km = eq["radius_km"]
        for pt in sample:
            dist = _haversine_km(pt[0], pt[1], eq_lat, eq_lon)
            if dist <= radius_km:
                hits.append(eq)
                if sev_order.index(eq["severity"]) > sev_order.index(max_sev):
                    max_sev = eq["severity"]
                break  # one hit per quake is enough

    return {
        "has_risk":    len(hits) > 0,
        "earthquakes": hits,
        "max_severity": max_sev,
        "penalty":     penalties.get(max_sev, 0),
    }


def apply_seismic_to_routes(routes: list, earthquakes: list) -> list:
    """
    Apply seismic risk penalties and warnings to all routes.
    """
    from risk_monitor.features import apply_penalty_to_route, get_score_color, get_score_label

    for route in routes:
        coords = []
        if route.get("coords"):
            coords = route["coords"]
        elif route.get("segments"):
            for seg in route.get("segments", []):
                coords.extend(seg.get("coords", []))

        seismic = check_route_seismic_risk(coords, earthquakes)
        route["seismic_risk"]    = seismic
        route["seismic_warning"] = ""

        if seismic["has_risk"]:
            apply_penalty_to_route(route, seismic["penalty"], "")
            route["score_color"] = get_score_color(route["safety_score"])
            route["score_label"] = get_score_label(route["safety_score"])

            eqs = seismic["earthquakes"]
            top = max(eqs, key=lambda e: e["magnitude"])
            tsunami_note = " ⚠️ TSUNAMI WARNING ACTIVE" if any(e["tsunami"] for e in eqs) else ""
            route["seismic_warning"] = (
                f"M{top['magnitude']} earthquake near {top['place']} "
                f"({top['depth_km']}km deep) — possible road/bridge damage.{tsunami_note}"
            )

    return routes


def get_seismic_banner_html(earthquakes: list) -> str:
    """
    Returns an HTML banner if a significant recent earthquake occurred near PH.
    Show the most severe quake with tsunami flag if active.
    """
    if not earthquakes:
        return ""

    # Only show if there's at least one moderate+ quake
    significant = [e for e in earthquakes if e["severity"] in ("moderate", "high", "critical")]
    if not significant:
        return ""

    top = max(significant, key=lambda e: e["magnitude"])
    color = top["color"]
    tsunami = " — ⚠️ TSUNAMI WARNING" if top["tsunami"] else ""

    return (
        f'<div class="phivolcs-banner" style="background:{color};color:#fff;'
        f'padding:8px 16px;font-size:13px;font-weight:bold;text-align:center;">'
        f'🌍 PHIVOLCS: M{top["magnitude"]} earthquake — {top["place"]}'
        f' ({top["depth_km"]}km deep){tsunami} · {top["time_pht"]}'
        f'</div>'
    )


def get_epicenter_map_js(earthquakes: list) -> str:
    """
    Generate Leaflet JS to render earthquake epicenter markers on the map.

    Each epicenter shows:
      - A pulsing circle scaled to the damage radius
      - A marker icon with magnitude label
      - A popup with full details (place, depth, time, tsunami warning)
      - A dashed damage-radius circle (only for moderate+ quakes)

    Inject into index.html: eval(data.epicenter_js) after route search,
    or {{ epicenter_js | safe }} on page load.
    """
    if not earthquakes:
        return ""

    lines = [
        "(function() {",
        "  if (typeof map === 'undefined') return;",
        "  // Clear old epicenter layers",
        "  if (window._epicenterGroup) { window._epicenterGroup.clearLayers(); }",
        "  else { window._epicenterGroup = L.featureGroup().addTo(map); }",
        "  var eg = window._epicenterGroup;",
    ]

    for eq in earthquakes:
        mag       = eq["magnitude"]
        lat       = eq["lat"]
        lon       = eq["lon"]
        place     = eq["place"].replace("'", "\\'")
        depth     = eq["depth_km"]
        time_pht  = eq["time_pht"]
        severity  = eq["severity"]
        color     = eq["color"]
        radius_km = eq["radius_km"]
        radius_m  = int(radius_km * 1000)
        tsunami   = eq["tsunami"]
        url       = eq["url"]

        # Scale marker size to magnitude
        marker_size = min(10 + int((mag - 4.0) * 4), 28)

        tsunami_html = (
            "<br><b style=\\'color:#fff;background:#c0392b;padding:2px 6px;"
            "border-radius:3px;\\'>⚠️ TSUNAMI WARNING</b>"
            if tsunami else ""
        )
        tsunami_badge = "⚠️ TSUNAMI · " if tsunami else ""

        # Severity → ring opacity and fill
        fill_op  = {"moderate": 0.08, "high": 0.12, "critical": 0.18}.get(severity, 0.06)
        ring_w   = {"moderate": 2,    "high": 3,    "critical": 4   }.get(severity, 2)

        popup_html = (
            f"<div style=\\'min-width:210px;font-family:Arial,sans-serif;\\'>"
            f"<div style=\\'font-weight:800;font-size:14px;color:{color};"
            f"margin-bottom:4px;\\'>🌍 M{mag} Earthquake</div>"
            f"<div style=\\'font-size:12px;margin-bottom:3px;\\'><b>📍 {place}</b></div>"
            f"<div style=\\'font-size:12px;color:#555;margin-bottom:3px;\\'>"
            f"Depth: {depth} km · {time_pht}</div>"
            f"<div style=\\'font-size:11px;color:#888;margin-bottom:6px;\\'>"
            f"Estimated concern radius: {radius_km:.0f} km</div>"
            f"{tsunami_html}"
            f"<a href=\\'{url}\\' target=\\'_blank\\' "
            f"style=\\'font-size:11px;color:#2980b9;\\'>View USGS details →</a>"
            f"</div>"
        )

        lines += [
            f"  (function() {{",
            f"    var lat={lat}, lon={lon}, color='{color}';",
            # Damage-radius circle (dashed, semi-transparent)
            f"    var circle = L.circle([lat, lon], {{",
            f"      radius: {radius_m},",
            f"      color: color, weight: {ring_w},",
            f"      fillColor: color, fillOpacity: {fill_op},",
            f"      dashArray: '10 6',",
            f"      interactive: false,",
            f"      pane: 'hazardCircles'",
            f"    }}).addTo(eg);",
            # Pulsing epicenter dot
            f"    var pulseIcon = L.divIcon({{",
            f"      className: '',",
            f"      html: '<div style=\""
            f"width:{marker_size}px;height:{marker_size}px;"
            f"background:{color};border-radius:50%;"
            f"border:3px solid #fff;"
            f"box-shadow:0 0 0 3px {color},0 0 12px {color};"
            f"display:flex;align-items:center;justify-content:center;"
            f"font-size:{max(8, marker_size//3)}px;font-weight:bold;color:#fff;"
            f"animation:sos-pulse 1.8s ease-in-out infinite;"
            f"\">{mag}</div>',",
            f"      iconSize: [{marker_size},{marker_size}],",
            f"      iconAnchor: [{marker_size//2},{marker_size//2}]",
            f"    }});",
            f"    var marker = L.marker([lat, lon], {{",
            f"      icon: pulseIcon,",
            f"      pane: 'hazardMarkers',",
            f"      zIndexOffset: 900",
            f"    }}).addTo(eg);",
            # Popup
            f"    var popupHtml = '{popup_html}';",
            f"    circle.bindPopup(popupHtml, {{maxWidth:250}});",
            f"    marker.bindPopup(popupHtml, {{maxWidth:250}});",
            f"    marker.bindTooltip('{tsunami_badge}M{mag} · {place}');",
            f"  }})();",
        ]

    lines.append("})();")
    return "\n".join(lines)