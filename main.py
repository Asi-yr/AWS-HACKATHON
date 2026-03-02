from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from navigation import geocode_location, get_navigation_data
from folium import plugins
import requests # NEW: Needed to make API calls from Python
import folium

USE_MYSQL = False 

if USE_MYSQL:
    from database_handlers import mysqdb as chDB_perf
    chDB_perf.init_db()
else:
    from database_handlers import sqdb as chDB_perf
    chDB_perf.init_db()

app = Flask(__name__)
app.secret_key = 'saferoute_super_secret_key'

def get_base_map(center_lat=14.605, center_lon=120.985, zoom=13):
    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom, tiles="OpenStreetMap")
    
    # Folium Plugin 1: Live Tracking/GPS (Adds a button to the map)
    plugins.LocateControl(auto_start=False, strings={"title": "Use my current location"}).add_to(m)
    
    # Folium Plugin 2: Click map to see coordinates (Useful for manual entry)
    m.add_child(folium.LatLngPopup())
    
    return m

# 🚦 ROUTES & APPLICATION LOGIC
@app.route('/', methods=['GET', 'POST'])
def home():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    routes_data =[]
    
    # 1. Start with an empty map
    m = get_base_map()

    # 2. If user clicked "Find Safe Routes" (Form Submission)
    if request.method == 'POST':
        origin_text = request.form.get('origin')
        dest_text = request.form.get('destination')
        commuter_type = request.form.get('commuterType')

        # Geocode from Navigation.py
        orig_lon, orig_lat = geocode_location(origin_text)
        dest_lon, dest_lat = geocode_location(dest_text)

        if not orig_lon or not dest_lon:
            flash("Location not found. Please type a more specific address or use coordinates (Lat, Lon).")
        else:
            # Calculate Routes
            nav_response = get_navigation_data(orig_lon, orig_lat, dest_lon, dest_lat, commuter_type,[])
            
            if "error" in nav_response:
                flash(nav_response["error"])
            else:
                routes_data = nav_response.get("routes",[])
                
                # Draw the routes on the Folium Map
                for route in routes_data:
                    folium.PolyLine(
                        locations=route['coords'],
                        color=route['color'],
                        weight=6,
                        opacity=0.8,
                        tooltip=route['name']
                    ).add_to(m)

                # Add Green and Red Markers for the best route
                if routes_data:
                    best_route = routes_data[0]
                    start_coord = best_route['coords'][0]
                    end_coord = best_route['coords'][-1]

                    folium.Marker(start_coord, popup="Starting Point", icon=folium.Icon(color="green")).add_to(m)
                    folium.Marker(end_coord, popup="Destination", icon=folium.Icon(color="red")).add_to(m)

                    # Automatically zoom the map to fit the route lines
                    m.fit_bounds([start_coord, end_coord])

    # 3. Convert the Folium map to HTML
    map_html = m.get_root().render()

    return render_template('index.html', user=session['user'], map_html=map_html, routes=routes_data)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        conn, c = chDB_perf.get_db_connection()
        chDB_perf.execute_query(c, "SELECT * FROM users WHERE username=?", (username,))

        if c.fetchone():
            flash("Username already exists.")
            c.close()
            conn.close()
            return redirect(url_for('register'))
        
        hashed_pw = generate_password_hash(password)
        chDB_perf.execute_query(c, "INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_pw))
        conn.commit()
        c.close()
        conn.close()

        flash("Registration successful!")
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        conn, c = chDB_perf.get_db_connection()
        chDB_perf.execute_query(c, "SELECT password FROM users WHERE username=?", (username,))

        user = c.fetchone()
        c.close()
        conn.close()
        if user and check_password_hash(user[0], password):
            session['user'] = username
            return redirect(url_for('home'))
        else:
            flash("Invalid username or password.")
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

# 🗺️ MAP & LOCATION APIs (Moved from JS to Python)
# 1. Fetch Suggestions (Autocomplete)
@app.route('/api/suggest', methods=['GET'])
def suggest_location():
    query = request.args.get('q', '')
    if len(query) < 3:
        return jsonify([])
    
    # Python makes the API call instead of JS
    url = f"https://nominatim.openstreetmap.org/search?q={query}&format=json&addressdetails=1&limit=5&countrycodes=ph"
    headers = {'User-Agent': 'SafeRoute-Flask-App/1.0'} # Nominatim requires a User-Agent
    
    try:
        response = requests.get(url, headers=headers)
        return jsonify(response.json())
    except Exception as e:
        print("Suggestion error:", e)
        return jsonify([])

# 2. Reverse Geocode (Map Click to Address)
@app.route('/api/reverse', methods=['GET'])
def reverse_geocode_api():
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    
    url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
    headers = {'User-Agent': 'SafeRoute-Flask-App/1.0'}
    
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        return jsonify({"address": data.get("display_name", f"{lat}, {lon}")})
    except Exception as e:
        print("Reverse geocode error:", e)
        return jsonify({"address": f"{lat}, {lon}"})

# 3. Main Route Calculation
@app.route('/api/routes', methods=['POST'])
def get_routes():
    data = request.json
    origin_text = data.get('origin')
    dest_text = data.get('destination')
    orig_coords = data.get('originCoords')  
    dest_coords = data.get('destCoords')    
    commuter_type = data.get('commuterType')

    # Handle Origin
    if orig_coords:
        orig_lon, orig_lat = float(orig_coords['lon']), float(orig_coords['lat'])
    else:
        orig_lon, orig_lat = geocode_location(origin_text)

    # Handle Destination
    if dest_coords:
        dest_lon, dest_lat = float(dest_coords['lon']), float(dest_coords['lat'])
    else:
        dest_lon, dest_lat = geocode_location(dest_text)

    if not orig_lon or not dest_lon:
        return jsonify({"error": "Location not found. Please select from the suggestions or use the Map Pin."}), 400

    nav_response = get_navigation_data(orig_lon, orig_lat, dest_lon, dest_lat, commuter_type,[])
    
    if "error" in nav_response:
        return jsonify({"error": nav_response["error"]}), 400

    return jsonify(nav_response)

if __name__ == '__main__':
    app.run(debug=True)