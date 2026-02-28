from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from navigation import geocode_location, get_navigation_data
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
USE_MYSQL = False
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = ""
DB_NAME = "saferoute_db"
SQLITE_DB = "users.db"

# ==========================================
# 🛠️ DATABASE HELPER FUNCTIONS
# ==========================================
def get_db_connection():
    if USE_MYSQL:
        conn = mysql.connector.connect(
            host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
        )
        return conn, conn.cursor()
    else:
        conn = sqlite3.connect(SQLITE_DB)
        return conn, conn.cursor()

def execute_query(cursor, query, params=None):
    if USE_MYSQL:
        query = query.replace('?', '%s')
    if params:
        cursor.execute(query, params)
    else:
        cursor.execute(query)

def init_db():
    if USE_MYSQL:
        try:
            temp_conn = mysql.connector.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD)
            temp_cursor = temp_conn.cursor()
            temp_cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
            temp_cursor.close()
            temp_conn.close()
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
        conn, c = get_db_connection()
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                     (username TEXT PRIMARY KEY, password TEXT)''')
        conn.commit()
        c.close()
        conn.close()
        print("🟢 Using SQLite Database")

init_db()

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
        execute_query(c, "SELECT * FROM users WHERE username=?", (username,))
        if c.fetchone():
            flash("Username already exists.")
            c.close()
            conn.close()
            return redirect(url_for('register'))
        hashed_pw = generate_password_hash(password)
        execute_query(c, "INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_pw))
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
        conn, c = get_db_connection()
        execute_query(c, "SELECT password FROM users WHERE username=?", (username,))
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

@app.route('/api/routes', methods=['POST'])
def get_routes():
    data = request.json
    origin = data.get('origin')
    destination = data.get('destination')
    commuter_type = data.get('commuterType')

    orig_lon, orig_lat = geocode_location(origin)
    dest_lon, dest_lat = geocode_location(destination)

    if not orig_lon or not dest_lon:
        return jsonify({"error": "Could not find locations."}), 400

    # Passing an empty list [] instead of FLOOD_ZONES 
    # This disables the hazard calculation in navigation.py
    nav_response = get_navigation_data(orig_lon, orig_lat, dest_lon, dest_lat, commuter_type, [])
    
    if "error" in nav_response:
        return jsonify({"error": nav_response["error"]}), 400

    return jsonify(nav_response)

if __name__ == '__main__':
    app.run(debug=True)