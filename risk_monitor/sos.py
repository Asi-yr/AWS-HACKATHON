"""
sos.py
------
SOS / emergency broadcast system for SafeRoute.

Features:
  1. Trusted contacts — store up to 5 phone numbers / emails per user
  2. Live location sharing — generate a shareable link with current coords + route
  3. SOS broadcast — sends alert to all trusted contacts with location
  4. Emergency numbers — quick-dial PH emergency contacts
  5. Panic button — one-tap SOS from the map

DB tables:
  trusted_contacts(id, username, name, contact_type, contact_value, active, created_at)
  sos_events(id, username, lat, lon, route_summary, message, sent_at, contacts_notified)

Integration:
  - init_sos_tables(db)          — call in app startup alongside init_user_tables()
  - add_trusted_contact(...)     — settings page
  - get_trusted_contacts(...)    — settings + SOS send
  - log_sos_event(...)           — called when SOS is triggered
  - get_sos_panel_html()         — injects SOS button + panel into index.html
  - get_share_link(lat, lon, route_summary) → URL string

FIX: All db calls now use the nsql wrapper pattern:
  conn, c = db.get_db_connection()
  db.execute_query(c, "SQL", (params,))
  rows = c.fetchall() / c.fetchone()
  conn.commit()
  c.close(); conn.close()

The original used db.connect() which does not exist on nsql, causing:
  'nsql' object has no attribute 'connect'

Nothing runs on import.
"""

from datetime import datetime, timezone, timedelta
import re

_PHT = timezone(timedelta(hours=8))

# ── Philippine Emergency Numbers ─────────────────────────────────────────────
PH_EMERGENCY_NUMBERS = [
    {"label": "PNP Emergency",        "number": "911",          "icon": "🚔"},
    {"label": "BFP Fire",             "number": "160",          "icon": "🚒"},
    {"label": "Red Cross PH",         "number": "143",          "icon": "🏥"},
    {"label": "NDRRMC Hotline",       "number": "02-8911-5061", "icon": "🆘"},
    {"label": "MMDA Traffic",         "number": "136",          "icon": "🚧"},
    {"label": "LRT/MRT Operations",   "number": "02-8359-4219", "icon": "🚇"},
]


# ── DB Table Init ─────────────────────────────────────────────────────────────

def init_sos_tables(db) -> None:
    """
    Create SOS-related tables if they don't exist.
    Call this alongside init_user_tables() in app startup.
    """
    # FIX: Use get_db_connection() instead of db.connect().
    # FIX: nsql has no executescript() — run each CREATE TABLE separately
    #      using db.execute_query().
    conn, c = db.get_db_connection()
    try:
        db.execute_query(c, """
            CREATE TABLE IF NOT EXISTS trusted_contacts (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    NOT NULL,
                name          TEXT    NOT NULL,
                contact_type  TEXT    NOT NULL DEFAULT 'phone',
                contact_value TEXT    NOT NULL,
                active        INTEGER NOT NULL DEFAULT 1,
                created_at    TEXT    NOT NULL
            )
        """, ())

        db.execute_query(c, """
            CREATE TABLE IF NOT EXISTS sos_events (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                username          TEXT    NOT NULL,
                lat               REAL,
                lon               REAL,
                route_summary     TEXT,
                message           TEXT,
                contacts_notified INTEGER DEFAULT 0,
                sent_at           TEXT    NOT NULL
            )
        """, ())

        db.execute_query(c, """
            CREATE INDEX IF NOT EXISTS idx_contacts_username
                ON trusted_contacts(username)
        """, ())

        db.execute_query(c, """
            CREATE INDEX IF NOT EXISTS idx_sos_username
                ON sos_events(username)
        """, ())

        conn.commit()
        print("🟢 SOS tables ready.")
    except Exception as e:
        print(f"[SOS] init_sos_tables error: {e}")
    finally:
        try:
            c.close()
            conn.close()
        except Exception:
            pass


# ── Trusted Contacts CRUD ─────────────────────────────────────────────────────

