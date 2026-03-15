import time
import logging
from datetime import datetime, timezone

print("[DEBUG] [INIT] Starting application initialization...")
t_init_start = time.time()

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from navigation import geocode_location, get_navigation_data
from branca.element import Element
from folium import plugins
import requests
import folium
from risk_monitor.user_data       import (
    init_user_tables, get_user_settings, save_user_settings,
    save_route_history, get_route_history, clear_route_history,
    get_user_profile, save_user_profile, change_password,
    extract_settings_from_form, get_settings_page_html, get_history_page_html,
)

from risk_monitor.features         import (
    get_typhoon_signal, get_banner_html,
    get_night_banner_html, enrich_routes_with_scores,
    attach_fares, apply_night_safety,
)
from risk_monitor.weather          import get_weather_risk, get_weather_banner_html, get_forecast
from risk_monitor.noah             import get_flood_risk_at, get_flood_warning_html, add_noah_flood_layer
from risk_monitor.community_reports import (
    init_report_tables, submit_report, confirm_report,
    get_all_active_reports, get_reports_map_js, get_report_panel_html,
    get_area_safety_penalty, apply_reports_to_routes, REPORT_TYPES,
)

from risk_monitor.crime_data import get_crime_risk_for_area  # used by home() POST path
from rss import build_rss
from risk_monitor.incidents import get_active_incidents, apply_incidents_to_routes, get_incidents_map_data

# ── New module integrations ────────────────────────────────────────────────────
from risk_monitor.mmda import (
    get_number_coding, get_road_closures,
    apply_mmda_to_routes, get_mmda_banner_html,
)
from risk_monitor.phivolcs import (
    get_recent_earthquakes, apply_seismic_to_routes,
    get_seismic_banner_html, get_epicenter_map_js,
)
from risk_monitor.safe_spots import (
    apply_safe_spots_to_routes, get_safe_spots_js,
    get_safe_spots_near, get_route_safe_spots_js, get_flat_route_coords, get_spots_for_coords,
)
from risk_monitor.vulnerable_profiles import (
    apply_vulnerable_profile_to_routes, get_profile_badge_html,
    PROFILES,
)
from risk_monitor.sos import (
    init_sos_tables, get_trusted_contacts,
    add_trusted_contact, remove_trusted_contact,
    log_sos_event, get_sos_panel_html,
    get_trusted_contacts_settings_html,
)

USE_MYSQL = False
print(f"[DEBUG] [INIT] USE_MYSQL is set to: {USE_MYSQL}")

if USE_MYSQL:
    print("[DEBUG] [INIT] Importing msql from db_opt...")
    from db_opt import msql
    chDB_perf = msql()
else:
    print("[DEBUG] [INIT] Importing nsql from db_opt...")
    from db_opt import nsql
    chDB_perf = nsql()

print("[DEBUG] [INIT] Initializing databases...")
t_db_init = time.time()
chDB_perf.init_db()
init_user_tables(chDB_perf)
init_report_tables(chDB_perf)
init_sos_tables(chDB_perf)
print(f"[DEBUG] [INIT] Database initialization took {time.time() - t_db_init:.4f}s")

app = Flask(__name__)
app.secret_key = 'saferoute_super_secret_key'
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=False)

print(f"[DEBUG] [INIT] Application setup complete in {time.time() - t_init_start:.4f}s")

# ── Map factory ───────────────────────────────────────────────────────────────

def get_base_map(center_lat=14.605, center_lon=120.985, zoom=13):
    t_start = time.time()
    print(f"[DEBUG] [get_base_map] Creating base map at center_lat={center_lat}, center_lon={center_lon}, zoom={zoom}")
    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom, tiles="OpenStreetMap")
    print("[DEBUG][get_base_map] Map instance created. Adding LocateControl plugin...")
    plugins.LocateControl(auto_start=False, strings={"title": "Use my current location"}).add_to(m)

    print("[DEBUG][get_base_map] Injecting custom Javascript map interaction handlers...")
    click_js = """
    <script>
        var originMarker = null;
        var destMarker   = null;
        var greenIcon = new L.Icon({
            iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png',
            shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
            iconSize: [25,41], iconAnchor:[12,41], popupAnchor: [1,-34], shadowSize: [41,41]
        });
        var redIcon = new L.Icon({
            iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
            shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
            iconSize: [25,41], iconAnchor: [12,41], popupAnchor: [1,-34], shadowSize:[41,41]
        });

        setTimeout(function() {
            var map_instance = window['{{MAP_ID}}'];
            if (map_instance) {
                map_instance.on('click', function(e) {
                    window.parent.postMessage({ type: 'map_click', lat: e.latlng.lat, lng: e.latlng.lng }, '*');
                });
                window.addEventListener("message", function(event) {
                    if (event.data && event.data.type === 'draw_marker') {
                        var coords = [event.data.lat, event.data.lng];
                        if (event.data.kind === 'origin') {
                            if (originMarker) map_instance.removeLayer(originMarker);
                            originMarker = L.marker(coords, {icon: greenIcon, interactive: false}).addTo(map_instance);
                        } else if (event.data.kind === 'destination') {
                            if (destMarker) map_instance.removeLayer(destMarker);
                            destMarker = L.marker(coords, {icon: redIcon, interactive: false}).addTo(map_instance);
                        }
                    }
                });
            }
        }, 1000);
    </script>
    """.replace('{{MAP_ID}}', m.get_name())

    m.get_root().html.add_child(Element(click_js))
    print(f"[DEBUG][get_base_map] Finished creating base map in {time.time() - t_start:.4f}s")
    return m


# ── Route renderers ───────────────────────────────────────────────────────────

def _draw_train_route(route, m):
    t_start = time.time()
    print(f"[DEBUG][_draw_train_route] Starting for route: {route.get('name', 'Unknown')}")
    route_layer = folium.FeatureGroup(name=route.get('name', 'Unknown Train Route'))
    line_color  = route.get('color', '#8e44ad')

    coords = route.get('coords', [])
    print(f"[DEBUG] [_draw_train_route] Drawing track polyline with {len(coords)} segments. Color: {line_color}")
    for segment in coords:
        if len(segment) >= 2:
            folium.PolyLine(
                locations=segment,
                color=line_color,
                weight=5,
                opacity=0.85,
                dash_array='10 6',
                tooltip=route.get('name', ''),
            ).add_to(route_layer)

    stations = route.get('stations', [])
    print(f"[DEBUG][_draw_train_route] Drawing {len(stations)} station pins.")
    for idx, station in enumerate(stations):
        is_terminal = (idx == 0 or idx == len(stations) - 1)
        folium.CircleMarker(
            location=[station['lat'], station['lon']],
            radius=9 if is_terminal else 6,
            color=line_color,
            weight=2,
            fill=True,
            fill_color='#ffffff',
            fill_opacity=1.0,
            tooltip=f"{'🔴 ' if is_terminal else '⚪ '}{station['name']}",
            popup=folium.Popup(
                f"<b>{station['name']}</b>"
                + ("<br><i>Terminal</i>" if is_terminal else ""),
                max_width=180,
            ),
        ).add_to(route_layer)

    route_layer.add_to(m)
    print(f"[DEBUG] [_draw_train_route] Completed in {time.time() - t_start:.4f}s")


def _draw_road_route(route, m):
    t_start = time.time()
    print(f"[DEBUG] [_draw_road_route] Starting for route: {route.get('name', 'Unknown')}")
    route_layer = folium.FeatureGroup(name=route.get('name', 'Unknown Road Route'))
    
    coords = route.get('coords', [])
    print(f"[DEBUG] [_draw_road_route] Drawing polyline with {len(coords)} coordinates.")
    folium.PolyLine(
        locations=coords,
        color=route.get('color', '#3388ff'),
        weight=7 if route.get('id') == 0 else 5,
        opacity=0.9,
        tooltip=f"{route.get('name', '')} ({route.get('time', '')})",
    ).add_to(route_layer)
    
    route_layer.add_to(m)
    print(f"[DEBUG][_draw_road_route] Completed in {time.time() - t_start:.4f}s")


def _draw_jeepney_route(route, m):
    t_start = time.time()
    print(f"[DEBUG] [_draw_jeepney_route] Starting for route: {route.get('name', 'Unknown')}")
    route_layer = folium.FeatureGroup(name=route.get('name', 'Unknown Jeepney Route'))
    segments    = route.get('segments',[])
    line_color  = route.get('color', '#e67e22')

    if not segments:
        print("[DEBUG] [_draw_jeepney_route] No segments found. Falling back to drawing raw coords.")
        folium.PolyLine(
            locations=route.get('coords',[]),
            color=line_color,
            weight=5,
            opacity=0.9,
            tooltip=route.get('name', ''),
        ).add_to(route_layer)
        route_layer.add_to(m)
        print(f"[DEBUG] [_draw_jeepney_route] Completed fallback drawing in {time.time() - t_start:.4f}s")
        return

    print(f"[DEBUG][_draw_jeepney_route] Processing {len(segments)} segments.")
    for seg in segments:
        coords = seg.get('coords',[])
        if len(coords) < 2:
            continue

        if seg['type'] == 'walk':
            folium.PolyLine(
                locations=coords,
                color='#7f8c8d',
                weight=3,
                opacity=0.8,
                dash_array='8 6',
                tooltip=seg.get('label', 'Walk'),
            ).add_to(route_layer)

        elif seg['type'] == 'jeepney':
            folium.PolyLine(
                locations=coords,
                color=seg.get('color', line_color),
                weight=6,
                opacity=0.9,
                tooltip=f"Jeepney: {seg.get('label', route.get('name', ''))} ({route.get('time', '')})",
            ).add_to(route_layer)

            stations = route.get('stations',[])
            for idx, stop in enumerate(stations):
                is_terminal = (idx == 0 or idx == len(stations) - 1)
                folium.CircleMarker(
                    location=[stop['lat'], stop['lon']],
                    radius=8 if is_terminal else 5,
                    color=seg.get('color', line_color),
                    weight=2,
                    fill=True,
                    fill_color='#ffffff',
                    fill_opacity=1.0,
                    tooltip=f"{'[END] ' if is_terminal else ''}{stop.get('name', '')}",
                    popup=folium.Popup(
                        f"<b>{stop.get('name', '')}</b>"
                        + ("<br><i>Terminal stop</i>" if is_terminal else ""),
                        max_width=180,
                    ),
                ).add_to(route_layer)

    board  = route.get('board_point')
    alight = route.get('alight_point')
    if board:
        print(f"[DEBUG] [_draw_jeepney_route] Adding board point at lat={board.get('lat')}, lon={board.get('lon')}")
        folium.Marker(
            location=[board['lat'], board['lon']],
            icon=folium.Icon(color='orange', icon='arrow-up', prefix='fa'),
            popup=folium.Popup(
                f"<b>Board here</b><br>Walk {route.get('walk_board_m', '?')}m from origin",
                max_width=200,
            ),
            tooltip="Board jeepney here",
        ).add_to(route_layer)
    if alight:
        print(f"[DEBUG] [_draw_jeepney_route] Adding alight point at lat={alight.get('lat')}, lon={alight.get('lon')}")
        folium.Marker(
            location=[alight['lat'], alight['lon']],
            icon=folium.Icon(color='orange', icon='arrow-down', prefix='fa'),
            popup=folium.Popup(
                f"<b>Alight here</b><br>Walk {route.get('walk_alight_m', '?')}m to destination",
                max_width=200,
            ),
            tooltip="Alight jeepney here",
        ).add_to(route_layer)

    route_layer.add_to(m)
    print(f"[DEBUG] [_draw_jeepney_route] Completed in {time.time() - t_start:.4f}s")


def _draw_bus_route(route, m):
    t_start = time.time()
    print(f"[DEBUG][_draw_bus_route] Starting for route: {route.get('name', 'Unknown')}")
    route_layer = folium.FeatureGroup(name=route.get('name', 'Unknown Bus Route'))
    segments    = route.get('segments',[])
    line_color  = route.get('color', '#16a085')

    if not segments:
        print("[DEBUG][_draw_bus_route] No segments. Fallback to raw coords.")
        folium.PolyLine(
            locations=route.get('coords',[]),
            color=line_color, weight=6, opacity=0.9,
            tooltip=route.get('name', ''),
        ).add_to(route_layer)
        route_layer.add_to(m)
        print(f"[DEBUG][_draw_bus_route] Completed fallback in {time.time() - t_start:.4f}s")
        return

    print(f"[DEBUG] [_draw_bus_route] Processing {len(segments)} segments.")
    for seg in segments:
        coords = seg.get('coords',[])
        if len(coords) < 2:
            continue

        if seg['type'] == 'walk':
            folium.PolyLine(
                locations=coords, color='#7f8c8d', weight=3,
                opacity=0.8, dash_array='8 6',
                tooltip=seg.get('label', 'Walk'),
            ).add_to(route_layer)

        elif seg['type'] == 'bus':
            folium.PolyLine(
                locations=coords,
                color=seg.get('color', line_color),
                weight=7, opacity=0.9,
                tooltip=f"Bus: {seg.get('label', route.get('name', ''))} ({route.get('time', '')})",
            ).add_to(route_layer)

            stations = route.get('stations',[])
            for idx, stop in enumerate(stations):
                is_terminal = (idx == 0 or idx == len(stations) - 1)
                folium.CircleMarker(
                    location=[stop['lat'], stop['lon']],
                    radius=7 if is_terminal else 4,
                    color='white',
                    fill=True,
                    fill_color=line_color,
                    fill_opacity=1.0 if is_terminal else 0.7,
                    weight=2,
                    tooltip=stop.get('name', f'Stop {idx+1}'),
                ).add_to(route_layer)

            if route.get('board_point'):
                bp = route['board_point']
                folium.Marker(
                    location=[bp['lat'], bp['lon']],
                    tooltip=f"Board bus here ({route.get('walk_board_m', '?')}m walk)",
                    icon=folium.Icon(color='blue', icon='bus', prefix='fa'),
                ).add_to(route_layer)

            if route.get('alight_point'):
                ap = route['alight_point']
                folium.Marker(
                    location=[ap['lat'], ap['lon']],
                    tooltip=f"Alight here ({route.get('walk_alight_m', '?')}m walk)",
                    icon=folium.Icon(color='orange', icon='flag', prefix='fa'),
                ).add_to(route_layer)

    route_layer.add_to(m)
    print(f"[DEBUG][_draw_bus_route] Completed in {time.time() - t_start:.4f}s")


