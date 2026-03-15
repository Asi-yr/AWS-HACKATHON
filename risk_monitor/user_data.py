"""
user_data.py
------------
Feature: User Data — Settings, Route History, Account & Profile Settings.

Stores all user-specific data in the existing SQLite/MySQL database
via the db_opt.py interface (nsql/msql). No new database engine needed.

Tables created (if not exist) on first call to init_user_tables(db):
  user_settings  — per-user preferences (commuter type, overlay toggles, etc.)
  route_history  — past route searches per user
  user_profile   — display name, email, join date

Nothing runs on import. Call init_user_tables(db) once at app startup.

Integration points (do NOT modify original files — wire in your local copy):

  main.py additions:
    from risk_monitor.user_data import (
        init_user_tables, get_user_settings, save_user_settings,
        save_route_history, get_route_history, clear_route_history,
        get_user_profile, save_user_profile, change_password,
        extract_settings_from_form, get_settings_form_html, get_history_html,
    )

    # After chDB_perf.init_db():
    init_user_tables(chDB_perf)

    # After successful route search (inside POST handler):
    save_route_history(
        chDB_perf, session['user'],
        origin_text, dest_text, commuter_type, len(routes_data)
    )

    # New Flask routes to add:
    @app.route('/settings', methods=['GET', 'POST'])
    def settings():
        if 'user' not in session:
            return redirect(url_for('login'))
        if request.method == 'POST':
            settings_data = extract_settings_from_form(request.form)
            save_user_settings(chDB_perf, session['user'], settings_data)
            # Also handle profile update sub-form if present
            if request.form.get('display_name') is not None:
                save_user_profile(
                    chDB_perf, session['user'],
                    request.form.get('display_name', ''),
                    request.form.get('email', ''),
                )
            flash('Settings saved.')
            return redirect(url_for('settings'))
        user_settings = get_user_settings(chDB_perf, session['user'])
        profile       = get_user_profile(chDB_perf, session['user'])
        settings_html = get_settings_form_html(user_settings)
        return render_template(
            'settings.html',
            user=session['user'],
            settings_html=settings_html,
            profile=profile,
        )

    @app.route('/history')
    def history():
        if 'user' not in session:
            return redirect(url_for('login'))
        hist      = get_route_history(chDB_perf, session['user'])
        hist_html = get_history_html(hist)
        return render_template(
            'history.html',
            user=session['user'],
            history_html=hist_html,
        )

    @app.route('/history/clear', methods=['POST'])
    def history_clear():
        if 'user' not in session:
            return redirect(url_for('login'))
        clear_route_history(chDB_perf, session['user'])
        flash('History cleared.')
        return redirect(url_for('history'))

    @app.route('/account/password', methods=['POST'])
    def change_password_route():
        if 'user' not in session:
            return redirect(url_for('login'))
        result = change_password(
            chDB_perf, session['user'],
            request.form.get('old_password', ''),
            request.form.get('new_password', ''),
        )
        flash(result['message'])
        return redirect(url_for('settings'))

  Templates needed (create in your local templates/ folder):
    templates/settings.html  — see get_settings_page_html() for a self-contained example
    templates/history.html   — see get_history_page_html() for a self-contained example

New modules needed (add to requirements.txt):
  # new modules to add
  # (none — uses sqlite3/mysql.connector already installed via db_opt.py)
"""

import json
from datetime import datetime, timezone, timedelta

_PHT = timezone(timedelta(hours=8))

# ── Default user settings ─────────────────────────────────────────────────────

DEFAULT_SETTINGS = {
    "default_commuter_type":  "commute",
    "show_flood_overlay":     True,
    "show_weather_banner":    True,
    "show_night_warnings":    True,
    "preferred_name":         "",    # display name override
    "home_address":           "",
    "work_address":           "",
    "auto_search_history":    False, # auto-run search when using History "Use Again"
}

# Max route history entries to keep per user
_MAX_HISTORY = 50


# ═════════════════════════════════════════════════════════════════════════════
# DB SETUP
# ═════════════════════════════════════════════════════════════════════════════

