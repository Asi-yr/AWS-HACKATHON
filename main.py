from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from navigation import geocode_location, get_navigation_data
from branca.element import Element
from folium import plugins
import requests
import folium

USE_MYSQL = False

if USE_MYSQL:
    from db_opt import msql
    chDB_perf = msql()
else:
    from db_opt import nsql
    chDB_perf = nsql()

chDB_perf.init_db()
app = Flask(__name__)
app.secret_key = 'saferoute_super_secret_key'


# ── Map factory ───────────────────────────────────────────────────────────────

def get_base_map(center_lat=14.605, center_lon=120.985, zoom=13):
    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom, tiles="OpenStreetMap")
    plugins.LocateControl(auto_start=False, strings={"title": "Use my current location"}).add_to(m)

    click_js = """
    <script>
        var originMarker = null;
        var destMarker   = null;
        var greenIcon = new L.Icon({
            iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png',
            shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
            iconSize: [25,41], iconAnchor: [12,41], popupAnchor: [1,-34], shadowSize: [41,41]
        });
        var redIcon = new L.Icon({
            iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
            shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
            iconSize: [25,41], iconAnchor: [12,41], popupAnchor: [1,-34], shadowSize: [41,41]
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
    return m


# ── Route renderers ───────────────────────────────────────────────────────────

def _draw_train_route(route, m):
    """
    Draw track polyline + ordered station pins for a train route.
    !! DO NOT modify the station/track rendering logic here without
       also verifying against get_osm_railway_geometry() in navigation.py.
       The station list is ordered and trimmed there — this just renders it.
    """
    route_layer = folium.FeatureGroup(name=route['name'])
    line_color  = route.get('color', '#8e44ad')

    # Track polyline (dashed to feel like rail tracks)
    for segment in route.get('coords', []):
        if len(segment) >= 2:
            folium.PolyLine(
                locations=segment,
                color=line_color,
                weight=5,
                opacity=0.85,
                dash_array='10 6',
                tooltip=route['name'],
            ).add_to(route_layer)

    # Ordered station pins — from OSM relation member sequence
    stations = route.get('stations', [])
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


def _draw_road_route(route, m):
    """Draw a standard OSRM road/bus/car polyline (no multi-leg support needed)."""
    route_layer = folium.FeatureGroup(name=route['name'])
    folium.PolyLine(
        locations=route['coords'],
        color=route['color'],
        weight=7 if route['id'] == 0 else 5,
        opacity=0.9,
        tooltip=f"{route['name']} ({route.get('time', '')})",
    ).add_to(route_layer)
    route_layer.add_to(m)


def _draw_jeepney_route(route, m):
    """
    Draw a multi-leg jeepney route: walk -> jeepney -> walk.

    Segment types and their visual treatment:
      'walk'    -- dashed grey polyline (OSRM foot geometry)
      'jeepney' -- solid coloured polyline (OSM relation geometry)
                   + ordered stop pins from route['stations']
    """
    route_layer = folium.FeatureGroup(name=route['name'])
    segments    = route.get('segments', [])
    line_color  = route['color']

    # If no segment list, fall back to drawing raw coords
    if not segments:
        folium.PolyLine(
            locations=route['coords'],
            color=line_color,
            weight=5,
            opacity=0.9,
            tooltip=route['name'],
        ).add_to(route_layer)
        route_layer.add_to(m)
        return

    for seg in segments:
        coords = seg.get('coords', [])
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
                tooltip=f"Jeepney: {seg.get('label', route['name'])} ({route.get('time', '')})",
            ).add_to(route_layer)

            # Ordered stop pins (same style as train stations)
            stations = route.get('stations', [])
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
                    tooltip=f"{'[END] ' if is_terminal else ''}{stop['name']}",
                    popup=folium.Popup(
                        f"<b>{stop['name']}</b>"
                        + ("<br><i>Terminal stop</i>" if is_terminal else ""),
                        max_width=180,
                    ),
                ).add_to(route_layer)

    # Board / alight pin markers
    board  = route.get('board_point')
    alight = route.get('alight_point')
    if board:
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


def _draw_bus_route(route, m):
    """
    Draw a multi-leg bus route: walk -> bus -> walk.
    Visual: solid thicker line with terminal stop markers.
    """
    route_layer = folium.FeatureGroup(name=route['name'])
    segments    = route.get('segments', [])
    line_color  = route['color']

    if not segments:
        folium.PolyLine(
            locations=route['coords'],
            color=line_color, weight=6, opacity=0.9,
            tooltip=route['name'],
        ).add_to(route_layer)
        route_layer.add_to(m)
        return

    for seg in segments:
        coords = seg.get('coords', [])
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
                tooltip=f"Bus: {seg.get('label', route['name'])} ({route.get('time', '')})",
            ).add_to(route_layer)

            # OSM bus stop pins along the route
            stations = route.get('stations', [])
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

            # Board marker — walk destination
            if route.get('board_point'):
                bp = route['board_point']
                folium.Marker(
                    location=[bp['lat'], bp['lon']],
                    tooltip=f"Board bus here ({route.get('walk_board_m', '?')}m walk)",
                    icon=folium.Icon(color='blue', icon='bus', prefix='fa'),
                ).add_to(route_layer)

            # Alight marker
            if route.get('alight_point'):
                ap = route['alight_point']
                folium.Marker(
                    location=[ap['lat'], ap['lon']],
                    tooltip=f"Alight here ({route.get('walk_alight_m', '?')}m walk)",
                    icon=folium.Icon(color='orange', icon='flag', prefix='fa'),
                ).add_to(route_layer)

    route_layer.add_to(m)

def _draw_multimodal_route(route, m):
    route_layer = folium.FeatureGroup(name=route['name'])
    for seg in route.get('segments', []):
        coords = seg.get('coords',[])
        if not coords: continue
        
        if seg['type'] == 'walk':
            folium.PolyLine(locations=coords, color='#7f8c8d', weight=3, dash_array='8 6', tooltip=seg.get('label', 'Walk')).add_to(route_layer)
        elif seg['type'] == 'train':
            for t_seg in coords:
                folium.PolyLine(locations=t_seg, color=seg.get('color', '#8e44ad'), weight=6, dash_array='10 6', tooltip=seg.get('label', 'Train')).add_to(route_layer)
        else: # Jeepney or Bus legs
            folium.PolyLine(locations=coords, color=seg.get('color', '#e67e22'), weight=6, tooltip=seg.get('label', 'Road')).add_to(route_layer)
            
    # Draw stations pins across the whole journey
    for station in route.get('stations', []):
        folium.CircleMarker(
            location=[station['lat'], station['lon']],
            radius=5, color=route['color'], weight=2, fill=True, fill_color='#fff', fill_opacity=1.0,
            tooltip=station.get('name', 'Station/Stop')
        ).add_to(route_layer)
        
    route_layer.add_to(m)


def _draw_transit_route(route, m):
    """
    Draw a transit route card (type='transit').

    Segment types:
      'walk'    → dashed grey  — OSRM foot (sidewalks, footbridges, crossings)
      'train'   → dashed colour + filled circle station pins
      'jeepney' → solid orange  — jeepney connector to/from station

    Each segment carries 'stations' so pins appear at the exact OSM coords.
    """
    route_layer = folium.FeatureGroup(name=route['name'])
    line_color  = route.get('color', '#8e44ad')

    for seg in route.get('segments', []):
        seg_type = seg.get('type')
        coords   = seg.get('coords', [])

        # ── Walk leg ──────────────────────────────────────────────────────────
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
            # Board/alight marker at the walk endpoint nearest a station
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

        # ── Jeepney connector leg ─────────────────────────────────────────────
        elif seg_type == 'jeepney':
            if len(coords) >= 2:
                folium.PolyLine(
                    locations=coords,
                    color=seg.get('color', '#e67e22'),
                    weight=5,
                    opacity=0.88,
                    tooltip=seg.get('label', 'Jeepney connector'),
                ).add_to(route_layer)

        # ── Train leg ─────────────────────────────────────────────────────────
        elif seg_type == 'train':
            seg_color    = seg.get('color', line_color)
            seg_stations = seg.get('stations', [])

            # Track polyline(s)
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

            # Station pins — every stop gets a circle; terminals are bigger
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


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/', methods=['GET', 'POST'])
def home():
    if 'user' not in session:
        return redirect(url_for('login'))

    routes_data = []
    m = get_base_map()

    if request.method == 'POST':
        origin_text   = request.form.get('origin')
        dest_text     = request.form.get('destination')
        commuter_type = request.form.get('commuterType')

        orig_lon, orig_lat = geocode_location(origin_text)
        dest_lon, dest_lat = geocode_location(dest_text)

        if not orig_lon or not dest_lon:
            flash("Location not found. Please type a specific address.")
        else:
            nav_response = get_navigation_data(
                orig_lon, orig_lat, dest_lon, dest_lat, commuter_type, []
            )

            if "error" in nav_response:
                flash(nav_response["error"])
            else:
                routes_data = nav_response.get("routes", [])

                if routes_data:
                    start_coord  = [orig_lat, orig_lon]
                    end_coord    = [dest_lat, dest_lon]
                    marker_group = folium.FeatureGroup(name="Start & End Points")
                    folium.Marker(start_coord, popup="Starting Point",
                                  icon=folium.Icon(color="green", icon="play")).add_to(marker_group)
                    folium.Marker(end_coord, popup="Destination",
                                  icon=folium.Icon(color="red",   icon="stop")).add_to(marker_group)
                    marker_group.add_to(m)
                    m.fit_bounds([start_coord, end_coord])

                for route in routes_data:
                    rtype = route.get('type', '')
                    if rtype in ('transit', 'train'):
                        _draw_transit_route(route, m)
                    elif route.get('type') == 'jeepney':
                        _draw_jeepney_route(route, m)
                    elif route.get('type') == 'bus':
                        _draw_bus_route(route, m)
                    elif route.get('type') == 'multimodal':
                        _draw_multimodal_route(route, m)
                    else:
                        _draw_road_route(route, m)

                if routes_data:
                    folium.LayerControl().add_to(m)

    map_html = m.get_root().render()
    return render_template('index.html', user=session['user'], map_html=map_html, routes=routes_data)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username  = request.form.get('username')
        password  = request.form.get('password')
        conn, c   = chDB_perf.get_db_connection()
        chDB_perf.execute_query(c, "SELECT * FROM users WHERE username=?", (username,))
        if c.fetchone():
            flash("Username already exists.")
            c.close(); conn.close()
            return redirect(url_for('register'))
        hashed_pw = generate_password_hash(password)
        chDB_perf.execute_query(c, "INSERT INTO users (username, password) VALUES (?, ?)",
                                (username, hashed_pw))
        conn.commit(); c.close(); conn.close()
        flash("Registration successful!")
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        conn, c  = chDB_perf.get_db_connection()
        chDB_perf.execute_query(c, "SELECT password FROM users WHERE username=?", (username,))
        user = c.fetchone()
        c.close(); conn.close()
        if user and check_password_hash(user[0], password):
            session['user'] = username
            return redirect(url_for('home'))
        flash("Invalid username or password.")
        return redirect(url_for('login'))
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))


@app.route('/api/suggest', methods=['GET'])
def suggest_location():
    query = request.args.get('q', '')
    if len(query) < 3:
        return jsonify([])
    url = (
        f"https://nominatim.openstreetmap.org/search"
        f"?q={query}&format=json&addressdetails=1&limit=5&countrycodes=ph"
    )
    try:
        return jsonify(requests.get(url, headers={'User-Agent': 'SafeRoute-Flask-App/1.0'}).json())
    except Exception:
        return jsonify([])


@app.route('/api/reverse', methods=['GET'])
def reverse_geocode_api():
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
    try:
        data = requests.get(url, headers={'User-Agent': 'SafeRoute-Flask-App/1.0'}).json()
        return jsonify({"address": data.get("display_name", f"{lat}, {lon}")})
    except Exception:
        return jsonify({"address": f"{lat}, {lon}"})

@app.route('/api/nearby', methods=['GET'])
def get_nearby_api():
    try:
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
        radius = float(request.args.get('radius', 800))
        from navigation import get_nearby_transit
        results = get_nearby_transit(lat, lon, radius)
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/api/route', methods=['POST'])
@app.route('/api/routes', methods=['POST'])
def get_routes():
    data = request.json
    # Handle both direct text input or coordinates
    origin_text = data.get('origin')
    dest_text = data.get('destination')
    commuter_type = data.get('mode') or data.get('commuterType') or 'car'
    
    # Check for coordinates first (from map clicks/pins)
    orig_coords = data.get('orig_coords') or data.get('originCoords')
    dest_coords = data.get('dest_coords') or data.get('destCoords')

    if orig_coords:
        orig_lon = float(orig_coords.get('lon', orig_coords.get('lng', 0)))
        orig_lat = float(orig_coords.get('lat', 0))
    else:
        orig_lon, orig_lat = geocode_location(origin_text)

    if dest_coords:
        dest_lon = float(dest_coords.get('lon', dest_coords.get('lng', 0)))
        dest_lat = float(dest_coords.get('lat', 0))
    else:
        dest_lon, dest_lat = geocode_location(dest_text)

    if not orig_lon or not dest_lon:
        return jsonify({"error": "Location not found."}), 400

    # Calculate the route
    nav_response = get_navigation_data(
        orig_lon, orig_lat, dest_lon, dest_lat, commuter_type, []
    )
    
    if "error" in nav_response:
        return jsonify({"error": nav_response["error"]}), 400

    return jsonify(nav_response)

if __name__ == '__main__':
    app.run(debug=True)