def _draw_surface_route(route, m):
    t_start = time.time()
    print(f"[DEBUG] [_draw_surface_route] Starting for route: {route.get('name', 'Route')}")
    route_layer = folium.FeatureGroup(name=route.get('name', 'Route'))
    segments    = route.get('segments', [])

    if not segments:
        print("[DEBUG] [_draw_surface_route] No segments. Fallback raw coords drawing.")
        folium.PolyLine(
            locations=route.get('coords',[]),
            color=route.get('color', '#e67e22'), weight=5, opacity=0.9,
            tooltip=route.get('name', 'Route'),
        ).add_to(route_layer)
        route_layer.add_to(m)
        print(f"[DEBUG] [_draw_surface_route] Fallback completed in {time.time() - t_start:.4f}s")
        return

    print(f"[DEBUG] [_draw_surface_route] Iterating over {len(segments)} segments.")
    for seg_idx, seg in enumerate(segments):
        coords   = seg.get('coords',[])
        seg_type = seg.get('type', '')
        label    = seg.get('label', '')

        if len(coords) < 2:
            continue

        if seg_type == 'walk':
            folium.PolyLine(
                locations=coords, color='#7f8c8d', weight=3,
                opacity=0.8, dash_array='8 6',
                tooltip=label or 'Walk',
            ).add_to(route_layer)

        elif seg_type in ('jeepney', 'bus'):
            seg_color = '#e67e22' if seg_type == 'jeepney' else '#16a085'
            folium.PolyLine(
                locations=coords,
                color=seg.get('color', seg_color),
                weight=6, opacity=0.9,
                tooltip=f"{'Jeepney' if seg_type=='jeepney' else 'Bus'}: {label}",
            ).add_to(route_layer)

            stops = seg.get('stations', [])
            if stops:
                board  = stops[0]
                alight = stops[-1]
                folium.CircleMarker(
                    location=[board['lat'], board['lon']],
                    radius=8, color=seg_color, weight=2,
                    fill=True, fill_color='#ffffff', fill_opacity=1.0,
                    tooltip=f"Board: {board.get('name','Stop')}",
                ).add_to(route_layer)
                if len(stops) > 1:
                    folium.CircleMarker(
                        location=[alight['lat'], alight['lon']],
                        radius=8, color=seg_color, weight=2,
                        fill=True, fill_color=seg_color, fill_opacity=1.0,
                        tooltip=f"Alight: {alight.get('name','Stop')}",
                    ).add_to(route_layer)

    route_layer.add_to(m)
    print(f"[DEBUG][_draw_surface_route] Completed in {time.time() - t_start:.4f}s")


def _draw_multimodal_route(route, m):
    t_start = time.time()
    print(f"[DEBUG] [_draw_multimodal_route] Starting for route: {route.get('name', 'Unknown')}")
    route_layer = folium.FeatureGroup(name=route.get('name', 'Unknown Multimodal'))
    segments = route.get('segments', [])
    print(f"[DEBUG][_draw_multimodal_route] Drawing {len(segments)} segments.")
    for seg in segments:
        coords = seg.get('coords',[])
        if not coords: continue
        
        if seg['type'] == 'walk':
            folium.PolyLine(locations=coords, color='#7f8c8d', weight=3, dash_array='8 6', tooltip=seg.get('label', 'Walk')).add_to(route_layer)
        elif seg['type'] == 'train':
            for t_seg in coords:
                folium.PolyLine(locations=t_seg, color=seg.get('color', '#8e44ad'), weight=6, dash_array='10 6', tooltip=seg.get('label', 'Train')).add_to(route_layer)
        else: # Jeepney or Bus legs
            folium.PolyLine(locations=coords, color=seg.get('color', '#e67e22'), weight=6, tooltip=seg.get('label', 'Road')).add_to(route_layer)
            
    stations = route.get('stations', [])
    print(f"[DEBUG] [_draw_multimodal_route] Adding {len(stations)} station pins across journey.")
    for station in stations:
        folium.CircleMarker(
            location=[station['lat'], station['lon']],
            radius=5, color=route.get('color', '#000000'), weight=2, fill=True, fill_color='#fff', fill_opacity=1.0,
            tooltip=station.get('name', 'Station/Stop')
        ).add_to(route_layer)
        
    route_layer.add_to(m)
    print(f"[DEBUG] [_draw_multimodal_route] Completed in {time.time() - t_start:.4f}s")