def init_user_tables(db) -> None:
    """
    Creates user_settings, route_history, and user_profile tables
    if they don't already exist.

    Args:
        db: an nsql or msql instance from db_opt.py

    Usage in main.py (add right after chDB_perf.init_db()):
        from risk_monitor.user_data import init_user_tables
        init_user_tables(chDB_perf)
    """
    conn, c = db.get_db_connection()
    try:
        # User settings — one row per user, JSON blob for flexibility
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                username      TEXT PRIMARY KEY,
                settings_json TEXT NOT NULL DEFAULT '{}'
            )
        """)

        # Route history — one row per search
        c.execute("""
            CREATE TABLE IF NOT EXISTS route_history (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT NOT NULL,
                origin        TEXT,
                destination   TEXT,
                commuter_type TEXT,
                route_count   INTEGER,
                searched_at   TEXT
            )
        """)

        # User profile — extended info beyond username/password
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_profile (
                username     TEXT PRIMARY KEY,
                display_name TEXT DEFAULT '',
                email        TEXT DEFAULT '',
                joined_at    TEXT DEFAULT ''
            )
        """)

        conn.commit()
        print("🟢 user_data tables ready.")
    except Exception as e:
        print(f"🔴 user_data init error: {e}")
    finally:
        c.close()
        conn.close()


# ═════════════════════════════════════════════════════════════════════════════
# USER SETTINGS
# ═════════════════════════════════════════════════════════════════════════════

def get_user_settings(db, username: str) -> dict:
    """
    Load settings for a user. Returns DEFAULT_SETTINGS if user has none yet.

    Args:
        db:       nsql or msql instance
        username: logged-in username (from session['user'])

    Returns:
        dict of settings (always contains all DEFAULT_SETTINGS keys)
    """
    conn, c = db.get_db_connection()
    try:
        db.execute_query(c,
            "SELECT settings_json FROM user_settings WHERE username=?",
            (username,)
        )
        row = c.fetchone()
        if not row:
            return dict(DEFAULT_SETTINGS)
        stored = json.loads(row[0] or "{}")
        merged = dict(DEFAULT_SETTINGS)
        merged.update(stored)
        return merged
    except Exception as e:
        print(f"[user_data] get_user_settings error: {e}")
        return dict(DEFAULT_SETTINGS)
    finally:
        c.close()
        conn.close()


def save_user_settings(db, username: str, settings: dict) -> bool:
    """
    Persist user settings to the database (upsert).

    Args:
        db:       nsql or msql instance
        username: logged-in username
        settings: dict of settings to save (merged with defaults before saving)

    Returns:
        True if saved successfully, False on error.
    """
    merged = dict(DEFAULT_SETTINGS)
    merged.update(settings)
    blob = json.dumps(merged)

    conn, c = db.get_db_connection()
    try:
        db.execute_query(c,
            "SELECT username FROM user_settings WHERE username=?",
            (username,)
        )
        if c.fetchone():
            db.execute_query(c,
                "UPDATE user_settings SET settings_json=? WHERE username=?",
                (blob, username)
            )
        else:
            db.execute_query(c,
                "INSERT INTO user_settings (username, settings_json) VALUES (?, ?)",
                (username, blob)
            )
        conn.commit()
        return True
    except Exception as e:
        print(f"[user_data] save_user_settings error: {e}")
        return False
    finally:
        c.close()
        conn.close()


def update_single_setting(db, username: str, key: str, value) -> bool:
    """
    Update one setting key for a user without overwriting others.

    Args:
        db:       nsql or msql instance
        username: logged-in username
        key:      setting key (must be in DEFAULT_SETTINGS)
        value:    new value

    Returns:
        True if saved successfully.
    """
    if key not in DEFAULT_SETTINGS:
        print(f"[user_data] Unknown setting key: {key}")
        return False
    current = get_user_settings(db, username)
    current[key] = value
    return save_user_settings(db, username, current)


# ═════════════════════════════════════════════════════════════════════════════
# ROUTE HISTORY
# ═════════════════════════════════════════════════════════════════════════════

