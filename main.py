from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from shapely.geometry import LineString, Polygon
import requests
import sqlite3

# Try to import MySQL, but don't crash if it's not installed yet
try:
    import mysql.connector
except ImportError:
    pass

app = Flask(__name__)
app.secret_key = 'saferoute_super_secret_key'

# ==========================================
# ⚙️ DATABASE TOGGLE SWITCH
# ==========================================
# Set to True to use MySQL. Set to False to use SQLite.
USE_MYSQL = False

# MySQL Configuration
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = ""
DB_NAME = "saferoute_db"

# SQLite Configuration
SQLITE_DB = "users.db"


# ==========================================
# 🛠️ DATABASE HELPER FUNCTIONS
# ==========================================
def get_db_connection():
    """Returns a connection and a cursor based on the selected database."""
    if USE_MYSQL:
        conn = mysql.connector.connect(
            host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
        )
        return conn, conn.cursor()
    else:
        conn = sqlite3.connect(SQLITE_DB)
        return conn, conn.cursor()

def execute_query(cursor, query, params=None):
    """Automatically swaps SQLite '?' with MySQL '%s' depending on the active DB."""
    if USE_MYSQL:
        query = query.replace('?', '%s')
    
    if params:
        cursor.execute(query, params)
    else:
        cursor.execute(query)

def init_db():
    """Initializes the active database and creates the users table."""
    if USE_MYSQL:
        try:
            # Connect to MySQL server to create database if it doesn't exist
            temp_conn = mysql.connector.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD)
            temp_cursor = temp_conn.cursor()
            temp_cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
            temp_cursor.close()
            temp_conn.close()

            # Connect to the specific database to create the table
            conn, c = get_db_connection()
            c.execute('''CREATE TABLE IF NOT EXISTS users 
                         (username VARCHAR(255) PRIMARY KEY, password VARCHAR(255))''')
            conn.commit()
            c.close()
            conn.close()
            print("🟢 Using MySQL Database")
        except Exception as e:
            print(f"🔴 MySQL Error: {e}")
    else:
        # SQLite automatically creates the file if it doesn't exist
        conn, c = get_db_connection()
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                     (username TEXT PRIMARY KEY, password TEXT)''')
        conn.commit()
        c.close()
        conn.close()
        print("🟢 Using SQLite Database")

# Initialize the database when the server starts
init_db()


# ==========================================
# 🌊 FLOOD ZONES (MOCK DATA)
# ==========================================
FLOOD_ZONES =[
    {
        "name": "Espana Flood Zone",
        "polygon": Polygon([(120.980, 14.600), (120.999, 14.600), (120.999, 14.615), (120.980, 14.615)])
    }
]


# ==========================================
# 🚦 ROUTES & APPLICATION LOGIC
# ==========================================
@app.route('/')
def home():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', user=session['user'])

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn, c = get_db_connection()
        
        # Check if user already exists
        execute_query(c, "SELECT * FROM users WHERE username=?", (username,))
        if c.fetchone():
            flash("Username already exists. Please choose a different one.")
            c.close()
            conn.close()
            return redirect(url_for('register'))
            
        # Hash the password and save the new user
        hashed_pw = generate_password_hash(password)
        execute_query(c, "INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_pw))
        conn.commit()
        
        c.close()
        conn.close()
        
        flash("Registration successful! You can now log in.")
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn, c = get_db_connection()
        execute_query(c, "SELECT password FROM users WHERE username=?", (username,))
        user = c.fetchone()
        
        c.close()
        conn.close()
        
        # Check if user exists and password is correct (user[0] is the hashed password)
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

@app.route('/api/routes', methods=['POST'])
def get_routes():
    data = request.json
    origin = data.get('origin')
    destination = data.get('destination')
    commuter_type = data.get('commuterType')

    headers = {'User-Agent': 'SafeRouteAI/1.0'}

    # 1. Geocoding
    try:
        orig_resp = requests.get(f"https://nominatim.openstreetmap.org/search?q={origin}&format=json&limit=1", headers=headers).json()
        dest_resp = requests.get(f"https://nominatim.openstreetmap.org/search?q={destination}&format=json&limit=1", headers=headers).json()
        
        if not orig_resp or not dest_resp:
            return jsonify({"error": "Could not find locations. Try being more specific (e.g. 'Manila City')."}), 400

        orig_coords = (float(orig_resp[0]['lon']), float(orig_resp[0]['lat']))
        dest_coords = (float(dest_resp[0]['lon']), float(dest_resp[0]['lat']))
    except Exception as e:
        return jsonify({"error": "Geocoding service unavailable."}), 500

    # 2. Routing via OSRM
    osrm_url = f"https://router.project-osrm.org/route/v1/driving/{orig_coords[0]},{orig_coords[1]};{dest_coords[0]},{dest_coords[1]}?overview=full&geometries=geojson&alternatives=true"
    route_resp = requests.get(osrm_url).json()

    if route_resp.get("code") != "Ok":
        return jsonify({"error": "Could not calculate a route."}), 400

    processed_routes = []
    colors =["#3498db", "#f1c40f", "#2ecc71"]
    names =["Fastest Route", "Alternative 1", "Alternative 2"]
    risk_multiplier = {"tricycle": 3.0, "car": 1.5, "jeepney": 1.0}.get(commuter_type, 1.0)

    # 3. Apply Safety Algorithm
    for i, r in enumerate(route_resp.get("routes", [])[:3]):
        coords_lonlat = r["geometry"]["coordinates"]
        coords_latlon = [[pt[1], pt[0]] for pt in coords_lonlat]
        line = LineString(coords_lonlat)
        
        flood_intersection_length = 0
        for zone in FLOOD_ZONES:
            if line.intersects(zone["polygon"]):
                intersection = line.intersection(zone["polygon"])
                flood_intersection_length += intersection.length

        hazard_penalty = flood_intersection_length * 5000 * risk_multiplier
        safety_score = max(0, int(100 - hazard_penalty))
        duration_mins = int(r["duration"] / 60)
        distance_km = round(r["distance"] / 1000, 1)

        processed_routes.append({
            "id": i,
            "name": names[i] if i < len(names) else f"Route {i+1}",
            "color": colors[i] if i < len(colors) else "#95a5a6",
            "time": f"{duration_mins} mins",
            "distance": f"{distance_km} km",
            "coords": coords_latlon,
            "safety_score": safety_score,
            "hazards_flagged": "High Flood Risk" if safety_score < 50 else ("Moderate Risk" if safety_score < 80 else "Clear")
        })

    processed_routes = sorted(processed_routes, key=lambda x: x["safety_score"], reverse=True)
    return jsonify({"routes": processed_routes})

if __name__ == '__main__':
    app.run(debug=True)