def _draw_transit_route(route, m):
    t_start = time.time()
    print(f"[DEBUG] [_draw_transit_route] Starting for route: {route.get('name', 'Unknown Transit')}")
    route_layer = folium.FeatureGroup(name=route.get('name', 'Transit Route'))
    line_color  = route.get('color', '#8e44ad')

    segments = route.get('segments', [])
    print(f"[DEBUG] [_draw_transit_route] Processing {len(segments)} transit segments.")
    for seg in segments:
        seg_type = seg.get('type')
        coords   = seg.get('coords',[])

        if seg_type == 'walk':
            if len(coords) >= 2:
                folium.PolyLine(
                    locations=coords,
                    color='#7f8c8d',
                    weight=3,
                    opacity=0.85,
                    dash_array='8 5',
                    tooltip=seg.get('label', 'Walk'),
                ).add_to(route_layer)
            lbl = seg.get('label', '')
            if coords:
                pin_coord = coords[-1] if 'To ' in lbl or 'Walk to' in lbl else coords[0]
                folium.CircleMarker(
                    location=pin_coord,
                    radius=6,
                    color='#7f8c8d',
                    weight=2,
                    fill=True,
                    fill_color='#ecf0f1',
                    fill_opacity=1.0,
                    tooltip=lbl,
                ).add_to(route_layer)

        elif seg_type in ('jeepney', 'bus'):
            seg_color = seg.get('color', '#e67e22' if seg_type == 'jeepney' else '#16a085')
            if len(coords) >= 2:
                folium.PolyLine(
                    locations=coords,
                    color=seg_color,
                    weight=5 if seg_type == 'jeepney' else 6,
                    opacity=0.88,
                    tooltip=seg.get('label', seg_type.capitalize()),
                ).add_to(route_layer)
            stops = seg.get('stations', [])
            if stops:
                for si, st in enumerate([stops[0], stops[-1]]):
                    folium.CircleMarker(
                        location=[st['lat'], st['lon']],
                        radius=7, color=seg_color, weight=2,
                        fill=True,
                        fill_color='#ffffff' if si == 0 else seg_color,
                        fill_opacity=1.0,
                        tooltip=('Board: ' if si == 0 else 'Alight: ') + st.get('name', ''),
                    ).add_to(route_layer)

        elif seg_type == 'train':
            seg_color    = seg.get('color', line_color)
            seg_stations = seg.get('stations',[])

            for track_seg in coords:
                if len(track_seg) >= 2:
                    folium.PolyLine(
                        locations=track_seg,
                        color=seg_color,
                        weight=6,
                        opacity=0.9,
                        dash_array='12 5',
                        tooltip=seg.get('label', 'Train'),
                    ).add_to(route_layer)

            for idx, st in enumerate(seg_stations):
                is_terminal = (idx == 0 or idx == len(seg_stations) - 1)
                folium.CircleMarker(
                    location=[st['lat'], st['lon']],
                    radius=9 if is_terminal else 5,
                    color=seg_color,
                    weight=2,
                    fill=True,
                    fill_color='#ffffff',
                    fill_opacity=1.0,
                    tooltip=f"{'🔴 ' if is_terminal else '⚪ '}{st['name']}",
                    popup=folium.Popup(
                        f"<b>{st['name']}</b>"
                        + ("<br><i>Board here</i>" if idx == 0 else
                           "<br><i>Alight here</i>" if is_terminal else ""),
                        max_width=180,
                    ),
                ).add_to(route_layer)

    route_layer.add_to(m)
    print(f"[DEBUG][_draw_transit_route] Completed in {time.time() - t_start:.4f}s")


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/', methods=['GET', 'POST'])
def home():
    t_home_start = time.time()
    print(f"[DEBUG] [home] Request received. Method: {request.method}")
    if 'user' not in session:
        print("[DEBUG][home] User not in session, redirecting to login.")
        return redirect(url_for('login'))

    print(f"[DEBUG] [home] User authenticated as {session.get('user')}.")
    routes_data = []
    print("[DEBUG] [home] Generating base map...")
    t_map = time.time()
    m = get_base_map()
    print(f"[DEBUG] [home] Map generated in {time.time() - t_map:.4f}s")

    # ── Prefill from GET params (history "Use Again") ─────────────────────
    prefill_origin      = request.args.get('origin', '')
    prefill_destination = request.args.get('destination', '')
    prefill_mode        = request.args.get('commuterType', '')
    print(f"[DEBUG] [home] Prefill args -> origin: '{prefill_origin}', destination: '{prefill_destination}', mode: '{prefill_mode}'")

    if request.method == 'POST':
        origin_text   = request.form.get('origin')
        dest_text     = request.form.get('destination')
        commuter_type = request.form.get('commuterType')
        print(f"[DEBUG] [home] POST data -> origin: '{origin_text}', dest: '{dest_text}', commuterType: '{commuter_type}'")

        print("[DEBUG] [home] Executing geocoding...")
        t_geo = time.time()
        orig_lon, orig_lat = geocode_location(origin_text)
        dest_lon, dest_lat = geocode_location(dest_text)
        print(f"[DEBUG][home] Geocoding took {time.time() - t_geo:.4f}s")
        print(f"[DEBUG] [home] Geocode results -> Origin: ({orig_lon}, {orig_lat}), Destination: ({dest_lon}, {dest_lat})")

        if not orig_lon or not dest_lon:
            print("[DEBUG] [home] Location not found. Flashing error.")
            flash("Location not found. Please type a specific address.")
        else:
            print("[DEBUG] [home] Calling get_navigation_data()...")
            t_nav = time.time()
            nav_response = get_navigation_data(
                orig_lon, orig_lat, dest_lon, dest_lat, commuter_type, []
            )
            print(f"[DEBUG] [home] get_navigation_data completed in {time.time() - t_nav:.4f}s")

            if "error" in nav_response:
                print(f"[DEBUG] [home] Navigation error returned: {nav_response['error']}")
                flash(nav_response["error"])
            else:
                routes_data = nav_response.get("routes", [])
                print(f"[DEBUG] [home] Received {len(routes_data)} routes from navigation data.")

                if routes_data:
                    print("[DEBUG] [home] Setting up map markers for start and end coordinates.")
                    start_coord  = [orig_lat, orig_lon]
                    end_coord    = [dest_lat, dest_lon]
                    marker_group = folium.FeatureGroup(name="Start & End Points")
                    folium.Marker(start_coord, popup="Starting Point",
                                  icon=folium.Icon(color="green", icon="play")).add_to(marker_group)
                    folium.Marker(end_coord, popup="Destination",
                                  icon=folium.Icon(color="red",   icon="stop")).add_to(marker_group)
                    marker_group.add_to(m)
                    m.fit_bounds([start_coord, end_coord])
                    print("[DEBUG] [home] Map bounds fitted.")

                for i, route in enumerate(routes_data):
                    t_draw = time.time()
                    rtype = route.get('type', '')
                    segs  = route.get('segments',[])
                    seg_types = {s.get('type') for s in segs}
                    print(f"[DEBUG] [home] Drawing route {i}. Type: '{rtype}', Segment types: {seg_types}")
                    has_surface = bool(seg_types & {'jeepney', 'bus'})
                    has_train   = 'train' in seg_types
                    if rtype == 'transit' and has_surface and not has_train:
                        _draw_surface_route(route, m)
                    elif rtype in ('transit', 'train'):
                        _draw_transit_route(route, m)
                    elif rtype == 'jeepney':
                        _draw_jeepney_route(route, m)
                    elif rtype == 'bus':
                        _draw_bus_route(route, m)
                    elif rtype == 'multimodal':
                        _draw_multimodal_route(route, m)
                    else:
                        _draw_road_route(route, m)
                    print(f"[DEBUG] [home] Route {i} drawing took {time.time() - t_draw:.4f}s")

                if routes_data:
                    # ── Safety enrichment pipeline ────────────────────────────
                    print("[DEBUG] [home] Starting safety enrichment pipeline...")
                    
                    t_enrich = time.time()
                    enrich_routes_with_scores(routes_data)
                    print(f"[DEBUG] [home] enrich_routes_with_scores took {time.time() - t_enrich:.4f}s")
                    
                    t_night = time.time()
                    apply_night_safety(routes_data, commuter_type)
                    print(f"[DEBUG] [home] apply_night_safety took {time.time() - t_night:.4f}s")
                    
                    t_fares = time.time()
                    attach_fares(routes_data, commuter_type)
                    print(f"[DEBUG] [home] attach_fares took {time.time() - t_fares:.4f}s")

                    # Weather risk
                    print("[DEBUG] [home] Fetching weather risk...")
                    t_weather = time.time()
                    weather = get_weather_risk(orig_lat, orig_lon)
                    from risk_monitor.weather import apply_weather_to_routes
                    apply_weather_to_routes(routes_data, weather, commuter_type)
                    print(f"[DEBUG] [home] Weather risk and apply took {time.time() - t_weather:.4f}s")

                    # Flood risk (NOAH)
                    print("[DEBUG] [home] Analyzing route flood risk...")
                    t_flood = time.time()
                    from risk_monitor.noah import apply_route_flood_analysis, add_noah_flood_layer
                    apply_route_flood_analysis(routes_data, weather)
                    print(f"[DEBUG] [home] Route flood analysis took {time.time() - t_flood:.4f}s")

                    # Community reports penalty
                    print("[DEBUG] [home] Applying community reports to routes...")
                    t_reports = time.time()
                    apply_reports_to_routes(
                        routes_data, chDB_perf,
                        orig_lat, orig_lon, dest_lat, dest_lon,
                    )
                    print(f"[DEBUG] [home] Apply community reports took {time.time() - t_reports:.4f}s")

                    # Crime zone risk
                    print("[DEBUG][home] Fetching and applying crime risk...")
                    t_crime = time.time()
                    from risk_monitor.crime_data import (
                        apply_crime_both_ends, get_crime_risk_with_reports,
                        scan_route_crime_zones, apply_route_crime_to_routes,
                    )
                    orig_crime = get_crime_risk_with_reports(orig_lat, orig_lon, origin_text or "", chDB_perf)
                    dest_crime = get_crime_risk_with_reports(dest_lat, dest_lon, dest_text or "", chDB_perf)

                    for route in routes_data:
                        wps =[]
                        if route.get("segments"):
                            for seg in route["segments"]:
                                sc = seg.get("coords",[])
                                if sc and isinstance(sc[0], list) and isinstance(sc[0][0], list):
                                    for sub in sc:
                                        wps.extend(sub)
                                else:
                                    wps.extend(sc)
                        if not wps and route.get("coords"):
                            wps = route["coords"]
                        route["route_crime_zones"] = scan_route_crime_zones(wps)

                    apply_crime_both_ends(routes_data, orig_crime, dest_crime, commuter_type)
                    apply_route_crime_to_routes(routes_data, commuter_type)
                    print(f"[DEBUG] [home] Crime risk pipeline took {time.time() - t_crime:.4f}s")

                    # Real-time incidents
                    print("[DEBUG] [home] Fetching and applying real-time incidents...")
                    t_inc = time.time()
                    try:
                        _incidents = get_active_incidents()
                        apply_incidents_to_routes(
                            routes_data, _incidents,
                            orig_lat, orig_lon, dest_lat, dest_lon,
                        )
                    except Exception as e:
                        print(f"[DEBUG] [home] Exception in real-time incidents pipeline: {e}")
                        pass
                    print(f"[DEBUG] [home] Real-time incidents took {time.time() - t_inc:.4f}s")

                    # MMDA closures
                    print("[DEBUG][home] Applying MMDA data to routes...")
                    t_mmda = time.time()
                    try:
                        apply_mmda_to_routes(routes_data, None)
                    except Exception as e:
                        print(f"[DEBUG] [home] Exception in MMDA pipeline: {e}")
                        pass
                    print(f"[DEBUG] [home] MMDA pipeline took {time.time() - t_mmda:.4f}s")

                    # Seismic risk
                    print("[DEBUG] [home] Fetching and applying seismic risk data...")
                    t_seismic = time.time()
                    try:
                        _eqs = get_recent_earthquakes(hours_back=12)
                        apply_seismic_to_routes(routes_data, _eqs)
                    except Exception as e:
                        print(f"[DEBUG][home] Exception in seismic pipeline: {e}")
                        pass
                    print(f"[DEBUG] [home] Seismic pipeline took {time.time() - t_seismic:.4f}s")

                    # Vulnerable commuter profile
                    print("[DEBUG] [home] Applying vulnerable commuter profile...")
                    t_vuln = time.time()
                    try:
                        _profile = request.form.get('vulnerable_profile', '')
                        if _profile and _profile in PROFILES:
                            print(f"[DEBUG] [home] Found vulnerable profile: {_profile}")
                            apply_vulnerable_profile_to_routes(routes_data, _profile, weather)
                    except Exception as e:
                        print(f"[DEBUG] [home] Exception in vulnerable profiles pipeline: {e}")
                        pass
                    print(f"[DEBUG] [home] Vulnerable profile processing took {time.time() - t_vuln:.4f}s")

                    # Add NOAH flood layer to map
                    print("[DEBUG] [home] Adding NOAH flood layer to map...")
                    add_noah_flood_layer(m)
                    folium.LayerControl().add_to(m)

                    # Save history
                    if 'user' in session:
                        print(f"[DEBUG] [home] Saving route history for user '{session['user']}'...")
                        t_hist = time.time()
                        save_route_history(
                            chDB_perf, session['user'],
                            origin_text, dest_text, commuter_type, len(routes_data)
                        )
                        print(f"[DEBUG] [home] History saving took {time.time() - t_hist:.4f}s")
                    print("[DEBUG] [home] Finished safety pipeline for POST request.")

    # ── Banners & report data for template ───────────────────────────────────
    print("[DEBUG] [home] Generating banners and report data...")
    t_banners = time.time()
    typhoon        = get_typhoon_signal()
    typhoon_banner = get_banner_html(typhoon)
    _commuter_type_for_banner = request.form.get('commuterType', 'commute') if request.method == 'POST' else 'commute'
    night_banner   = get_night_banner_html(_commuter_type_for_banner)

    try:
        weather_loc = (orig_lat, orig_lon)
    except NameError:
        weather_loc = (14.5995, 120.9842)
    print(f"[DEBUG] [home] Weather banner location: {weather_loc}")
    weather        = get_weather_risk(*weather_loc)
    weather_banner = get_weather_banner_html(weather, _commuter_type_for_banner)

    active_reports = get_all_active_reports(chDB_perf, limit=50)
    reports_map_js = get_reports_map_js(active_reports)
    report_panel   = get_report_panel_html()

    # ── MMDA banner (number coding) ───────────────────────────────────────
    try:
        _mmda_closures = get_road_closures()
        mmda_banner    = get_mmda_banner_html(None, _mmda_closures)
    except Exception as e:
        print(f"[DEBUG] [home] Exception fetching MMDA banner: {e}")
        mmda_banner = ""

    # ── PHIVOLCS banner (seismic) ─────────────────────────────────────────
    try:
        _earthquakes    = get_recent_earthquakes(hours_back=12)
        seismic_banner  = get_seismic_banner_html(_earthquakes)
        epicenter_js    = get_epicenter_map_js(_earthquakes)
    except Exception as e:
        print(f"[DEBUG] [home] Exception fetching PHIVOLCS banner: {e}")
        seismic_banner = ""
        epicenter_js   = ""

    # ── SOS panel ─────────────────────────────────────────────────────────
    try:
        _sos_contacts = get_trusted_contacts(chDB_perf, session['user']) if 'user' in session else[]
        sos_panel     = get_sos_panel_html(_sos_contacts)
    except Exception as e:
        print(f"[DEBUG] [home] Exception generating SOS panel: {e}")
        sos_panel = ""
    print(f"[DEBUG] [home] Banner & report generation took {time.time() - t_banners:.4f}s")

    print("[DEBUG] [home] Rendering map HTML...")
    t_render_map = time.time()
    map_html = m.get_root().render()
    print(f"[DEBUG] [home] Map rendering took {time.time() - t_render_map:.4f}s")

    print(f"[DEBUG] [home] Total /home response constructed in {time.time() - t_home_start:.4f}s. Rendering index.html.")
    return render_template(
        'index.html',
        user=session['user'],
        username=session['user'],
        map_html=map_html,
        routes=routes_data,
        typhoon_banner=typhoon_banner,
        night_banner=night_banner,
        weather_banner=weather_banner,
        mmda_banner=mmda_banner,
        seismic_banner=seismic_banner,
        epicenter_js=epicenter_js,
        sos_panel=sos_panel,
        reports_map_js=reports_map_js,
        report_panel=report_panel,
        active_reports=active_reports,
        prefill_origin=prefill_origin,
        prefill_destination=prefill_destination,
        prefill_mode=prefill_mode,
        vulnerable_profiles=PROFILES,
    )

@app.route('/register', methods=['GET', 'POST'])
def register():
    t_reg = time.time()
    print(f"[DEBUG] [register] Method: {request.method}")
    if request.method == 'POST':
        username  = request.form.get('username')
        password  = request.form.get('password')
        print(f"[DEBUG] [register] Attempting registration for username: '{username}'")
        conn, c   = chDB_perf.get_db_connection()
        chDB_perf.execute_query(c, "SELECT * FROM users WHERE username=?", (username,))
        if c.fetchone():
            print(f"[DEBUG] [register] Username '{username}' already exists. Failing registration.")
            flash("Username already exists.")
            c.close(); conn.close()
            return redirect(url_for('register'))
        
        print(f"[DEBUG] [register] Username available. Hashing password...")
        hashed_pw = generate_password_hash(password)
        chDB_perf.execute_query(c, "INSERT INTO users (username, password) VALUES (?, ?)",
                                (username, hashed_pw))
        conn.commit(); c.close(); conn.close()
        print(f"[DEBUG] [register] Registration successful for '{username}'. Time taken: {time.time() - t_reg:.4f}s")
        flash("Registration successful!")
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    t_login = time.time()
    print(f"[DEBUG] [login] Method: {request.method}")
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        print(f"[DEBUG] [login] Attempting login for username: '{username}'")
        conn, c  = chDB_perf.get_db_connection()
        chDB_perf.execute_query(c, "SELECT password FROM users WHERE username=?", (username,))
        user = c.fetchone()
        c.close(); conn.close()
        if user and check_password_hash(user[0], password):
            print(f"[DEBUG] [login] Password match for '{username}'. Setting session.")
            session['user'] = username
            print(f"[DEBUG] [login] Login operation took {time.time() - t_login:.4f}s")
            return redirect(url_for('home'))
        print(f"[DEBUG] [login] Invalid username or password for '{username}'.")
        flash("Invalid username or password.")
        return redirect(url_for('login'))
    return render_template('login.html')


@app.route('/logout')
def logout():
    print(f"[DEBUG] [logout] User logging out: {session.get('user')}")
    session.pop('user', None)
    return redirect(url_for('login'))


# ══════════════════════════════════════════════════════════════════════════════
#  JSON API AUTH ENDPOINTS (for Flutter app)
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    """JSON API endpoint for Flutter login. Returns user token & info."""
    t_start = time.time()
    print("[DEBUG] [api_login] POST /api/auth/login hit")
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        if not username or not password:
            print("[DEBUG] [api_login] Missing username or password")
            return jsonify({'ok': False, 'message': 'Username and password required'}), 400
        
        print(f"[DEBUG] [api_login] Attempting login for: '{username}'")
        conn, c = chDB_perf.get_db_connection()
        chDB_perf.execute_query(c, "SELECT password FROM users WHERE username=?", (username,))
        user_row = c.fetchone()
        c.close()
        conn.close()
        
        if not user_row or not check_password_hash(user_row[0], password):
            print(f"[DEBUG] [api_login] Auth failed for '{username}'")
            return jsonify({'ok': False, 'message': 'Invalid credentials'}), 401
        
        # Success: store session and return user token
        session['user'] = username
        print(f"[DEBUG] [api_login] Login successful for '{username}'. Time: {time.time() - t_start:.4f}s")
        
        return jsonify({
            'ok': True,
            'message': 'Login successful',
            'user': username,
            'token': username,  # Simple token = username (backend validates via session)
        }), 200
        
    except Exception as e:
        print(f"[DEBUG] [api_login] Exception: {e}")
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/auth/register', methods=['POST'])
def api_register():
    """JSON API endpoint for Flutter registration. Returns user token & info."""
    t_start = time.time()
    print("[DEBUG] [api_register] POST /api/auth/register hit")
    try:
        data     = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        email    = data.get('email',    '').strip()

        if not username or not password:
            print("[DEBUG] [api_register] Missing username or password")
            return jsonify({'ok': False, 'message': 'Username and password required'}), 400

        if len(password) < 6:
            return jsonify({'ok': False, 'message': 'Password must be at least 6 characters'}), 400

        print(f"[DEBUG] [api_register] Attempting registration for: '{username}'")
        conn, c = chDB_perf.get_db_connection()
        chDB_perf.execute_query(c, "SELECT * FROM users WHERE username=?", (username,))

        if c.fetchone():
            print(f"[DEBUG] [api_register] Username '{username}' already exists")
            c.close(); conn.close()
            return jsonify({'ok': False, 'message': 'Username already in use'}), 409

        # Create new user
        hashed_pw = generate_password_hash(password)
        chDB_perf.execute_query(c, "INSERT INTO users (username, password) VALUES (?, ?)",
                                (username, hashed_pw))
        conn.commit()

        # Initialize user profile
        save_user_profile(chDB_perf, username, username, email)
        c.close(); conn.close()

        # Auto-login after registration
        session['user'] = username
        print(f"[DEBUG] [api_register] Registration successful for '{username}'. Time: {time.time() - t_start:.4f}s")

        return jsonify({
            'ok':      True,
            'message': 'Registration successful',
            'user':    username,
            'token':   username,
        }), 201

    except Exception as e:
        print(f"[DEBUG] [api_register] Exception: {e}")
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    """JSON API endpoint for Flutter logout."""
    print(f"[DEBUG] [api_logout] User logging out: {session.get('user')}")
    session.pop('user', None)
    return jsonify({'ok': True, 'message': 'Logged out'}), 200