def get_trusted_contacts(db, username: str) -> list:
    """
    Returns list of active trusted contacts for a user.
    [{id, name, contact_type, contact_value, created_at}]
    """
    # FIX: db.connect() → db.get_db_connection()
    # FIX: c.execute()  → db.execute_query(c, ...)
    conn, c = db.get_db_connection()
    try:
        db.execute_query(
            c,
            "SELECT id, name, contact_type, contact_value, created_at "
            "FROM trusted_contacts WHERE username=? AND active=1 ORDER BY id",
            (username,)
        )
        rows = c.fetchall()
        return [
            {
                "id":            row[0],
                "name":          row[1],
                "contact_type":  row[2],
                "contact_value": row[3],
                "created_at":    row[4],
            }
            for row in rows
        ]
    except Exception as e:
        print(f"[SOS] get_trusted_contacts error: {e}")
        return []
    finally:
        try:
            c.close()
            conn.close()
        except Exception:
            pass


def _validate_contact_value(contact_type: str, value: str) -> tuple:
    """
    Validate a phone number or email address.
    Returns (is_valid: bool, error_message: str).

    Phone rules:
      - Optional leading + (for international format e.g. +63)
      - 7 to 15 digits after the optional +
      - Spaces, dashes, and parentheses are stripped before checking
      - PH local format 09XXXXXXXXX (11 digits) and
        international +639XXXXXXXXX are both accepted

    Email rules:
      - Standard format: localpart@domain.tld
      - TLD must be at least 2 characters
    """
    value = value.strip()

    if contact_type == "phone":
        # Strip common formatting characters before validating
        digits_only = re.sub(r'[\s\-\(\)]', '', value)
        # Must be + followed by 7-15 digits, or just 7-15 digits
        if not re.fullmatch(r'\+?\d{7,15}', digits_only):
            return (
                False,
                "Invalid phone number. Use a valid format like 09171234567 "
                "or +639171234567 (7–15 digits)."
            )
        return (True, "")

    if contact_type == "email":
        # RFC-5321 simplified — covers all real-world email addresses
        if not re.fullmatch(r'[\w\.\+\-]+@[\w\-]+\.[a-zA-Z]{2,}', value):
            return (
                False,
                "Invalid email address. Use a real email like name@example.com."
            )
        return (True, "")

    return (False, "Unknown contact type.")


def add_trusted_contact(db, username: str, name: str,
                        contact_type: str, contact_value: str) -> dict:
    """
    Add a trusted contact (max 5 per user).
    contact_type: 'phone' or 'email'
    Returns {"ok": bool, "message": str, "id": int or None}
    """
    if not name.strip() or not contact_value.strip():
        return {"ok": False, "message": "Name and contact value are required.", "id": None}
    if contact_type not in ("phone", "email"):
        return {"ok": False, "message": "contact_type must be 'phone' or 'email'.", "id": None}

    # ── Validate the phone number or email before saving ─────────────────────
    is_valid, error_msg = _validate_contact_value(contact_type, contact_value)
    if not is_valid:
        return {"ok": False, "message": error_msg, "id": None}

    # FIX: db.connect() → db.get_db_connection()
    # FIX: c.execute()  → db.execute_query(c, ...)
    conn, c = db.get_db_connection()
    try:
        # Enforce 5-contact limit
        db.execute_query(
            c,
            "SELECT COUNT(*) FROM trusted_contacts WHERE username=? AND active=1",
            (username,)
        )
        row = c.fetchone()
        count = row[0] if row else 0
        if count >= 5:
            return {"ok": False, "message": "Maximum 5 trusted contacts allowed.", "id": None}

        now = datetime.now(_PHT).strftime("%Y-%m-%d %H:%M PHT")
        db.execute_query(
            c,
            "INSERT INTO trusted_contacts "
            "(username, name, contact_type, contact_value, active, created_at) "
            "VALUES (?, ?, ?, ?, 1, ?)",
            (username, name.strip(), contact_type, contact_value.strip(), now)
        )
        conn.commit()
        new_id = c.lastrowid
        return {"ok": True, "message": f"Contact '{name}' added.", "id": new_id}
    except Exception as e:
        print(f"[SOS] add_trusted_contact error: {e}")
        return {"ok": False, "message": str(e), "id": None}
    finally:
        try:
            c.close()
            conn.close()
        except Exception:
            pass


def remove_trusted_contact(db, username: str, contact_id: int) -> dict:
    """Soft-delete a trusted contact (sets active=0)."""
    # FIX: db.connect() → db.get_db_connection()
    # FIX: c.execute()  → db.execute_query(c, ...)
    conn, c = db.get_db_connection()
    try:
        db.execute_query(
            c,
            "UPDATE trusted_contacts SET active=0 WHERE id=? AND username=?",
            (contact_id, username)
        )
        conn.commit()
        return {"ok": True, "message": "Contact removed."}
    except Exception as e:
        print(f"[SOS] remove_trusted_contact error: {e}")
        return {"ok": False, "message": str(e)}
    finally:
        try:
            c.close()
            conn.close()
        except Exception:
            pass