def save_route_history(
    db,
    username:      str,
    origin:        str,
    destination:   str,
    commuter_type: str,
    route_count:   int = 0,
) -> bool:
    """
    Save a route search to the user's history.

    Args:
        db:            nsql or msql instance
        username:      logged-in username
        origin:        origin text as typed
        destination:   destination text as typed
        commuter_type: e.g. 'commute', 'motorcycle'
        route_count:   number of routes returned

    Returns:
        True if saved successfully.

    Usage in main.py after successful nav_response:
        save_route_history(
            chDB_perf, session['user'],
            origin_text, dest_text, commuter_type, len(routes_data)
        )
    """
    now = datetime.now(_PHT).strftime("%Y-%m-%d %H:%M PHT")
    conn, c = db.get_db_connection()
    try:
        db.execute_query(c,
            """INSERT INTO route_history
               (username, origin, destination, commuter_type, route_count, searched_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (username, origin, destination, commuter_type, route_count, now)
        )
        conn.commit()
        _trim_history(db, c, conn, username)
        return True
    except Exception as e:
        print(f"[user_data] save_route_history error: {e}")
        return False
    finally:
        c.close()
        conn.close()


def _trim_history(db, c, conn, username: str) -> None:
    """Keep only the last _MAX_HISTORY entries per user."""
    try:
        db.execute_query(c,
            """DELETE FROM route_history WHERE id IN (
                SELECT id FROM route_history
                WHERE username=?
                ORDER BY id DESC
                LIMIT -1 OFFSET ?
            )""",
            (username, _MAX_HISTORY)
        )
        conn.commit()
    except Exception:
        pass  # Non-critical — history trimming failure is silent


def get_route_history(db, username: str, limit: int = 20) -> list:
    """
    Retrieve recent route history for a user.

    Args:
        db:       nsql or msql instance
        username: logged-in username
        limit:    max entries to return (default 20)

    Returns:
        List of dicts: [{origin, destination, commuter_type, route_count, searched_at}]
        Most recent first.
    """
    conn, c = db.get_db_connection()
    try:
        db.execute_query(c,
            """SELECT origin, destination, commuter_type, route_count, searched_at
               FROM route_history
               WHERE username=?
               ORDER BY id DESC
               LIMIT ?""",
            (username, limit)
        )
        rows = c.fetchall()
        return [
            {
                "origin":        r[0],
                "destination":   r[1],
                "commuter_type": r[2],
                "route_count":   r[3],
                "searched_at":   r[4],
            }
            for r in rows
        ]
    except Exception as e:
        print(f"[user_data] get_route_history error: {e}")
        return []
    finally:
        c.close()
        conn.close()


def clear_route_history(db, username: str) -> bool:
    """
    Delete all route history entries for a user.

    Returns True if successful.
    """
    conn, c = db.get_db_connection()
    try:
        db.execute_query(c,
            "DELETE FROM route_history WHERE username=?",
            (username,)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"[user_data] clear_route_history error: {e}")
        return False
    finally:
        c.close()
        conn.close()


# ═════════════════════════════════════════════════════════════════════════════
# USER PROFILE
# ═════════════════════════════════════════════════════════════════════════════

def get_user_profile(db, username: str) -> dict:
    """
    Load the extended profile for a user.

    Returns:
        {username, display_name, email, joined_at}
    """
    conn, c = db.get_db_connection()
    try:
        db.execute_query(c,
            "SELECT display_name, email, joined_at FROM user_profile WHERE username=?",
            (username,)
        )
        row = c.fetchone()
        if not row:
            return {"username": username, "display_name": "", "email": "", "joined_at": ""}
        return {
            "username":     username,
            "display_name": row[0] or "",
            "email":        row[1] or "",
            "joined_at":    row[2] or "",
        }
    except Exception as e:
        print(f"[user_data] get_user_profile error: {e}")
        return {"username": username, "display_name": "", "email": "", "joined_at": ""}
    finally:
        c.close()
        conn.close()


def save_user_profile(db, username: str, display_name: str = "", email: str = "") -> bool:
    """
    Upsert display name and email for a user.

    Returns True if saved successfully.
    """
    conn, c = db.get_db_connection()
    try:
        db.execute_query(c,
            "SELECT username FROM user_profile WHERE username=?",
            (username,)
        )
        if c.fetchone():
            db.execute_query(c,
                "UPDATE user_profile SET display_name=?, email=? WHERE username=?",
                (display_name, email, username)
            )
        else:
            joined = datetime.now(_PHT).strftime("%Y-%m-%d")
            db.execute_query(c,
                "INSERT INTO user_profile (username, display_name, email, joined_at) VALUES (?, ?, ?, ?)",
                (username, display_name, email, joined)
            )
        conn.commit()
        return True
    except Exception as e:
        print(f"[user_data] save_user_profile error: {e}")
        return False
    finally:
        c.close()
        conn.close()


# ═════════════════════════════════════════════════════════════════════════════
# ACCOUNT SETTINGS (password change)
# ═════════════════════════════════════════════════════════════════════════════

def change_password(db, username: str, old_password: str, new_password: str) -> dict:
    """
    Verify old password and update to new password.

    Args:
        db:           nsql or msql instance
        username:     logged-in username
        old_password: plaintext old password
        new_password: plaintext new password

    Returns:
        {"ok": bool, "message": str}

    Note: Uses werkzeug check_password_hash / generate_password_hash
    (already in requirements.txt via Flask).
    """
    from werkzeug.security import check_password_hash, generate_password_hash

    if len(new_password) < 6:
        return {"ok": False, "message": "New password must be at least 6 characters."}

    conn, c = db.get_db_connection()
    try:
        db.execute_query(c,
            "SELECT password FROM users WHERE username=?",
            (username,)
        )
        row = c.fetchone()
        if not row:
            return {"ok": False, "message": "User not found."}
        if not check_password_hash(row[0], old_password):
            return {"ok": False, "message": "Current password is incorrect."}

        new_hash = generate_password_hash(new_password)
        db.execute_query(c,
            "UPDATE users SET password=? WHERE username=?",
            (new_hash, username)
        )
        conn.commit()
        return {"ok": True, "message": "Password changed successfully."}
    except Exception as e:
        return {"ok": False, "message": f"Error: {str(e)}"}
    finally:
        c.close()
        conn.close()


# ═════════════════════════════════════════════════════════════════════════════
# FORM HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def extract_settings_from_form(form) -> dict:
    """
    Parse a Flask form submission (request.form) into a settings dict.

    Args:
        form: Flask request.form object

    Returns:
        dict ready to pass to save_user_settings()

    Usage in main.py /settings POST handler:
        settings = extract_settings_from_form(request.form)
        save_user_settings(chDB_perf, session['user'], settings)
    """
    return {
        "default_commuter_type": form.get("default_commuter_type", "commute"),
        "preferred_name":        form.get("preferred_name", "").strip(),
        "home_address":          form.get("home_address", "").strip(),
        "work_address":          form.get("work_address", "").strip(),
        "show_flood_overlay":    bool(form.get("show_flood_overlay")),
        "show_weather_banner":   bool(form.get("show_weather_banner")),
        "show_night_warnings":   bool(form.get("show_night_warnings")),
        "auto_search_history":   bool(form.get("auto_search_history")),
    }


# ═════════════════════════════════════════════════════════════════════════════
# HTML HELPERS (for Jinja templates)
# ═════════════════════════════════════════════════════════════════════════════

def get_settings_form_html(settings: dict) -> str:
    """
    Returns an HTML snippet for the user settings form.
    Inject into a settings.html template via Jinja: {{ settings_html | safe }}

    Args:
        settings: dict from get_user_settings()

    Returns:
        HTML string containing the full settings form.
    """
    def checked(val):
        return "checked" if val else ""

    # Inlined from the missing risk_monitor.form_state module
    _COMMUTER_OPTIONS = [
        {"value": "commute",    "label": "🚌 Public Commute (Jeepney/Bus)"},
        {"value": "walk",       "label": "🚶 Walking"},
        {"value": "bike",       "label": "🚲 Bicycle"},
        {"value": "motorcycle", "label": "🏍️ Motorcycle"},
        {"value": "car",        "label": "🚗 Car / Private Vehicle"},
        {"value": "lrt1",       "label": "🚇 LRT-1"},
        {"value": "lrt2",       "label": "🚇 LRT-2"},
        {"value": "mrt3",       "label": "🚇 MRT-3"},
    ]
    _selected = settings.get("default_commuter_type", "commute")
    opts = [
        {**o, "selected": o["value"] == _selected}
        for o in _COMMUTER_OPTIONS
    ]
    options_html = "\n".join(
        f'<option value="{o["value"]}" {"selected" if o["selected"] else ""}>{o["label"]}</option>'
        for o in opts
    )

    return f"""
<div class="settings-panel">
  <h3>⚙️ General Settings</h3>
  <form method="POST" action="/settings">

    <label class="input-label">Default Commuter Type:</label>
    <select name="default_commuter_type" style="width:100%;padding:10px;margin-bottom:15px;border:1px solid #ddd;border-radius:5px;">
      {options_html}
    </select>

    <label class="input-label">Preferred Display Name:</label>
    <input type="text" name="preferred_name" class="settings-input"
           value="{settings.get('preferred_name', '')}"
           placeholder="Leave blank to use username">

    <label class="input-label">Home Address:</label>
    <input type="text" name="home_address" class="settings-input"
           value="{settings.get('home_address', '')}"
           placeholder="e.g. Quezon City Hall">

    <label class="input-label">Work / School Address:</label>
    <input type="text" name="work_address" class="settings-input"
           value="{settings.get('work_address', '')}"
           placeholder="e.g. Intramuros, Manila">

    <hr style="margin:15px 0;">
    <h3>🔔 Display Preferences</h3>

    <label class="checkbox-label">
      <input type="checkbox" name="show_flood_overlay" value="1"
             {checked(settings.get('show_flood_overlay', True))}>
      Show NOAH Flood Zone Overlay
    </label>

    <label class="checkbox-label">
      <input type="checkbox" name="show_weather_banner" value="1"
             {checked(settings.get('show_weather_banner', True))}>
      Show Live Weather Banner
    </label>

    <label class="checkbox-label">
      <input type="checkbox" name="show_night_warnings" value="1"
             {checked(settings.get('show_night_warnings', True))}>
      Show Night Safety Warnings
    </label>

    <label class="checkbox-label">
      <input type="checkbox" name="auto_search_history" value="1"
             {checked(settings.get('auto_search_history', False))}>
      Auto-search when using History "Use Again"
    </label>

    <hr style="margin:15px 0;">
    <button type="submit" class="btn-primary">Save Settings</button>
  </form>
</div>
"""


def get_history_html(history: list) -> str:
    """
    Returns an HTML block of recent route history entries.
    Inject into a history.html template via Jinja: {{ history_html | safe }}

    Args:
        history: list from get_route_history()

    Returns:
        HTML string.
    """
    if not history:
        return '<p style="color:#7f8c8d;text-align:center;padding:20px;">No route history yet. Search for a route to get started!</p>'

    import urllib.parse
    rows = ""
    for entry in history:
        origin      = entry["origin"]
        destination = entry["destination"]
        ctype       = entry["commuter_type"]
        # Build a query string so the main page can pre-fill the form
        qs = urllib.parse.urlencode({
            "origin":       origin,
            "destination":  destination,
            "commuterType": ctype,
        })
        reuse_url = f"/?{qs}"

        rows += (
            f'<div class="history-entry" style="'
            f'background:#fdfdfd;border:1px solid #eee;border-left:4px solid #2980b9;'
            f'padding:12px 15px;margin-bottom:10px;border-radius:5px;'
            f'display:flex;justify-content:space-between;align-items:center;">'

            # Left: route info
            f'<div style="flex:1;min-width:0;">'
            f'<div style="font-weight:bold;color:#2c3e50;white-space:nowrap;'
            f'overflow:hidden;text-overflow:ellipsis;">'
            f'📍 {entry["origin"]} → {entry["destination"]}'
            f'</div>'
            f'<div style="font-size:12px;color:#7f8c8d;margin-top:4px;">'
            f'{ctype} &nbsp;|&nbsp; '
            f'{entry["route_count"]} route(s) found &nbsp;|&nbsp; '
            f'{entry["searched_at"]}'
            f'</div>'
            f'</div>'

            # Right: re-use button
            f'<a href="{reuse_url}" title="Re-run this route" style="'
            f'margin-left:14px;flex-shrink:0;background:#2980b9;color:#fff;'
            f'padding:7px 14px;border-radius:5px;font-size:12px;font-weight:bold;'
            f'text-decoration:none;white-space:nowrap;transition:background 0.2s;"'
            f'onmouseover="this.style.background=\'#1a5276\'" '
            f'onmouseout="this.style.background=\'#2980b9\'">'
            f'▶ Use Again'
            f'</a>'

            f'</div>'
        )

    return f'<div class="history-list">{rows}</div>'


# ═════════════════════════════════════════════════════════════════════════════
# STANDALONE PAGE HTML (drop-in templates if you don't want separate .html)
# ═════════════════════════════════════════════════════════════════════════════

def get_settings_page_html(settings: dict, profile: dict, flash_message: str = "") -> str:
    """
    Returns a complete self-contained settings page HTML string.
    Use this if you want to return it directly from a Flask route without
    a separate template file.

    Args:
        settings:      dict from get_user_settings()
        profile:       dict from get_user_profile()
        flash_message: optional message to display at top (e.g. "Settings saved.")

    Returns:
        Full HTML page as a string.

    Usage in main.py /settings route:
        from risk_monitor.user_data import get_settings_page_html
        return get_settings_page_html(settings, profile, flash_msg)
    """
    flash_html = (
        f'<div class="flash-message" style="background:#d4edda;color:#155724;'
        f'border:1px solid #c3e6cb;padding:10px;border-radius:5px;margin-bottom:15px;">'
        f'{flash_message}</div>'
    ) if flash_message else ""

    settings_form = get_settings_form_html(settings)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Settings — SafeRouteAI</title>
  <link rel="stylesheet" href="/static/style.css">
  <style>
    .settings-page {{ max-width: 600px; margin: 40px auto; padding: 0 20px; }}
    .settings-input {{
      display: block; width: 100%; padding: 10px; margin-bottom: 15px;
      border: 1px solid #ddd; border-radius: 5px; box-sizing: border-box;
    }}
    .checkbox-label {{
      display: flex; align-items: center; gap: 10px;
      margin-bottom: 12px; font-size: 14px; cursor: pointer;
    }}
    .section-card {{
      background: white; border-radius: 8px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.08);
      padding: 25px; margin-bottom: 25px;
    }}
    .section-card h3 {{ color: #2c3e50; margin-bottom: 15px; }}
    .danger-btn {{
      background: #e74c3c; color: white; padding: 10px 20px;
      border: none; border-radius: 5px; cursor: pointer; font-size: 14px;
    }}
    .danger-btn:hover {{ background: #c0392b; }}
    .back-link {{ display:inline-block; margin-bottom:20px; color:#2980b9; text-decoration:none; }}
    .back-link:hover {{ text-decoration:underline; }}
  </style>
</head>
<body style="background:#f4f7f6;color:#333;font-family:Segoe UI,sans-serif;overflow:auto;height:auto;">
  <div class="settings-page">
    <a href="/" class="back-link">← Back to Map</a>
    <h1 style="color:#2c3e50;margin-bottom:5px;">Settings</h1>
    <p style="color:#7f8c8d;margin-bottom:25px;">Hi, {profile.get('username', '')} 👋</p>

    {flash_html}

    <div class="section-card">
      {settings_form}
    </div>

    <!-- Profile Section -->
    <div class="section-card">
      <h3>👤 Profile</h3>
      <form method="POST" action="/settings">
        <label class="input-label" style="font-size:13px;font-weight:bold;color:#34495e;display:block;margin-bottom:5px;">Display Name:</label>
        <input type="text" name="display_name" class="settings-input"
               value="{profile.get('display_name', '')}" placeholder="Optional display name">
        <label class="input-label" style="font-size:13px;font-weight:bold;color:#34495e;display:block;margin-bottom:5px;">Email:</label>
        <input type="email" name="email" class="settings-input"
               value="{profile.get('email', '')}" placeholder="Optional — for account recovery">
        <button type="submit" class="btn-primary" style="width:auto;padding:10px 25px;">
          Update Profile
        </button>
      </form>
    </div>

    <!-- Password Change Section -->
    <div class="section-card">
      <h3>🔒 Change Password</h3>
      <form method="POST" action="/account/password">
        <label class="input-label" style="font-size:13px;font-weight:bold;color:#34495e;display:block;margin-bottom:5px;">Current Password:</label>
        <input type="password" name="old_password" class="settings-input" placeholder="Enter current password">
        <label class="input-label" style="font-size:13px;font-weight:bold;color:#34495e;display:block;margin-bottom:5px;">New Password:</label>
        <input type="password" name="new_password" class="settings-input" placeholder="Min. 6 characters">
        <button type="submit" class="btn-primary" style="width:auto;padding:10px 25px;">
          Change Password
        </button>
      </form>
    </div>

    <!-- History Link -->
    <div class="section-card">
      <h3>🗺️ Route History</h3>
      <p style="font-size:14px;color:#555;margin-bottom:15px;">
        View and manage your past route searches.
      </p>
      <a href="/history" class="btn-primary" style="text-decoration:none;display:inline-block;padding:10px 25px;width:auto;">
        View History
      </a>
    </div>
  </div>
</body>
</html>"""


def get_history_page_html(history: list, username: str, flash_message: str = "") -> str:
    """
    Returns a complete self-contained history page HTML string.

    Args:
        history:       list from get_route_history()
        username:      logged-in username
        flash_message: optional message to display

    Returns:
        Full HTML page as a string.

    Usage in main.py /history route:
        from risk_monitor.user_data import get_history_page_html
        hist = get_route_history(chDB_perf, session['user'])
        return get_history_page_html(hist, session['user'])
    """
    flash_html = (
        f'<div style="background:#d4edda;color:#155724;border:1px solid #c3e6cb;'
        f'padding:10px;border-radius:5px;margin-bottom:15px;">{flash_message}</div>'
    ) if flash_message else ""

    history_html = get_history_html(history)
    count        = len(history)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Route History — SafeRouteAI</title>
  <link rel="stylesheet" href="/static/style.css">
  <style>
    .history-page {{ max-width: 700px; margin: 40px auto; padding: 0 20px; }}
    .back-link {{ display:inline-block; margin-bottom:20px; color:#2980b9; text-decoration:none; }}
    .back-link:hover {{ text-decoration:underline; }}
    .section-card {{
      background: white; border-radius: 8px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.08);
      padding: 25px; margin-bottom: 25px;
    }}
    .clear-btn {{
      background: #e74c3c; color: white; padding: 10px 20px;
      border: none; border-radius: 5px; cursor: pointer; font-size: 14px;
      margin-top: 15px;
    }}
    .clear-btn:hover {{ background: #c0392b; }}
  </style>
</head>
<body style="background:#f4f7f6;color:#333;font-family:Segoe UI,sans-serif;overflow:auto;height:auto;">
  <div class="history-page">
    <a href="/" class="back-link">← Back to Map</a>
    <h1 style="color:#2c3e50;margin-bottom:5px;">Route History</h1>
    <p style="color:#7f8c8d;margin-bottom:25px;">
      {count} recent search{'es' if count != 1 else ''} for {username}
    </p>

    {flash_html}

    <div class="section-card">
      {history_html}
      {(
        '<form method="POST" action="/history/clear" style="margin-top:15px;">'
        '<button type="submit" class="clear-btn">🗑️ Clear All History</button>'
        '</form>'
      ) if history else ""}
    </div>

    <p style="text-align:center;">
      <a href="/settings" style="color:#2980b9;">← Back to Settings</a>
    </p>
  </div>
</body>
</html>"""