@app.route('/api/user/current', methods=['GET'])
def api_user_current():
    """JSON API endpoint to get current user profile and settings."""
    print("[DEBUG] [api_user_current] GET /api/user/current hit")
    
    # Check if user is authenticated by looking for token in headers or session
    auth_header = request.headers.get('Authorization', '')
    token = None
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]  # Extract token after 'Bearer '
    
    username = token if token else session.get('user')
    
    if not username:
        print("[DEBUG] [api_user_current] Unauthorized (no user)")
        return jsonify({'ok': False, 'message': 'Unauthorized'}), 401
    
    try:
        print(f"[DEBUG] [api_user_current] Fetching profile for '{username}'")
        user_settings = get_user_settings(chDB_perf, username)
        user_profile = get_user_profile(chDB_perf, username)
        
        # Build comprehensive user response for Flutter
        user_data = {
            'ok': True,
            'id': username,
            'name': user_profile.get('display_name', username),
            'username': username,
            'email': user_profile.get('email', ''),
            'role': 'Commuter',
            'avatarUrl': None,
            'stats': {
                'trips': user_profile.get('trips_count', 0),
                'reports': user_profile.get('reports_count', 0),
                'upvotedReports': user_profile.get('upvotes_count', 0),
            },
            'commuterType': user_settings.get('default_commuter_type', 'commute'),
            'preferences': {
                'aiSafety': user_settings.get('show_weather_banner', True),
                'nightMode': False,  # Controlled by ThemeController on the client
                'transport': user_settings.get('transport_preference', ['jeep', 'walk']),
            },
            'survey': {
                'completed': user_settings.get('survey_completed', False),
                'commuter_types': user_settings.get('commuter_types', []),
                'transport_modes': user_settings.get('transport_modes', []),
                'safety_concerns': user_settings.get('safety_concerns', []),
            },
        }
        print(f"[DEBUG] [api_user_current] Returning user data for '{username}'")
        return jsonify(user_data), 200
        
    except Exception as e:
        print(f"[DEBUG] [api_user_current] Exception: {e}")
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/settings', methods=['GET'])
def api_get_settings():
    """JSON API endpoint to retrieve user settings for Flutter."""
    print("[DEBUG] [api_get_settings] GET /api/settings hit")
    
    # Extract token from Authorization header or use session
    auth_header = request.headers.get('Authorization', '')
    token = None
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
    
    username = token if token else session.get('user')
    
    if not username:
        print("[DEBUG] [api_get_settings] Unauthorized (no user)")
        return jsonify({'ok': False, 'message': 'Unauthorized'}), 401
    
    try:
        print(f"[DEBUG] [api_get_settings] Fetching settings for '{username}'")
        user_settings = get_user_settings(chDB_perf, username)
        
        # Return settings with expected field names for Flutter
        return jsonify({
            'ok': True,
            'settings': {
                'default_commuter_type': user_settings.get('default_commuter_type', 'commute'),
                'transport_preference': user_settings.get('transport_preference', ['jeep', 'walk']),
                'show_weather_banner': user_settings.get('show_weather_banner', True),
                'show_crime_banner': user_settings.get('show_crime_banner', True),
                'show_flood_banner': user_settings.get('show_flood_banner', True),
                'show_night_warnings': user_settings.get('show_night_warnings', True),
                'preferred_name': user_settings.get('preferred_name', ''),
                'home_address': user_settings.get('home_address', ''),
                'work_address': user_settings.get('work_address', ''),
                'commuter_types': user_settings.get('commuter_types', []),
                'transport_modes': user_settings.get('transport_modes', []),
                'safety_concerns': user_settings.get('safety_concerns', []),
                'survey_completed': user_settings.get('survey_completed', False),
            }
        }), 200
    except Exception as e:
        print(f"[DEBUG] [api_get_settings] Exception: {e}")
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/settings', methods=['POST'])
def api_save_settings():
    """JSON API endpoint to save user settings from Flutter."""
    print("[DEBUG] [api_save_settings] POST /api/settings hit")
    
    # Extract token from Authorization header or use session
    auth_header = request.headers.get('Authorization', '')
    token = None
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
    
    username = token if token else session.get('user')
    
    if not username:
        print("[DEBUG] [api_save_settings] Unauthorized (no user)")
        return jsonify({'ok': False, 'message': 'Unauthorized'}), 401
    
    try:
        data = request.get_json() or {}
        print(f"[DEBUG] [api_save_settings] Received settings data: {data}")
        
        # Load current settings first to preserve survey data and other fields
        current_settings = get_user_settings(chDB_perf, username)
        
        # Apply only the non-survey settings fields provided in this request
        updatable_keys = [
            'default_commuter_type', 'transport_preference', 'show_weather_banner',
            'show_crime_banner', 'show_flood_banner', 'show_night_warnings',
            'preferred_name', 'home_address', 'work_address',
        ]
        for key in updatable_keys:
            if key in data:
                current_settings[key] = data[key]
        
        # Save merged settings (survey data preserved)
        success = save_user_settings(chDB_perf, username, current_settings)
        
        if not success:
            print(f"[DEBUG] [api_save_settings] Failed to save settings for '{username}'")
            return jsonify({'ok': False, 'message': 'Failed to save settings'}), 500
        
        # Also update user profile if display_name or email provided
        if data.get('display_name') or data.get('email'):
            print(f"[DEBUG] [api_save_settings] Updating user profile")
            save_user_profile(
                chDB_perf, username,
                data.get('display_name', ''),
                data.get('email', '')
            )
        
        print(f"[DEBUG] [api_save_settings] Settings saved successfully for '{username}'")
        return jsonify({'ok': True, 'message': 'Settings saved'}), 200
        
    except Exception as e:
        print(f"[DEBUG] [api_save_settings] Exception: {e}")
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/user/survey', methods=['POST'])
def api_save_survey():
    """JSON API endpoint to save user onboarding survey responses from Flutter."""
    print("[DEBUG] [api_save_survey] POST /api/user/survey hit")
    
    # Extract token from Authorization header or use session
    auth_header = request.headers.get('Authorization', '')
    token = None
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
    
    username = token if token else session.get('user')
    
    if not username:
        print("[DEBUG] [api_save_survey] Unauthorized (no user)")
        return jsonify({'ok': False, 'message': 'Unauthorized'}), 401
    
    try:
        data = request.get_json() or {}
        print(f"[DEBUG] [api_save_survey] Received survey data: {data}")
        
        # Build settings dict with survey data
        survey_settings = {
            'commuter_types': data.get('commuterTypes', []),
            'transport_modes': data.get('transport', []),
            'safety_concerns': data.get('safety', []),
            'survey_completed': True,
            'survey_completed_at': datetime.now(tz=timezone.utc).isoformat(),
        }
        
        # Get current settings and merge with survey data
        current_settings = get_user_settings(chDB_perf, username)
        current_settings.update(survey_settings)
        
        # Save merged settings to database
        success = save_user_settings(chDB_perf, username, current_settings)
        
        if not success:
            print(f"[DEBUG] [api_save_survey] Failed to save survey for '{username}'")
            return jsonify({'ok': False, 'message': 'Failed to save survey'}), 500
        
        print(f"[DEBUG] [api_save_survey] Survey saved successfully for '{username}'")
        return jsonify({'ok': True, 'message': 'Survey saved'}), 200
        
    except Exception as e:
        print(f"[DEBUG] [api_save_survey] Exception: {e}")
        return jsonify({'ok': False, 'message': str(e)}), 500


# ────────────────────────────────────────────────────────────────────────────
# NICE TO HAVE: History, Password Change, and other user endpoints
# ────────────────────────────────────────────────────────────────────────────

@app.route('/api/auth/change-password', methods=['POST'])
def api_change_password():
    """JSON API endpoint for Flutter password change."""
    print("[DEBUG] [api_change_password] POST /api/auth/change-password hit")
    
    auth_header = request.headers.get('Authorization', '')
    token = None
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
    
    username = token if token else session.get('user')
    
    if not username:
        print("[DEBUG] [api_change_password] Unauthorized")
        return jsonify({'ok': False, 'message': 'Unauthorized'}), 401
    
    try:
        data = request.get_json() or {}
        current_password = data.get('current_password', '').strip()
        new_password = data.get('new_password', '').strip()
        
        if not current_password or not new_password:
            return jsonify({'ok': False, 'message': 'Missing password fields'}), 400
        
        # Use existing backend function
        result = change_password(chDB_perf, username, current_password, new_password)
        
        if result.get('ok'):
            print(f"[DEBUG] [api_change_password] Password changed for {username}")
            return jsonify({'ok': True, 'message': result.get('message', 'Password updated')}), 200
        else:
            print(f"[DEBUG] [api_change_password] Password change failed: {result.get('message')}")
            return jsonify({'ok': False, 'message': result.get('message', 'Password change failed')}), 400
            
    except Exception as e:
        print(f"[DEBUG] [api_change_password] Exception: {e}")
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/auth/change-email', methods=['POST'])
def api_change_email():
    """
    JSON API endpoint for Flutter email change.
    Requires the user's current password to confirm identity before
    updating the email — no verification link, just a direct DB update.
    Body: { current_password, new_email }
    """
    print("[DEBUG] [api_change_email] POST /api/auth/change-email hit")

    auth_header = request.headers.get('Authorization', '')
    token = None
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]

    username = token if token else session.get('user')

    if not username:
        print("[DEBUG] [api_change_email] Unauthorized")
        return jsonify({'ok': False, 'message': 'Unauthorized'}), 401

    try:
        data             = request.get_json() or {}
        current_password = data.get('current_password', '').strip()
        new_email        = data.get('new_email', '').strip()

        if not current_password or not new_email:
            return jsonify({'ok': False, 'message': 'Current password and new email are required'}), 400

        # Basic email format check
        import re
        if not re.fullmatch(r'[\w\.\+\-]+@[\w\-]+\.[a-zA-Z]{2,}', new_email):
            return jsonify({'ok': False, 'message': 'Invalid email address format'}), 400

        # Verify current password before making any changes
        conn, c = chDB_perf.get_db_connection()
        chDB_perf.execute_query(c, "SELECT password FROM users WHERE username=?", (username,))
        row = c.fetchone()
        c.close(); conn.close()

        if not row or not check_password_hash(row[0], current_password):
            print(f"[DEBUG] [api_change_email] Wrong password for '{username}'")
            return jsonify({'ok': False, 'message': 'Current password is incorrect'}), 401

        # Password confirmed — update the email in the user profile
        profile = get_user_profile(chDB_perf, username)
        display_name = profile.get('display_name', username)
        save_user_profile(chDB_perf, username, display_name, new_email)

        print(f"[DEBUG] [api_change_email] Email updated for '{username}' to '{new_email}'")
        return jsonify({'ok': True, 'message': 'Email updated successfully'}), 200

    except Exception as e:
        print(f"[DEBUG] [api_change_email] Exception: {e}")
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/history', methods=['GET'])
def api_history():
    """JSON API endpoint for Flutter to fetch route history."""
    print("[DEBUG] [api_history] GET /api/history hit")
    
    auth_header = request.headers.get('Authorization', '')
    token = None
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
    
    username = token if token else session.get('user')
    
    if not username:
        print("[DEBUG] [api_history] Unauthorized")
        return jsonify({'ok': False, 'message': 'Unauthorized'}), 401
    
    try:
        # Use existing backend function
        hist = get_route_history(chDB_perf, username, limit=20)
        
        # Transform to API response format
        history_data = [
            {
                'origin': item.get('origin', ''),
                'destination': item.get('destination', ''),
                'commuterType': item.get('commuter_type', 'commute'),
                'routeCount': item.get('route_count', 0),
                'searchedAt': item.get('searched_at', ''),
            }
            for item in hist
        ]
        
        print(f"[DEBUG] [api_history] Returned {len(history_data)} history items for {username}")
        return jsonify({'ok': True, 'history': history_data}), 200
        
    except Exception as e:
        print(f"[DEBUG] [api_history] Exception: {e}")
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/history/clear', methods=['POST'])
def api_history_clear():
    """JSON API endpoint for Flutter to clear route history."""
    print("[DEBUG] [api_history_clear] POST /api/history/clear hit")
    
    auth_header = request.headers.get('Authorization', '')
    token = None
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
    
    username = token if token else session.get('user')
    
    if not username:
        print("[DEBUG] [api_history_clear] Unauthorized")
        return jsonify({'ok': False, 'message': 'Unauthorized'}), 401
    
    try:
        # Use existing backend function
        clear_route_history(chDB_perf, username)
        
        print(f"[DEBUG] [api_history_clear] History cleared for {username}")
        return jsonify({'ok': True, 'message': 'History cleared'}), 200
        
    except Exception as e:
        print(f"[DEBUG] [api_history_clear] Exception: {e}")
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route('/api/suggest', methods=['GET'])
def suggest_location():
    t_start = time.time()
    query = request.args.get('q', '')
    print(f"[DEBUG] [suggest_location] Query received: '{query}'")
    if len(query) < 3:
        print("[DEBUG] [suggest_location] Query too short. Returning empty array.")
        return jsonify([])
    url = (
        f"https://nominatim.openstreetmap.org/search"
        f"?q={query}&format=json&addressdetails=1&limit=5&countrycodes=ph"
    )
    print(f"[DEBUG] [suggest_location] Calling Nominatim URL: {url}")
    try:
        t_req = time.time()
        res = requests.get(url, headers={'User-Agent': 'SafeRoute-Flask-App/1.0'}).json()
        print(f"[DEBUG] [suggest_location] Nominatim response received in {time.time() - t_req:.4f}s. Result count: {len(res)}")
        return jsonify(res)
    except Exception as e:
        print(f"[DEBUG] [suggest_location] Exception during search: {e}")
        return jsonify([])