# ── SOS Event Logging ─────────────────────────────────────────────────────────

def log_sos_event(db, username: str, lat: float, lon: float,
                  route_summary: str = "", message: str = "") -> dict:
    """
    Log an SOS event. In production this would also fire SMS/email via
    Twilio/SendGrid. For now it logs and returns the share link.
    Returns {"ok": bool, "share_link": str, "contacts_count": int}
    """
    contacts   = get_trusted_contacts(db, username)
    n_contacts = len(contacts)

    # FIX: db.connect() → db.get_db_connection()
    # FIX: c.execute()  → db.execute_query(c, ...)
    conn, c = db.get_db_connection()
    try:
        now = datetime.now(_PHT).strftime("%Y-%m-%d %H:%M PHT")
        db.execute_query(
            c,
            "INSERT INTO sos_events "
            "(username, lat, lon, route_summary, message, contacts_notified, sent_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (username, lat, lon, route_summary, message, n_contacts, now)
        )
        conn.commit()
    except Exception as e:
        print(f"[SOS] log_sos_event error: {e}")
    finally:
        try:
            c.close()
            conn.close()
        except Exception:
            pass

    share_link = get_share_link(lat, lon, route_summary, username)
    return {
        "ok":             True,
        "share_link":     share_link,
        "contacts_count": n_contacts,
        "message": (
            f"SOS logged. {n_contacts} contact(s) would be notified. "
            f"Share this link: {share_link}"
        ),
    }


def get_share_link(lat: float, lon: float,
                   route_summary: str = "", username: str = "") -> str:
    """Generate a shareable Google Maps link for the user's position."""
    if lat and lon:
        return f"https://maps.google.com/?q={round(lat, 5)},{round(lon, 5)}&z=16&t=m"
    return "https://maps.google.com/"


def get_sos_history(db, username: str, limit: int = 10) -> list:
    """Returns recent SOS events for a user."""
    # FIX: db.connect() → db.get_db_connection()
    # FIX: c.execute()  → db.execute_query(c, ...)
    conn, c = db.get_db_connection()
    try:
        db.execute_query(
            c,
            "SELECT lat, lon, route_summary, message, contacts_notified, sent_at "
            "FROM sos_events WHERE username=? ORDER BY id DESC LIMIT ?",
            (username, limit)
        )
        rows = c.fetchall()
        return [
            {
                "lat":               row[0],
                "lon":               row[1],
                "route_summary":     row[2],
                "message":           row[3],
                "contacts_notified": row[4],
                "sent_at":           row[5],
            }
            for row in rows
        ]
    except Exception as e:
        print(f"[SOS] get_sos_history error: {e}")
        return []
    finally:
        try:
            c.close()
            conn.close()
        except Exception:
            pass


# ── HTML UI ───────────────────────────────────────────────────────────────────