@app.route('/api/reverse', methods=['GET'])
def reverse_geocode_api():
    t_start = time.time()
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    print(f"[DEBUG] [reverse_geocode_api] Reversing lat: {lat}, lon: {lon}")
    url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
    print(f"[DEBUG] [reverse_geocode_api] Calling Nominatim URL: {url}")
    try:
        t_req = time.time()
        data = requests.get(url, headers={'User-Agent': 'SafeRoute-Flask-App/1.0'}).json()
        print(f"[DEBUG] [reverse_geocode_api] Request finished in {time.time() - t_req:.4f}s")
        return jsonify({"address": data.get("display_name", f"{lat}, {lon}")})
    except Exception as e:
        print(f"[DEBUG] [reverse_geocode_api] Exception during reverse geocode: {e}")
        return jsonify({"address": f"{lat}, {lon}"})

@app.route('/api/nearby', methods=['GET'])
def get_nearby_api():
    t_start = time.time()
    print(f"[DEBUG] [get_nearby_api] Incoming args: {request.args}")
    try:
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
        radius = float(request.args.get('radius', 800))
        print(f"[DEBUG] [get_nearby_api] Parsed params: lat={lat}, lon={lon}, radius={radius}")
        
        from navigation import get_nearby_transit
        print("[DEBUG] [get_nearby_api] Calling get_nearby_transit...")
        t_nav = time.time()
        results = get_nearby_transit(lat, lon, radius)
        print(f"[DEBUG] [get_nearby_api] get_nearby_transit returned {len(results)} items in {time.time() - t_nav:.4f}s")
        return jsonify(results)
    except Exception as e:
        print(f"[DEBUG] [get_nearby_api] Exception: {e}")
        return jsonify({"error": str(e)}), 400

@app.route('/api/route', methods=['POST'])
@app.route('/api/routes', methods=['POST'])
def get_routes():
    t_route_start = time.time()
    print("[DEBUG] [get_routes] /api/routes endpoint hit.")
    data = request.json
    print(f"[DEBUG][get_routes] Raw payload: {data}")
    
    # Handle both direct text input or coordinates
    origin_text = data.get('origin')
    dest_text = data.get('destination')
    commuter_type = data.get('mode') or data.get('commuterType') or 'car'
    print(f"[DEBUG] [get_routes] Parsed inputs -> origin_text='{origin_text}', dest_text='{dest_text}', mode='{commuter_type}'")
    
    # Check for coordinates first (from map clicks/pins)
    orig_coords = data.get('orig_coords') or data.get('originCoords')
    dest_coords = data.get('dest_coords') or data.get('destCoords')
    print(f"[DEBUG] [get_routes] Coordinate override check -> orig_coords: {orig_coords}, dest_coords: {dest_coords}")

    t_geo = time.time()
    if orig_coords:
        orig_lon = float(orig_coords.get('lon', orig_coords.get('lng', 0)))
        orig_lat = float(orig_coords.get('lat', 0))
    else:
        print(f"[DEBUG] [get_routes] Geocoding origin_text: '{origin_text}'")
        orig_lon, orig_lat = geocode_location(origin_text)

    if dest_coords:
        dest_lon = float(dest_coords.get('lon', dest_coords.get('lng', 0)))
        dest_lat = float(dest_coords.get('lat', 0))
    else:
        print(f"[DEBUG] [get_routes] Geocoding dest_text: '{dest_text}'")
        dest_lon, dest_lat = geocode_location(dest_text)
    print(f"[DEBUG] [get_routes] Geocode resolution took {time.time() - t_geo:.4f}s")
    print(f"[DEBUG] [get_routes] Final coordinates -> Orig: ({orig_lat}, {orig_lon}), Dest: ({dest_lat}, {dest_lon})")

    if not orig_lon or not orig_lat:
        print("[DEBUG][get_routes] Missing origin. Returning error 400.")
        return jsonify({"error": "Could not find your origin location. Try a more specific address."}), 400

    if not dest_lon or not dest_lat:
        # Destination not found — return a friendly error that tells the app
        # to show a "location not found" message rather than a generic failure.
        print(f"[DEBUG][get_routes] Destination '{dest_text}' could not be geocoded.")
        return jsonify({
            "error": f"Could not find '{dest_text}'. Try a more specific address, landmark, or neighbourhood name.",
            "error_type": "dest_not_found",
            "origin_lat": orig_lat,
            "origin_lon": orig_lon,
        }), 400

    # Calculate the route
    print("[DEBUG] [get_routes] Calling get_navigation_data()...")
    t_nav = time.time()
    nav_response = get_navigation_data(
        orig_lon, orig_lat, dest_lon, dest_lat, commuter_type,[]
    )
    print(f"[DEBUG] [get_routes] get_navigation_data completed in {time.time() - t_nav:.4f}s")

    if "error" in nav_response:
        print(f"[DEBUG] [get_routes] Navigation error: {nav_response['error']}")
        return jsonify({"error": nav_response["error"]}), 400

    routes = nav_response.get("routes", [])
    print(f"[DEBUG] [get_routes] Received {len(routes)} routes.")
    if routes:
        print("[DEBUG] [get_routes] Commencing route enrichments...")
        t_enrich_total = time.time()
        from risk_monitor.features import (
            rank_routes, enrich_routes_with_scores,
            attach_fares, apply_night_safety,
            _compute_safety_score,
        )
        from risk_monitor.weather import apply_weather_to_routes
        from risk_monitor.noah   import apply_route_flood_analysis

        _ct = commuter_type.lower().strip()
        _is_transit = _ct in (
            'transit', 'jeepney', 'bus', 'train',
            'jeepney_bus', 'train_jeepney', 'train_bus',
            'lrt1', 'lrt-1', 'lrt2', 'lrt-2',
            'mrt3', 'mrt-3', 'mrt7', 'pnr', 'commute',
        )
        print(f"[DEBUG] [get_routes] Commuter mode parsed as: '{_ct}'. Is transit: {_is_transit}")

        if not _is_transit:
            print("[DEBUG] [get_routes] Ranking non-transit routes...")
            routes = rank_routes(routes, commuter_type)
        else:
            print("[DEBUG] [get_routes] Processing transit-specific formatting and scores...")
            _mode_colors = {
                'train': '#27ae60', 'lrt1': '#27ae60', 'lrt-1': '#27ae60',
                'lrt2': '#2980b9', 'lrt-2': '#2980b9',
                'mrt3': '#f39c12', 'mrt-3': '#f39c12',
                'bus': '#16a085', 'jeepney': '#e67e22',
                'jeepney_bus': '#2980b9', 'train_jeepney': '#27ae60',
                'train_bus': '#16a085', 'transit': '#2980b9',
            }
            _ml_color = _mode_colors.get(_ct, '#2980b9')
            for i, r in enumerate(routes):
                r.setdefault('id', i)
                r.setdefault('mode_label', r.get('route_name', 'Route'))
                r.setdefault('mode_label_color', _ml_color)
                if 'safety_score' not in r or r.get('safety_score') is None:
                    print(f"[DEBUG][get_routes] Computing initial safety score for transit route {i}")
                    r['safety_score'] = _compute_safety_score(r, commuter_type)

        print("[DEBUG] [get_routes] Enriching routes with scores, fares, night safety...")
        enrich_routes_with_scores(routes, commuter_type)
        apply_night_safety(routes, commuter_type)
        attach_fares(routes, commuter_type)

        print("[DEBUG] [get_routes] Retrieving weather risk for routes...")
        t_weather = time.time()
        weather = get_weather_risk(orig_lat, orig_lon)
        apply_weather_to_routes(routes, weather, commuter_type)
        print(f"[DEBUG] [get_routes] Weather risk gathered and applied in {time.time() - t_weather:.4f}s")

        print("[DEBUG] [get_routes] Applying flood analysis (NOAH)...")
        t_flood = time.time()
        from risk_monitor.noah import apply_route_flood_analysis
        apply_route_flood_analysis(routes, weather)
        flood = get_flood_risk_at(orig_lat, orig_lon)
        print(f"[DEBUG] [get_routes] Flood analysis took {time.time() - t_flood:.4f}s. Orig Flood Risk: {flood.get('risk_level')}")

        print("[DEBUG] [get_routes] Applying community reports...")
        t_rep = time.time()
        apply_reports_to_routes(
            routes, chDB_perf,
            orig_lat, orig_lon, dest_lat, dest_lon,
        )
        print(f"[DEBUG] [get_routes] Community reports application took {time.time() - t_rep:.4f}s")

        print("[DEBUG] [get_routes] Analyzing crime risk for routes...")
        t_crime = time.time()
        from risk_monitor.crime_data import (
            get_crime_risk_with_reports, apply_crime_both_ends,
            scan_route_crime_zones, apply_route_crime_to_routes,
        )
        orig_crime = get_crime_risk_with_reports(orig_lat, orig_lon, origin_text or "", chDB_perf)
        dest_crime = get_crime_risk_with_reports(dest_lat, dest_lon, dest_text or "", chDB_perf)

        for route in routes:
            wps =[]
            if route.get("segments"):
                for seg in route["segments"]:
                    c = seg.get("coords", [])
                    if c and isinstance(c[0], list) and isinstance(c[0][0], list):
                        for sub in c:
                            wps.extend(sub)
                    else:
                        wps.extend(c)
            if not wps and route.get("coords"):
                wps = route["coords"]
            route["route_crime_zones"] = scan_route_crime_zones(wps)

        apply_crime_both_ends(routes, orig_crime, dest_crime, commuter_type)
        apply_route_crime_to_routes(routes, commuter_type)
        print(f"[DEBUG] [get_routes] Crime risk analysis completed in {time.time() - t_crime:.4f}s")

        # ── Real-time incidents (GDACS, NDRRMC, ReliefWeb) ────────────────
        print("[DEBUG] [get_routes] Applying real-time incidents...")
        t_inc = time.time()
        try:
            active_incidents = get_active_incidents()
            apply_incidents_to_routes(
                routes, active_incidents,
                orig_lat, orig_lon, dest_lat, dest_lon,
            )
            nav_response["incidents"] = get_incidents_map_data(active_incidents)
            print(f"[DEBUG][get_routes] Gathered {len(active_incidents)} real-time incidents.")
        except Exception as _ie:
            print(f"[DEBUG] [get_routes] [incidents] pipeline error: {_ie}")
            nav_response["incidents"] = []
        print(f"[DEBUG][get_routes] Incidents logic took {time.time() - t_inc:.4f}s")

        # ── MMDA: number coding + road closures ───────────────────────────
        print("[DEBUG][get_routes] Processing MMDA rules...")
        t_mmda = time.time()
        try:
            plate_raw = data.get("plate_last_digit")
            plate_digit = int(plate_raw) if plate_raw is not None else None
            apply_mmda_to_routes(routes, plate_digit)
            mmda_closures = get_road_closures()
            mmda_coding   = get_number_coding(plate_digit) if plate_digit is not None else None
            nav_response["mmda_banner"] = get_mmda_banner_html(mmda_coding, mmda_closures)
            nav_response["mmda_coding"] = mmda_coding
            nav_response["mmda_closures_count"] = len(mmda_closures)
        except Exception as _me:
            print(f"[DEBUG] [get_routes] [mmda] pipeline error: {_me}")
            nav_response["mmda_banner"] = ""
        print(f"[DEBUG] [get_routes] MMDA logic took {time.time() - t_mmda:.4f}s")

        # ── PHIVOLCS: seismic risk ─────────────────────────────────────────
        print("[DEBUG] [get_routes] Processing PHIVOLCS seismic data...")
        t_seismic = time.time()
        try:
            earthquakes = get_recent_earthquakes(hours_back=12)
            apply_seismic_to_routes(routes, earthquakes)
            nav_response["seismic_banner"] = get_seismic_banner_html(earthquakes)
            nav_response["epicenter_js"]   = get_epicenter_map_js(earthquakes)
            nav_response["earthquakes"]    =[
                {
                    "magnitude": e["magnitude"],
                    "place":     e["place"],
                    "severity":  e["severity"],
                    "time_pht":  e["time_pht"],
                    "tsunami":   e["tsunami"],
                    # ── Flutter needs these to build HotspotModel circles ──
                    "lat":       e["lat"],
                    "lon":       e["lon"],
                    "radius_km": e["radius_km"],
                    "color":     e["color"],
                }
                for e in earthquakes
            ]
        except Exception as _pe:
            print(f"[DEBUG][get_routes] [phivolcs] pipeline error: {_pe}")
            nav_response["seismic_banner"] = ""
            nav_response["epicenter_js"]   = ""
        print(f"[DEBUG] [get_routes] Seismic logic took {time.time() - t_seismic:.4f}s")

        print("[DEBUG] [get_routes] Initializing safe_spots_js as empty (loaded via /api/safe-spots/route)...")
        nav_response['safe_spots_js'] = ''

        # ── Vulnerable commuter profile ───────────────────────────────────
        print("[DEBUG][get_routes] Processing vulnerable profile...")
        t_vuln = time.time()
        try:
            profile = data.get("vulnerable_profile", "")
            if profile and profile in PROFILES:
                print(f"[DEBUG] [get_routes] Profile found: '{profile}'. Applying to routes.")
                apply_vulnerable_profile_to_routes(routes, profile, weather)
                from risk_monitor.vulnerable_profiles import get_infrastructure_warnings
                for route in routes:
                    coords = get_flat_route_coords(route)
                    infra_warns = get_infrastructure_warnings(profile, coords)
                    route.setdefault("profile_warnings", []).extend(infra_warns)
                nav_response["profile_badge"] = get_profile_badge_html(profile)
            else:
                nav_response["profile_badge"] = ""
        except Exception as _vpe:
            print(f"[DEBUG] [get_routes] [vulnerable_profiles] pipeline error: {_vpe}")
            nav_response["profile_badge"] = ""
        print(f"[DEBUG] [get_routes] Vulnerable profile logic took {time.time() - t_vuln:.4f}s")

        # ── Color each route by safety score ──────────────────────────────
        print("[DEBUG] [get_routes] Resolving route colors based on safety scores...")
        def _safety_to_color(score):
            if score >= 80: return '#27ae60'   # green
            if score >= 65: return '#f39c12'   # amber
            if score >= 50: return '#e67e22'   # orange
            return '#e74c3c'                   # red

        for idx, route in enumerate(routes):
            route_score = route.get('safety_score', 75)
            route['color'] = _safety_to_color(route_score)
            print(f"[DEBUG] [get_routes] Route {idx} score is {route_score}, color is {route['color']}")

        # Save to route history
        if 'user' in session:
            print(f"[DEBUG] [get_routes] Saving route history for user '{session['user']}'...")
            orig_label = origin_text or f"{orig_lat:.5f}, {orig_lon:.5f}"
            dest_label = dest_text   or f"{dest_lat:.5f}, {dest_lon:.5f}"
            save_route_history(
                chDB_perf, session['user'],
                orig_label, dest_label, commuter_type, len(routes)
            )
            print("[DEBUG] [get_routes] Route history saved.")

        nav_response["routes"] = routes

        # ── Include resolved coordinates so frontend can place A/B markers ─
        nav_response["orig_lat"]  = orig_lat
        nav_response["orig_lon"]  = orig_lon
        nav_response["dest_lat"]  = dest_lat
        nav_response["dest_lon"]  = dest_lon
        nav_response["orig_text"] = origin_text or ""
        nav_response["dest_text"] = dest_text   or ""

        # ── Attach live banners to API response ───────────────────────────
        print("[DEBUG][get_routes] Constructing final live banners for JSON response...")
        from risk_monitor.weather import get_weather_banner_html as _wbh
        from risk_monitor.noah   import get_flood_warning_html  as _fwh
        nav_response["weather_banner"] = _wbh(weather, commuter_type)
        nav_response["flood_banner"]   = _fwh(flood, weather)  # Pass weather to check if raining
        nav_response["weather_risk"]   = weather.get("risk_level", "clear")
        nav_response["flood_risk"]     = flood.get("risk_level",   "none")
        print(f"[DEBUG] [get_routes] Total enrichment pipeline took {time.time() - t_enrich_total:.4f}s")

    print(f"[DEBUG][get_routes] Endpoint returning response in {time.time() - t_route_start:.4f}s total.")
    return jsonify(nav_response)

# ══════════════════════════════════════════════════════════════════════════════
#  COMMUNITY REPORTS
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/incidents')
def api_incidents():
    t_start = time.time()
    print("[DEBUG][api_incidents] Handling request for real-time incidents overlay.")
    try:
        incidents = get_active_incidents()
        print(f"[DEBUG] [api_incidents] Returned {len(incidents)} incidents. Processing map data.")
        result = get_incidents_map_data(incidents)
        print(f"[DEBUG] [api_incidents] Request finished successfully in {time.time() - t_start:.4f}s")
        return jsonify(result)
    except Exception as e:
        print(f"[DEBUG][api_incidents] Exception: {e}")
        return jsonify([])


@app.route('/report', methods=['POST'])
def report():
    t_start = time.time()
    print("[DEBUG] [report] Receiving community report POST...")
    if 'user' not in session:
        print("[DEBUG] [report] User unauthorized. Rejecting.")
        return ('Unauthorized', 401)
    try:
        rtype = request.form.get('report_type', '')
        lat   = float(request.form.get('lat', 0))
        lon   = float(request.form.get('lon', 0))
        desc  = request.form.get('description', '')
        print(f"[DEBUG] [report] Form data -> user: {session['user']}, rtype: {rtype}, lat: {lat}, lon: {lon}, desc: '{desc}'")
        
        result = submit_report(chDB_perf, session['user'], rtype, lat, lon, desc)
        print(f"[DEBUG] [report] submit_report result: {result}")
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
           request.content_type == 'application/x-www-form-urlencoded':
            print("[DEBUG][report] Returning JSON response for XHR.")
            return jsonify(result)
        
        print("[DEBUG][report] Flashing message and redirecting to home.")
        flash(result['message'])
        print(f"[DEBUG] [report] Done in {time.time() - t_start:.4f}s")
        return redirect(url_for('home'))
    except Exception as e:
        print(f"[DEBUG][report] Exception: {e}")
        return jsonify({'ok': False, 'message': str(e)}), 400


@app.route('/api/reports', methods=['GET'])
def api_reports():
    t_start = time.time()
    print("[DEBUG] [api_reports] Fetching active community reports...")
    reports = get_all_active_reports(chDB_perf, limit=100)
    print(f"[DEBUG] [api_reports] Returning {len(reports)} reports in {time.time() - t_start:.4f}s")
    return jsonify(reports)


@app.route('/api/reports/confirm', methods=['POST'])
def api_confirm_report():
    t_start = time.time()
    print("[DEBUG] [api_confirm_report] Hit /api/reports/confirm endpoint.")
    auth_header = request.headers.get('Authorization', '')
    token = auth_header[7:] if auth_header.startswith('Bearer ') else None
    username = token if token else session.get('user')
    if not username:
        print("[DEBUG] [api_confirm_report] Unauthorized. Rejecting.")
        return jsonify({'ok': False, 'message': 'Login required'}), 401
    
    report_id = request.json.get('report_id')
    print(f"[DEBUG] [api_confirm_report] User '{username}' confirming report_id {report_id}")
    
    result = confirm_report(chDB_perf, int(report_id), username)
    print(f"[DEBUG] [api_confirm_report] confirm_report result: {result}. Took {time.time() - t_start:.4f}s")
    return jsonify(result)


@app.route('/api/report', methods=['POST'])
def api_report_json():
    """JSON API endpoint for Flutter community report submission."""
    t_start = time.time()
    print("[DEBUG] [api_report_json] Receiving JSON community report POST...")
    auth_header = request.headers.get('Authorization', '')
    token = auth_header[7:] if auth_header.startswith('Bearer ') else None
    username = token if token else session.get('user')
    if not username:
        print("[DEBUG] [api_report_json] Unauthorized. Rejecting.")
        return jsonify({'ok': False, 'message': 'Login required'}), 401
    try:
        data = request.get_json() or {}
        rtype = data.get('report_type', '')
        lat   = float(data.get('lat', 0))
        lon   = float(data.get('lon', 0))
        desc  = data.get('description', '')
        print(f"[DEBUG] [api_report_json] Data -> user: {username}, rtype: {rtype}, lat: {lat}, lon: {lon}, desc: '{desc}'")
        result = submit_report(chDB_perf, username, rtype, lat, lon, desc)
        print(f"[DEBUG] [api_report_json] submit_report result: {result}. Took {time.time() - t_start:.4f}s")
        return jsonify(result)
    except Exception as e:
        print(f"[DEBUG] [api_report_json] Exception: {e}")
        return jsonify({'ok': False, 'message': str(e)}), 400


@app.route('/api/report-types', methods=['GET'])
def api_report_types():
    print("[DEBUG] [api_report_types] Fetching report type options...")
    from risk_monitor.community_reports import get_report_type_options_for_api
    return jsonify(get_report_type_options_for_api())