def get_sos_panel_html(contacts: list) -> str:
    """
    Returns the SOS panel HTML — a floating panic button + slide-up drawer.
    Injected into index.html via Jinja: {{ sos_panel | safe }}
    """
    contact_rows = ""
    for ct in contacts:
        icon     = "📞" if ct["contact_type"] == "phone" else "✉️"
        ct_id    = ct["id"]
        ct_name  = ct["name"]
        ct_value = ct["contact_value"]
        contact_rows += (
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:6px 0;border-bottom:1px solid #f0f0f0;">'
            f'<span>{icon} <b>{ct_name}</b> — {ct_value}</span>'
            f'<button onclick="removeTrustedContact({ct_id})" '
            f'style="background:none;border:none;color:#c0392b;cursor:pointer;font-size:13px;">✕</button>'
            f'</div>'
        )
    if not contact_rows:
        contact_rows = (
            '<div style="color:#999;font-size:12px;padding:8px 0;">'
            'No trusted contacts yet. Add one in Settings.</div>'
        )

    emergency_rows = ""
    for e in PH_EMERGENCY_NUMBERS:
        emergency_rows += (
            f'<a href="tel:{e["number"]}" style="display:flex;align-items:center;gap:8px;'
            f'padding:7px 10px;background:#f8f9fa;border-radius:6px;text-decoration:none;color:#2c3e50;">'
            f'<span style="font-size:18px;">{e["icon"]}</span>'
            f'<div><div style="font-weight:bold;font-size:13px;">{e["label"]}</div>'
            f'<div style="color:#e74c3c;font-size:12px;font-weight:bold;">{e["number"]}</div></div>'
            f'</a>'
        )

    return f"""
<!-- ── SOS Panic Button ──────────────────────────────────────────────── -->
<button id="sos-panic-btn" onclick="toggleSosPanel()"
  title="SOS — Emergency"
  style="position:fixed;bottom:24px;right:20px;z-index:100010;
         width:56px;height:56px;border-radius:50%;
         background:#c0392b;color:#fff;border:none;cursor:pointer;
         font-size:22px;font-weight:bold;
         box-shadow:0 4px 16px rgba(192,57,43,0.55);
         animation:sos-pulse 2s ease-in-out infinite;">
  🆘
</button>

<!-- ── SOS Drawer ──────────────────────────────────────────────────────── -->
<div id="sos-panel" style="
  position:fixed;bottom:0;right:0;left:0;z-index:100009;
  background:#fff;border-radius:16px 16px 0 0;
  box-shadow:0 -4px 24px rgba(0,0,0,0.18);
  padding:20px 20px 28px;
  max-height:80vh;overflow-y:auto;
  transform:translateY(100%);transition:transform 0.3s ease;
  font-family:'Segoe UI',Arial,sans-serif;">

  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
    <div style="font-size:18px;font-weight:800;color:#c0392b;">🆘 Emergency / SOS</div>
    <button onclick="toggleSosPanel()" style="background:none;border:none;font-size:20px;cursor:pointer;color:#888;">✕</button>
  </div>

  <button onclick="sendSOS()" style="
    width:100%;padding:13px;background:#c0392b;color:#fff;
    border:none;border-radius:10px;font-size:15px;font-weight:800;
    cursor:pointer;margin-bottom:14px;letter-spacing:0.3px;">
    📍 Broadcast My Location Now
  </button>

  <div id="sos-feedback" style="font-size:12px;color:#27ae60;margin-bottom:10px;min-height:16px;"></div>

  <div style="font-weight:700;font-size:13px;color:#2c3e50;margin-bottom:8px;">📞 Emergency Numbers</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:16px;">
    {emergency_rows}
  </div>

  <div style="font-weight:700;font-size:13px;color:#2c3e50;margin-bottom:8px;">
    👥 My Trusted Contacts
    <span style="font-weight:normal;font-size:11px;color:#888;">(managed in Settings)</span>
  </div>
  <div id="trusted-contacts-list" style="margin-bottom:12px;">
    {contact_rows}
  </div>

  <button onclick="shareLocation()" style="
    width:100%;padding:10px;background:#2980b9;color:#fff;
    border:none;border-radius:8px;font-size:13px;font-weight:700;cursor:pointer;">
    🔗 Copy Share Link
  </button>
  <div id="share-link-feedback" style="font-size:11px;color:#888;margin-top:6px;"></div>
</div>

<style>
@keyframes sos-pulse {{
  0%,100% {{ box-shadow: 0 4px 16px rgba(192,57,43,0.55); transform: scale(1); }}
  50%      {{ box-shadow: 0 4px 28px rgba(192,57,43,0.9);  transform: scale(1.07); }}
}}
</style>

<script>
function toggleSosPanel() {{
  const panel = document.getElementById('sos-panel');
  const open  = panel.style.transform === 'translateY(0%)';
  panel.style.transform = open ? 'translateY(100%)' : 'translateY(0%)';
}}

async function sendSOS() {{
  const fb = document.getElementById('sos-feedback');
  fb.textContent = '⏳ Sending SOS…';
  try {{
    const pos = await new Promise((res, rej) =>
      navigator.geolocation
        ? navigator.geolocation.getCurrentPosition(res, rej, {{timeout:6000}})
        : rej(new Error('Geolocation not available'))
    );
    const resp = await fetch('/api/sos', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{
        lat: pos.coords.latitude,
        lon: pos.coords.longitude,
        message: 'SOS from SafeRoute user'
      }})
    }});
    const data = await resp.json();
    if (data.ok) {{
      fb.style.color = '#27ae60';
      fb.textContent = '✅ ' + data.message;
      if (data.share_link) {{
        try {{ await navigator.clipboard.writeText(data.share_link); }} catch(e) {{}}
      }}
    }} else {{
      fb.style.color = '#c0392b';
      fb.textContent = '❌ ' + (data.message || 'SOS failed.');
    }}
  }} catch(e) {{
    fb.style.color = '#c0392b';
    fb.textContent = '❌ Could not get location: ' + e.message;
  }}
}}

async function shareLocation() {{
  const fb = document.getElementById('share-link-feedback');
  try {{
    const pos = await new Promise((res, rej) =>
      navigator.geolocation.getCurrentPosition(res, rej, {{timeout:6000}})
    );
    const link = `https://maps.google.com/?q=${{pos.coords.latitude}},${{pos.coords.longitude}}&z=16`;
    await navigator.clipboard.writeText(link);
    fb.textContent = '✅ Link copied: ' + link;
    fb.style.color = '#27ae60';
  }} catch(e) {{
    fb.textContent = '❌ ' + e.message;
    fb.style.color = '#c0392b';
  }}
}}

async function removeTrustedContact(id) {{
  if (!confirm('Remove this contact?')) return;
  const resp = await fetch('/api/sos/contacts/' + id, {{method: 'DELETE'}});
  const data = await resp.json();
  if (data.ok) location.reload();
}}
</script>
"""