@app.route('/community', methods=['GET'])
def community():
    t_start = time.time()
    print("[DEBUG] [community] Accessing /community view.")
    if 'user' not in session:
        print("[DEBUG] [community] Redirecting unauthorized user to login.")
        return redirect(url_for('login'))
        
    print("[DEBUG] [community] Fetching active reports and weather for Manila baseline...")
    reports = get_all_active_reports(chDB_perf, limit=50)
    weather = get_weather_risk(14.5995, 120.9842)
    print(f"[DEBUG] [community] Rendering template with {len(reports)} reports. Elapsed: {time.time() - t_start:.4f}s")
    
    return render_template(
        'community.html',
        user=session['user'],
        username=session['user'],
        reports=reports,
        weather=weather,
        REPORT_TYPES=REPORT_TYPES,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  USER SETTINGS + HISTORY
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    t_start = time.time()
    print(f"[DEBUG] [settings] Method: {request.method}")
    if 'user' not in session:
        return redirect(url_for('login'))
        
    flash_msg = ''
    if request.method == 'POST':
        print("[DEBUG] [settings] Processing form POST.")
        settings_data = extract_settings_from_form(request.form)
        print(f"[DEBUG] [settings] Extracted settings: {settings_data}")
        save_user_settings(chDB_perf, session['user'], settings_data)
        
        if request.form.get('display_name') is not None:
            print("[DEBUG] [settings] Saving user profile display name & email...")
            save_user_profile(
                chDB_perf, session['user'],
                request.form.get('display_name', ''),
                request.form.get('email', ''),
            )
        flash_msg = 'Settings saved.'

    print("[DEBUG] [settings] Fetching user settings and profile state...")
    user_settings = get_user_settings(chDB_perf, session['user'])
    profile       = get_user_profile(chDB_perf, session['user'])
    try:
        print("[DEBUG] [settings] Fetching trusted contacts HTML...")
        _contacts          = get_trusted_contacts(chDB_perf, session['user'])
        sos_contacts_html  = get_trusted_contacts_settings_html(_contacts)
    except Exception as e:
        print(f"[DEBUG] [settings] Failed trusted contacts HTML: {e}")
        sos_contacts_html  = ""
        
    print(f"[DEBUG] [settings] Constructing response in {time.time() - t_start:.4f}s")
    return get_settings_page_html(user_settings, profile, flash_msg, sos_contacts_html)


@app.route('/history')
def history():
    t_start = time.time()
    print("[DEBUG] [history] Accessing user route history...")
    if 'user' not in session:
        return redirect(url_for('login'))
        
    hist = get_route_history(chDB_perf, session['user'])
    print(f"[DEBUG] [history] Fetched {len(hist)} history items for '{session['user']}' in {time.time() - t_start:.4f}s")
    return get_history_page_html(hist, session['user'])


@app.route('/history/clear', methods=['POST'])
def history_clear():
    t_start = time.time()
    print("[DEBUG] [history_clear] Action invoked.")
    if 'user' not in session:
        return redirect(url_for('login'))
        
    clear_route_history(chDB_perf, session['user'])
    print(f"[DEBUG][history_clear] History cleared for '{session['user']}' in {time.time() - t_start:.4f}s")
    flash('History cleared.')
    return redirect(url_for('history'))


@app.route('/account/password', methods=['POST'])
def change_password_route():
    t_start = time.time()
    print("[DEBUG] [change_password_route] Password change invoked.")
    if 'user' not in session:
        return redirect(url_for('login'))
        
    result = change_password(
        chDB_perf, session['user'],
        request.form.get('old_password', ''),
        request.form.get('new_password', ''),
    )
    print(f"[DEBUG] [change_password_route] Result: {result}. Time: {time.time() - t_start:.4f}s")
    flash(result['message'])
    return redirect(url_for('settings'))


# ══════════════════════════════════════════════════════════════════════════════
#  SAFETY API
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/safety', methods=['GET'])
def api_safety():
    """Returns weather, flood, and community report risk for a location."""
    t_start = time.time()
    print(f"[DEBUG] [api_safety] Safety API invoked. Args: {request.args}")
    try:
        lat = float(request.args.get('lat', 14.5995))
        lon = float(request.args.get('lon', 120.9842))
    except (TypeError, ValueError):
        print("[DEBUG] [api_safety] Invalid coordinates. Returning 400 error.")
        return jsonify({'error': 'Invalid coordinates'}), 400

    print(f"[DEBUG] [api_safety] Requesting risk metrics for lat={lat}, lon={lon}")
    
    t_w = time.time()
    weather = get_weather_risk(lat, lon)
    print(f"[DEBUG] [api_safety] Weather retrieved in {time.time() - t_w:.4f}s")

    t_f = time.time()
    flood   = get_flood_risk_at(lat, lon)
    print(f"[DEBUG] [api_safety] Flood retrieved in {time.time() - t_f:.4f}s")

    t_p = time.time()
    penalty = get_area_safety_penalty(chDB_perf, lat, lon)
    print(f"[DEBUG] [api_safety] Area penalty computed in {time.time() - t_p:.4f}s")

    t_r = time.time()
    reports = get_all_active_reports(chDB_perf, limit=50)
    print(f"[DEBUG] [api_safety] Active reports fetched in {time.time() - t_r:.4f}s")

    t_c = time.time()
    crime = get_crime_risk_for_area(lat, lon, "")
    print(f"[DEBUG] [api_safety] Crime risk resolved in {time.time() - t_c:.4f}s")

    # MMDA + Seismic
    try:
        mmda_closures = get_road_closures()
    except Exception as e:
        print(f"[DEBUG][api_safety] MMDA Exception: {e}")
        mmda_closures =[]
    try:
        quakes = get_recent_earthquakes(hours_back=12)
    except Exception as e:
        print(f"[DEBUG] [api_safety] Quakes Exception: {e}")
        quakes =[]

    print(f"[DEBUG] [api_safety] Finalizing JSON response payload. Total time: {time.time() - t_start:.4f}s")
    return jsonify({
        'ok': True,   # ── Flutter checks this in fetchSafetyOverlays()
        'weather': {
            'risk_level':   weather.get('risk_level'),
            'description':  weather.get('description'),
            'temp_c':       weather.get('temp_c'),
            'feels_like_c': weather.get('feels_like_c'),
            'humidity_pct': weather.get('humidity_pct'),
            'wind_kph':     weather.get('wind_kph'),
            'rain_mm':      weather.get('rain_mm'),
            'color':        weather.get('color'),
        },
        'flood': {
            'risk_level': flood.get('risk_level'),
            'label':      flood.get('label'),
            'color':      flood.get('color'),
            'penalty':    flood.get('penalty'),
        },
        'crime': {
            'risk_level': crime.get('risk_level'),
            'area':       crime.get('area'),
            'warning':    crime.get('warning'),
            'penalty':    crime.get('penalty'),
        },
        'mmda': {
            'closures_count': len(mmda_closures),
            'closures':       mmda_closures[:5],
        },
        'seismic': {
            'count':      len(quakes),
            'earthquakes': [
                {
                    'magnitude': e['magnitude'],
                    'place':     e['place'],
                    'severity':  e['severity'],
                    'tsunami':   e['tsunami'],
                    # Flutter HotspotModel needs these for map circles
                    'lat':       e['lat'],
                    'lon':       e['lon'],
                    'radius_km': e['radius_km'],
                    'color':     e['color'],
                }
                for e in quakes[:3]
            ],
        },
        'community_penalty': penalty,
        'reports': [
            {
                'id':            r['id'],
                'type':          r['report_type'],
                'icon':          r['icon'],
                'label':         r['label'],
                'color':         r['color'],
                'lat':           r['lat'],
                'lon':           r['lon'],
                'description':   r['description'],
                'confirmations': r['confirmations'],
                'verified':      r['verified'],
                'reported_at':   r['reported_at'],
            }
            for r in reports
        ],
    })


# ══════════════════════════════════════════════════════════════════════════════
#  COMMUNITY SCREEN — Weather + News endpoints
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/community/weather', methods=['GET'])
def api_community_weather():
    """Current weather + 5-day forecast + flood status for the community screen.
    GET /api/community/weather?lat=&lon=
    """
    try:
        lat = float(request.args.get('lat', 14.5995))
        lon = float(request.args.get('lon', 120.9842))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'Invalid coordinates'}), 400

    weather  = get_weather_risk(lat, lon)
    flood    = get_flood_risk_at(lat, lon)
    forecast = get_forecast(lat, lon, days=5)

    flood_active = flood.get('risk_level', 'none') not in ('none', 'low')

    return jsonify({
        'ok': True,
        'current': {
            'description':  weather.get('description', 'Clear sky'),
            'risk_level':   weather.get('risk_level', 'clear'),
            'temp_c':       weather.get('temp_c', 0),
            'feels_like_c': weather.get('feels_like_c', 0),
            'humidity_pct': weather.get('humidity_pct', 0),
            'wind_kph':     weather.get('wind_kph', 0),
            'rain_mm':      weather.get('rain_mm', 0),
            'color':        weather.get('color', '#7f8c8d'),
            'fetched_at':   weather.get('fetched_at', ''),
        },
        'flood': {
            'active':     flood_active,
            'risk_level': flood.get('risk_level', 'none'),
            'label':      flood.get('label', ''),
            'color':      flood.get('color', '#7f8c8d'),
        },
        'forecast': forecast,
    })


@app.route('/api/community/news', methods=['GET'])
def api_community_news():
    """Official-source news items for the community screen.
    Aggregates: typhoon signals (PAGASA), MMDA road closures,
    and real-time incidents (GDACS/USGS/PHIVOLCS).
    GET /api/community/news
    Returns: { ok, items: [ {source, headline, summary, url, published_at, severity} ] }
    """
    from datetime import timezone, timedelta
    _PHT = timezone(timedelta(hours=8))
    now_str = datetime.now(_PHT).strftime('%Y-%m-%d %H:%M PHT')

    items = []

    # 1. PAGASA typhoon signal
    try:
        typhoon = get_typhoon_signal()
        if typhoon and typhoon.get('signal', 0) > 0:
            items.append({
                'source':       'PAGASA',
                'headline':     f"Typhoon Signal #{typhoon.get('signal')} — {typhoon.get('name', 'Active')}",
                'summary':      typhoon.get('description', 'Tropical Cyclone Wind Signal raised.'),
                'url':          'https://www.pagasa.dost.gov.ph/',
                'published_at': typhoon.get('issued_at', now_str),
                'severity':     'high' if typhoon.get('signal', 0) >= 2 else 'moderate',
            })
    except Exception as _e:
        print(f'[api_community_news] typhoon error: {_e}')

    # 2. MMDA road closures
    try:
        closures = get_road_closures()
        for c in closures[:3]:
            items.append({
                'source':       'MMDA',
                'headline':     c.get('title', 'Road closure advisory'),
                'summary':      c.get('description', ''),
                'url':          'https://www.mmda.gov.ph/',
                'published_at': c.get('date', now_str),
                'severity':     'moderate',
            })
    except Exception as _e:
        print(f'[api_community_news] mmda error: {_e}')

    # 3. Real-time incidents (GDACS / USGS / PHIVOLCS)
    try:
        incidents = get_active_incidents(ph_only=True)
        _src_map = {
            'gdacs':    'NDRRMC',
            'usgs':     'PHIVOLCS',
            'phivolcs': 'PHIVOLCS',
            'mmda':     'MMDA',
            'pagasa':   'PAGASA',
        }
        for inc in incidents[:6]:
            raw_src   = inc.get('source', 'NDRRMC').lower()
            src_label = _src_map.get(raw_src, inc.get('source', 'NDRRMC'))
            items.append({
                'source':       src_label,
                'headline':     inc.get('title', 'Hazard alert'),
                'summary':      inc.get('description', ''),
                'url':          inc.get('source_url', ''),
                'published_at': inc.get('reported_at', now_str),
                'severity':     inc.get('severity', 'moderate'),
            })
    except Exception as _e:
        print(f'[api_community_news] incidents error: {_e}')

    return jsonify({'ok': True, 'items': items})