def get_trusted_contacts_settings_html(contacts: list) -> str:
    """Returns HTML for the trusted contacts section on the Settings page."""
    rows = ""
    for ct in contacts:
        icon     = "📞" if ct["contact_type"] == "phone" else "✉️"
        ct_id    = ct["id"]
        ct_name  = ct["name"]
        ct_value = ct["contact_value"]
        rows += (
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:8px 10px;background:#f8f9fa;border-radius:6px;margin-bottom:6px;">'
            f'<span>{icon} <b>{ct_name}</b> — {ct_value}</span>'
            f'<button onclick="removeContact({ct_id})" '
            f'style="background:#e74c3c;color:#fff;border:none;padding:4px 10px;'
            f'border-radius:4px;cursor:pointer;font-size:12px;">Remove</button>'
            f'</div>'
        )
    if not rows:
        rows = '<div style="color:#999;font-size:12px;padding:8px;">No contacts added yet.</div>'

    return f"""
<div style="background:#fff;border:1px solid #e0e0e0;border-radius:10px;padding:16px;margin-bottom:16px;">
  <div style="font-weight:700;font-size:14px;color:#2c3e50;margin-bottom:10px;">👥 Trusted SOS Contacts</div>
  <div id="contacts-list">{rows}</div>

  <div style="margin-top:12px;padding-top:12px;border-top:1px solid #f0f0f0;">
    <div style="font-weight:600;font-size:13px;margin-bottom:8px;">Add Contact</div>
    <input id="contact-name" type="text" placeholder="Contact name"
      style="width:100%;padding:8px;margin-bottom:6px;border:1px solid #ddd;border-radius:5px;" />
    <select id="contact-type"
      style="width:100%;padding:8px;margin-bottom:6px;border:1px solid #ddd;border-radius:5px;">
      <option value="phone">📞 Phone number</option>
      <option value="email">✉️ Email address</option>
    </select>
    <input id="contact-value" type="text" placeholder="Phone or email"
      style="width:100%;padding:8px;margin-bottom:8px;border:1px solid #ddd;border-radius:5px;" />
    <button onclick="addContact()"
      style="width:100%;padding:9px;background:#27ae60;color:#fff;border:none;
             border-radius:6px;font-weight:700;cursor:pointer;">
      + Add Trusted Contact
    </button>
    <div id="contact-feedback" style="margin-top:6px;font-size:12px;"></div>
  </div>
</div>

<script>
async function addContact() {{
  const name  = document.getElementById('contact-name').value.trim();
  const type  = document.getElementById('contact-type').value;
  const value = document.getElementById('contact-value').value.trim();
  const fb    = document.getElementById('contact-feedback');
  if (!name || !value) {{ fb.textContent = '❌ Fill in all fields.'; fb.style.color='#c0392b'; return; }}
  const resp = await fetch('/api/sos/contacts', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{name, contact_type: type, contact_value: value}})
  }});
  const data = await resp.json();
  fb.textContent = data.ok ? '✅ ' + data.message : '❌ ' + data.message;
  fb.style.color = data.ok ? '#27ae60' : '#c0392b';
  if (data.ok) setTimeout(() => location.reload(), 1000);
}}

async function removeContact(id) {{
  if (!confirm('Remove this contact?')) return;
  const resp = await fetch('/api/sos/contacts/' + id, {{method: 'DELETE'}});
  const data = await resp.json();
  if (data.ok) location.reload();
}}
</script>
"""