# ══════════════════════════════════════════════════════════════════════════════
#  NOTIFICATIONS  (polled every ~30 s by the Flutter app)
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/notifications', methods=['GET'])
def api_notifications():
    """Aggregate real-time notifications for the Flutter community screen.

    GET /api/notifications?since=<unix_epoch_seconds>

    Returns:
      { ok: true, notifications: [ {id, body, type, created_at, created_epoch} ] }

    ``since`` is optional.  When provided only notifications whose
    ``created_epoch`` is strictly greater than ``since`` are returned, so the
    app can do efficient incremental polls.

    Notification types (map to icons on the client):
      flood | typhoon | seismic | fire | crime | verify | info
    """
    from datetime import datetime, timezone, timedelta
    _PHT = timezone(timedelta(hours=8))

    try:
        since_epoch = float(request.args.get('since', 0))
    except (TypeError, ValueError):
        since_epoch = 0.0

    notifications = []

    def _epoch(dt_str: str) -> float:
        """Parse an ISO/PHT date string to a UTC epoch float, or return now."""
        try:
            for fmt in ('%Y-%m-%d %H:%M PHT', '%Y-%m-%dT%H:%M:%S',
                        '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
                try:
                    dt = datetime.strptime(dt_str, fmt)
                    if fmt.endswith('PHT'):
                        dt = dt.replace(tzinfo=_PHT)
                    else:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt.timestamp()
                except ValueError:
                    continue
        except Exception:
            pass
        return datetime.now(timezone.utc).timestamp()

    now_epoch = datetime.now(timezone.utc).timestamp()

    # ── 1. Typhoon signal ────────────────────────────────────────────────────
    try:
        typhoon = get_typhoon_signal()
        if typhoon and typhoon.get('signal', 0) > 0:
            sig = typhoon.get('signal', 1)
            name = typhoon.get('name', 'Active Typhoon')
            ep = _epoch(typhoon.get('issued_at', ''))
            notifications.append({
                'id':            f"typhoon_{sig}_{name.replace(' ', '_')}",
                'body':          f"Typhoon Signal #{sig} raised — {name}",
                'type':          'typhoon',
                'created_at':    typhoon.get('issued_at', ''),
                'created_epoch': ep,
            })
    except Exception as _e:
        print(f'[api_notifications] typhoon error: {_e}')

    # ── 2. Flood / Weather alert ─────────────────────────────────────────────
    try:
        flood = get_flood_risk_at(14.5995, 120.9842)
        risk = flood.get('risk_level', 'none')
        if risk not in ('none', 'low'):
            label = flood.get('label', 'Flood risk elevated')
            ep = now_epoch - 300  # treat as 5-min-old alert
            notifications.append({
                'id':            f"flood_{risk}",
                'body':          f"High flood risk detected — {label}",
                'type':          'flood',
                'created_at':    datetime.fromtimestamp(ep, _PHT).strftime('%Y-%m-%d %H:%M PHT'),
                'created_epoch': ep,
            })
    except Exception as _e:
        print(f'[api_notifications] flood error: {_e}')

    # ── 3. MMDA road closures ────────────────────────────────────────────────
    try:
        closures = get_road_closures()
        for c in closures[:2]:
            title = c.get('title', 'Road closure advisory')
            ep = _epoch(c.get('date', ''))
            notifications.append({
                'id':            f"mmda_{abs(hash(title)) % 100000}",
                'body':          title,
                'type':          'info',
                'created_at':    c.get('date', ''),
                'created_epoch': ep,
            })
    except Exception as _e:
        print(f'[api_notifications] mmda error: {_e}')

    # ── 4. Seismic alerts ────────────────────────────────────────────────────
    try:
        quakes = get_recent_earthquakes(hours_back=12)
        for q in quakes[:2]:
            mag = q.get('magnitude', 0)
            place = q.get('place', 'Philippines')
            ep = _epoch(q.get('time', ''))
            tsunami = ' — TSUNAMI WARNING' if q.get('tsunami') else ''
            notifications.append({
                'id':            f"quake_M{mag}_{abs(hash(place)) % 100000}",
                'body':          f"M{mag} earthquake near {place}{tsunami}",
                'type':          'seismic',
                'created_at':    q.get('time', ''),
                'created_epoch': ep,
            })
    except Exception as _e:
        print(f'[api_notifications] seismic error: {_e}')

    # ── 5. Active incidents (GDACS / NDRRMC) ────────────────────────────────
    try:
        incidents = get_active_incidents(ph_only=True)
        for inc in incidents[:3]:
            itype = inc.get('type', 'fire').lower()
            ntype = 'fire' if 'fire' in itype else \
                    'flood' if 'flood' in itype else \
                    'crime' if 'crime' in itype else 'info'
            title = inc.get('title', 'Hazard alert')
            ep = _epoch(inc.get('reported_at', ''))
            notifications.append({
                'id':            f"incident_{abs(hash(title)) % 100000}",
                'body':          title,
                'type':          ntype,
                'created_at':    inc.get('reported_at', ''),
                'created_epoch': ep,
            })
    except Exception as _e:
        print(f'[api_notifications] incidents error: {_e}')

    # ── 6. Highly-confirmed community reports ───────────────────────────────
    try:
        reports = get_all_active_reports(chDB_perf, limit=20)
        for r in reports:
            confs = r.get('confirmations', 0)
            if confs >= 5:
                ep = _epoch(r.get('reported_at', ''))
                rtype = r.get('report_type', 'report').lower()
                ntype = 'flood' if 'flood' in rtype else \
                        'fire'  if 'fire'  in rtype else \
                        'crime' if 'crime' in rtype else 'verify'
                body = f"Community report verified by {confs} people — {r.get('description', '')[:60]}"
                notifications.append({
                    'id':            f"report_{r.get('id', 0)}",
                    'body':          body,
                    'type':          ntype,
                    'created_at':    r.get('reported_at', ''),
                    'created_epoch': ep,
                })
    except Exception as _e:
        print(f'[api_notifications] reports error: {_e}')

    # ── Sort newest first, apply ``since`` filter ────────────────────────────
    notifications.sort(key=lambda n: n['created_epoch'], reverse=True)
    if since_epoch > 0:
        notifications = [n for n in notifications if n['created_epoch'] > since_epoch]

    # Cap at 20 to keep response light
    notifications = notifications[:20]

    return jsonify({'ok': True, 'notifications': notifications})


# ══════════════════════════════════════════════════════════════════════════════
#  SOS / EMERGENCY
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/sos', methods=['POST'])
def api_sos():
    """Trigger SOS: log event, return share link + contact count."""
    t_start = time.time()
    print("[DEBUG] [api_sos] Processing SOS request...")
    auth_header = request.headers.get('Authorization', '')
    token = auth_header[7:] if auth_header.startswith('Bearer ') else None
    username = token if token else session.get('user')
    if not username:
        print("[DEBUG][api_sos] Unauthorized user.")
        return jsonify({'ok': False, 'message': 'Login required'}), 401
    try:
        body    = request.json or {}
        lat     = float(body.get('lat', 0))
        lon     = float(body.get('lon', 0))
        message = body.get('message', 'SOS from SafeRoute user')
        route_summary = body.get('route_summary', '')
        
        print(f"[DEBUG] [api_sos] SOS Data -> User: {username}, Lat: {lat}, Lon: {lon}, Message: '{message}', Route Summary: '{route_summary}'")
        result  = log_sos_event(chDB_perf, username, lat, lon, route_summary, message)
        
        print(f"[DEBUG][api_sos] SOS log event result: {result}. Took {time.time() - t_start:.4f}s")
        return jsonify(result)
    except Exception as e:
        print(f"[DEBUG][api_sos] Exception: {e}")
        return jsonify({'ok': False, 'message': str(e)}), 400


@app.route('/api/sos/contacts', methods=['GET'])
def api_sos_contacts_get():
    t_start = time.time()
    print("[DEBUG] [api_sos_contacts_get] Requesting SOS contacts.")
    auth_header = request.headers.get('Authorization', '')
    token = auth_header[7:] if auth_header.startswith('Bearer ') else None
    username = token if token else session.get('user')
    if not username:
        return jsonify({'ok': False, 'message': 'Login required'}), 401
    contacts = get_trusted_contacts(chDB_perf, username)
    print(f"[DEBUG][api_sos_contacts_get] Fetched {len(contacts)} contacts for user in {time.time() - t_start:.4f}s")
    return jsonify({'ok': True, 'contacts': contacts})


@app.route('/api/sos/contacts', methods=['POST'])
def api_sos_contacts_add():
    t_start = time.time()
    print("[DEBUG][api_sos_contacts_add] Adding SOS contact.")
    auth_header = request.headers.get('Authorization', '')
    token = auth_header[7:] if auth_header.startswith('Bearer ') else None
    username = token if token else session.get('user')
    if not username:
        return jsonify({'ok': False, 'message': 'Login required'}), 401
    try:
        body = request.json or {}
        name = body.get('name', '')
        c_type = body.get('contact_type', 'phone')
        c_val = body.get('contact_value', '')
        
        print(f"[DEBUG] [api_sos_contacts_add] Contact payload -> name: '{name}', type: '{c_type}', value: '{c_val}'")
        result = add_trusted_contact(
            chDB_perf, username,
            name, c_type, c_val
        )
        print(f"[DEBUG] [api_sos_contacts_add] Added contact. Result: {result}. Took {time.time() - t_start:.4f}s")
        return jsonify(result)
    except Exception as e:
        print(f"[DEBUG] [api_sos_contacts_add] Exception: {e}")
        return jsonify({'ok': False, 'message': str(e)}), 400


@app.route('/api/sos/contacts/<int:contact_id>', methods=['DELETE'])
def api_sos_contacts_delete(contact_id):
    t_start = time.time()
    print(f"[DEBUG] [api_sos_contacts_delete] Deleting contact ID {contact_id}.")
    auth_header = request.headers.get('Authorization', '')
    token = auth_header[7:] if auth_header.startswith('Bearer ') else None
    username = token if token else session.get('user')
    if not username:
        return jsonify({'ok': False, 'message': 'Login required'}), 401
        
    result = remove_trusted_contact(chDB_perf, username, contact_id)
    print(f"[DEBUG] [api_sos_contacts_delete] Deletion result: {result}. Took {time.time() - t_start:.4f}s")
    return jsonify(result)


# ══════════════════════════════════════════════════════════════════════════════
#  MMDA / PHIVOLCS live data endpoints
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/mmda', methods=['GET'])
def api_mmda():
    """Current number coding status + active road closures."""
    t_start = time.time()
    print("[DEBUG] [api_mmda] Fetching MMDA status...")
    try:
        plate_raw   = request.args.get('plate')
        plate_digit = int(plate_raw) % 10 if plate_raw and plate_raw.isdigit() else None
        print(f"[DEBUG] [api_mmda] Resolving for plate digit: {plate_digit}")
        
        coding   = get_number_coding(plate_digit) if plate_digit is not None else None
        closures = get_road_closures()
        print(f"[DEBUG] [api_mmda] MMDA data obtained. Closures count: {len(closures)}. Time: {time.time() - t_start:.4f}s")
        
        return jsonify({
            'coding':         coding,
            'closures':       closures,
            'mmda_banner':    get_mmda_banner_html(coding, closures),
            'closures_count': len(closures),
        })
    except Exception as e:
        print(f"[DEBUG] [api_mmda] Exception: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/phivolcs', methods=['GET'])
def api_phivolcs():
    """Recent Philippine earthquakes from USGS/PHIVOLCS."""
    t_start = time.time()
    print("[DEBUG][api_phivolcs] Fetching seismic data...")
    try:
        hours = int(request.args.get('hours', 12))
        quakes = get_recent_earthquakes(hours_back=hours)
        print(f"[DEBUG] [api_phivolcs] Fetched {len(quakes)} earthquakes in last {hours} hours. Took {time.time() - t_start:.4f}s")
        
        return jsonify({
            'earthquakes':    quakes,
            'count':          len(quakes),
            'seismic_banner': get_seismic_banner_html(quakes),
            'epicenter_js':   get_epicenter_map_js(quakes),
        })
    except Exception as e:
        print(f"[DEBUG] [api_phivolcs] Exception: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/safe-spots/flutter', methods=['GET'])
def api_safe_spots_flutter():
    """
    Safe spots for Flutter app — returns plain JSON, NOT Leaflet JS.
    Flutter calls this from fetchSafetyOverlays() and maps results to PoiModel.

    Query params:
        lat    (float)  — latitude
        lon    (float)  — longitude
        radius (int)    — search radius in metres (default 1500)

    Response:
        {
          "ok": true,
          "spots": [
            {
              "id":       "...",
              "name":     "Philippine General Hospital",
              "type":     "hospital",
              "label":    "Hospital",
              "icon":     "🏥",
              "color":    "#e74c3c",
              "lat":      14.5794,
              "lon":      120.9822,
              "address":  "...",
              "priority": 1,
              "dist_m":   340,
              "open_24h": false
            }, ...
          ]
        }
    """
    t_start = time.time()
    print("[DEBUG][api_safe_spots_flutter] Flutter safe-spots request received.")
    try:
        lat    = float(request.args.get('lat',    14.5995))
        lon    = float(request.args.get('lon',   120.9842))
        radius = int(request.args.get('radius',    1500))
        print(f"[DEBUG][api_safe_spots_flutter] lat={lat}, lon={lon}, radius={radius}")

        spots = get_safe_spots_near(lat, lon, radius_m=radius)
        print(f"[DEBUG][api_safe_spots_flutter] Returning {len(spots)} spots in {time.time()-t_start:.4f}s")
        return jsonify({'ok': True, 'spots': spots, 'count': len(spots)})
    except Exception as e:
        print(f"[DEBUG][api_safe_spots_flutter] Exception: {e}")
        return jsonify({'ok': False, 'error': str(e), 'spots': []}), 500


@app.route('/api/safe-spots', methods=['GET'])
def api_safe_spots():
    """Safe spots (police, hospitals, fire stations, etc.) near a coordinate."""
    t_start = time.time()
    print("[DEBUG][api_safe_spots] Incoming query...")
    try:
        lat    = float(request.args.get('lat', 14.5995))
        lon    = float(request.args.get('lon', 120.9842))
        radius = int(request.args.get('radius', 1500))
        print(f"[DEBUG] [api_safe_spots] Parameters -> lat: {lat}, lon: {lon}, radius: {radius}")
        spots  = get_safe_spots_near(lat, lon, radius_m=radius)
        print(f"[DEBUG][api_safe_spots] Retrieved {len(spots)} spots in {time.time() - t_start:.4f}s")
        return jsonify({'spots': spots, 'count': len(spots)})
    except Exception as e:
        print(f"[DEBUG] [api_safe_spots] Exception: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/safe-spots/route', methods=['POST'])
def api_safe_spots_for_route():
    """
    On-demand safe spots for a specific route.
    Called when the user toggles safe spots ON for a selected route.
    Accepts a route object (coords + segments) and returns Leaflet JS.
    """
    t_start = time.time()
    print("[DEBUG][api_safe_spots_for_route] Generating safe spots script for route JSON...")
    try:
        route = request.json or {}
        print(f"[DEBUG] [api_safe_spots_for_route] Route structure length: {len(str(route))} chars")
        js = get_route_safe_spots_js(route)
        print(f"[DEBUG] [api_safe_spots_for_route] Generated JS payload size: {len(js)} chars. Took {time.time() - t_start:.4f}s")
        return jsonify({'safe_spots_js': js, 'ok': True})
    except Exception as e:
        print(f"[DEBUG] [api_safe_spots_for_route] Exception: {e}")
        return jsonify({'error': str(e), 'ok': False, 'safe_spots_js': ''}), 500


@app.route('/api/safe-spots/batch', methods=['POST'])
def api_safe_spots_batch():
    """
    Fetch safe spots for a batch of sample coordinates in parallel.
    Called by the frontend safe spots toggle for fast, progressive loading.
    Body: { "coords": [[lat, lon], ...], "radius": 600 }
    Returns: { "spots": [...], "ok": true }
    """
    t_start = time.time()
    print("[DEBUG][api_safe_spots_batch] Fetching safe spots in batch...")
    try:
        body     = request.json or {}
        coords   = body.get('coords',[])
        radius   = int(body.get('radius', 600))
        
        print(f"[DEBUG][api_safe_spots_batch] Incoming {len(coords)} coordinates, radius {radius}.")
        # Safety cap: max 12 sample points per request
        coords   = coords[:12]
        print(f"[DEBUG][api_safe_spots_batch] Processing capped list of {len(coords)} coordinates.")
        
        spots    = get_spots_for_coords(coords, radius_m=radius)
        print(f"[DEBUG][api_safe_spots_batch] Fetched {len(spots)} cumulative spots in {time.time() - t_start:.4f}s")
        return jsonify({'spots': spots, 'count': len(spots), 'ok': True})
    except Exception as e:
        print(f"[DEBUG][api_safe_spots_batch] Exception: {e}")
        return jsonify({'error': str(e), 'ok': False, 'spots':[]}), 500


# ══════════════════════════════════════════════════════════════════════════════
#  RSS FEED
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/rss')
def rss_feed():
    """
    Combined RSS 2.0 feed of community reports + weather/typhoon alerts.

    Query params:
        lat, lon   — coordinates for weather risk (default: Manila)
        type       — "all" (default) | "reports" | "weather"
    """
    t_start = time.time()
    print("[DEBUG] [rss_feed] Generating RSS feed...")
    from flask import Response, request as _req
    try:
        lat       = float(_req.args.get('lat', 14.5995))
        lon       = float(_req.args.get('lon', 120.9842))
    except (TypeError, ValueError):
        lat, lon  = 14.5995, 120.9842

    feed_type = _req.args.get('type', 'all')
    if feed_type not in ('all', 'reports', 'weather'):
        feed_type = 'all'

    print(f"[DEBUG][rss_feed] Feed type '{feed_type}', coordinate reference ({lat}, {lon})")
    
    t_r = time.time()
    reports = get_all_active_reports(chDB_perf, limit=100)
    print(f"[DEBUG] [rss_feed] Fetched {len(reports)} reports in {time.time() - t_r:.4f}s")
    
    typhoon = get_typhoon_signal()
    weather = get_weather_risk(lat, lon)

    xml_str = build_rss(
        reports=reports,
        typhoon=typhoon,
        weather=weather,
        lat=lat,
        lon=lon,
        feed_type=feed_type,
    )

    print(f"[DEBUG] [rss_feed] Generated XML output size: {len(xml_str)} chars in {time.time() - t_start:.4f}s")
    return Response(xml_str, mimetype='application/rss+xml; charset=utf-8')

if __name__ == '__main__':
    print("[DEBUG] [MAIN] Starting Flask app loop via main block...")
    app.run(debug=True, host='0.0.0.0', port=5000)