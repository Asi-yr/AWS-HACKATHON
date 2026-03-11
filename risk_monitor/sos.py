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

Nothing runs on import.
"""

from datetime import datetime, timezone, timedelta
import json

_PHT = timezone(timedelta(hours=8))

# ── Philippine Emergency Numbers ─────────────────────────────────────────────
PH_EMERGENCY_NUMBERS = [
    {"label": "PNP Emergency",        "number": "911",      "icon": "🚔"},
    {"label": "BFP Fire",             "number": "160",      "icon": "🚒"},
    {"label": "Red Cross PH",         "number": "143",      "icon": "🏥"},
    {"label": "NDRRMC Hotline",       "number": "02-8911-5061", "icon": "🆘"},
    {"label": "MMDA Traffic",         "number": "136",      "icon": "🚧"},
    {"label": "LRT/MRT Operations",   "number": "02-8359-4219", "icon": "🚇"},
]


# ── DB Table Init ─────────────────────────────────────────────────────────────

def init_sos_tables(db) -> None:
    """
    Create SOS-related tables if they don't exist.
    Call this alongside init_user_tables() in app startup.
    """
    try:
        conn = db.connect()
        c    = conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS trusted_contacts (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    NOT NULL,
                name          TEXT    NOT NULL,
                contact_type  TEXT    NOT NULL DEFAULT 'phone',
                contact_value TEXT    NOT NULL,
                active        INTEGER NOT NULL DEFAULT 1,
                created_at    TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sos_events (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                username            TEXT    NOT NULL,
                lat                 REAL,
                lon                 REAL,
                route_summary       TEXT,
                message             TEXT,
                contacts_notified   INTEGER DEFAULT 0,
                sent_at             TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_contacts_username
                ON trusted_contacts(username);
            CREATE INDEX IF NOT EXISTS idx_sos_username
                ON sos_events(username);
        """)
        conn.commit()
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ── Trusted Contacts CRUD ─────────────────────────────────────────────────────

def get_trusted_contacts(db, username: str) -> list:
    """
    Returns list of active trusted contacts for a user.
    [{id, name, contact_type, contact_value, created_at}]
    """
    try:
        conn = db.connect()
        c    = conn.cursor()
        rows = c.execute(
            "SELECT id, name, contact_type, contact_value, created_at "
            "FROM trusted_contacts WHERE username=? AND active=1 ORDER BY id",
            (username,)
        ).fetchall()
        conn.close()
        return [{"id": r[0], "name": r[1], "contact_type": r[2],
                 "contact_value": r[3], "created_at": r[4]} for r in rows]
    except Exception:
        return []


def add_trusted_contact(db, username: str, name: str,
                         contact_type: str, contact_value: str) -> dict:
    """
    Add a trusted contact (max 5 per user).
    contact_type: 'phone' or 'email'

    Returns {"ok": bool, "message": str, "id": int or None}
    """
    # Validate
    if not name.strip() or not contact_value.strip():
        return {"ok": False, "message": "Name and contact value are required.", "id": None}
    if contact_type not in ("phone", "email"):
        return {"ok": False, "message": "contact_type must be 'phone' or 'email'.", "id": None}

    try:
        conn = db.connect()
        c    = conn.cursor()

        # Enforce limit
        count = c.execute(
            "SELECT COUNT(*) FROM trusted_contacts WHERE username=? AND active=1",
            (username,)
        ).fetchone()[0]
        if count >= 5:
            conn.close()
            return {"ok": False, "message": "Maximum 5 trusted contacts allowed.", "id": None}

        now = datetime.now(_PHT).strftime("%Y-%m-%d %H:%M PHT")
        c.execute(
            "INSERT INTO trusted_contacts (username, name, contact_type, contact_value, active, created_at) "
            "VALUES (?, ?, ?, ?, 1, ?)",
            (username, name.strip(), contact_type, contact_value.strip(), now)
        )
        conn.commit()
        new_id = c.lastrowid
        conn.close()
        return {"ok": True, "message": f"Contact '{name}' added.", "id": new_id}
    except Exception as e:
        return {"ok": False, "message": str(e), "id": None}


def remove_trusted_contact(db, username: str, contact_id: int) -> dict:
    """Soft-delete a trusted contact."""
    try:
        conn = db.connect()
        c    = conn.cursor()
        c.execute(
            "UPDATE trusted_contacts SET active=0 WHERE id=? AND username=?",
            (contact_id, username)
        )
        conn.commit()
        conn.close()
        return {"ok": True, "message": "Contact removed."}
    except Exception as e:
        return {"ok": False, "message": str(e)}


# ── SOS Event Logging ─────────────────────────────────────────────────────────

def log_sos_event(db, username: str, lat: float, lon: float,
                   route_summary: str = "", message: str = "") -> dict:
    """
    Log an SOS event to the database.
    In a production system this would also trigger SMS/email via Twilio/SendGrid.
    For now it logs the event and returns the share link.

    Returns {"ok": bool, "share_link": str, "contacts_count": int}
    """
    contacts = get_trusted_contacts(db, username)
    n_contacts = len(contacts)

    try:
        conn = db.connect()
        c    = conn.cursor()
        now  = datetime.now(_PHT).strftime("%Y-%m-%d %H:%M PHT")
        c.execute(
            "INSERT INTO sos_events (username, lat, lon, route_summary, message, "
            "contacts_notified, sent_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (username, lat, lon, route_summary, message, n_contacts, now)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    share_link = get_share_link(lat, lon, route_summary, username)

    return {
        "ok":            True,
        "share_link":    share_link,
        "contacts_count": n_contacts,
        "message":       (f"SOS logged. {n_contacts} contact(s) would be notified. "
                          f"Share this link: {share_link}"),
    }


def get_share_link(lat: float, lon: float,
                    route_summary: str = "", username: str = "") -> str:
    """
    Generate a shareable Google Maps link with the user's current position.
    In a full deployment this would be a short link to your own tracking endpoint.
    """
    if lat and lon:
        return (f"https://maps.google.com/?q={round(lat,5)},{round(lon,5)}"
                f"&z=16&t=m")
    return "https://maps.google.com/"


def get_sos_history(db, username: str, limit: int = 10) -> list:
    """Returns recent SOS events for a user."""
    try:
        conn = db.connect()
        c    = conn.cursor()
        rows = c.execute(
            "SELECT lat, lon, route_summary, message, contacts_notified, sent_at "
            "FROM sos_events WHERE username=? ORDER BY id DESC LIMIT ?",
            (username, limit)
        ).fetchall()
        conn.close()
        return [{"lat": r[0], "lon": r[1], "route_summary": r[2],
                 "message": r[3], "contacts_notified": r[4], "sent_at": r[5]}
                for r in rows]
    except Exception:
        return []


# ── HTML UI ───────────────────────────────────────────────────────────────────

def get_sos_panel_html(contacts: list) -> str:
    """
    Returns the SOS panel HTML — a floating panic button + slide-up drawer.
    Injected into index.html via Jinja: {{ sos_panel | safe }}

    The panel contains:
      - Panic button (red, fixed bottom-right)
      - Emergency numbers quick-dial
      - Trusted contacts list
      - "Share my location" button
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
        contact_rows = ('<div style="color:#999;font-size:12px;padding:8px 0;">'
                        'No trusted contacts yet. Add one in Settings.</div>')

    emergency_rows = ""
    for e in PH_EMERGENCY_NUMBERS:
        e_number = e["number"]
        e_icon   = e["icon"]
        e_label  = e["label"]
        emergency_rows += (
            f'<a href="tel:{e_number}" style="display:flex;align-items:center;gap:8px;'
            f'padding:7px 10px;background:#f8f9fa;border-radius:6px;text-decoration:none;color:#2c3e50;">'
            f'<span style="font-size:18px;">{e_icon}</span>'
            f'<div><div style="font-weight:bold;font-size:13px;">{e_label}</div>'
            f'<div style="color:#e74c3c;font-size:12px;font-weight:bold;">{e_number}</div></div>'
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

  <!-- Share location -->
  <button onclick="sendSOS()" style="
    width:100%;padding:13px;background:#c0392b;color:#fff;
    border:none;border-radius:10px;font-size:15px;font-weight:800;
    cursor:pointer;margin-bottom:14px;letter-spacing:0.3px;">
    📍 Broadcast My Location Now
  </button>

  <div id="sos-feedback" style="font-size:12px;color:#27ae60;margin-bottom:10px;min-height:16px;"></div>

  <!-- Emergency numbers -->
  <div style="font-weight:700;font-size:13px;color:#2c3e50;margin-bottom:8px;">📞 Emergency Numbers</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:16px;">
    {emergency_rows}
  </div>

  <!-- Trusted contacts -->
  <div style="font-weight:700;font-size:13px;color:#2c3e50;margin-bottom:8px;">
    👥 My Trusted Contacts
    <span style="font-weight:normal;font-size:11px;color:#888;">(managed in Settings)</span>
  </div>
  <div id="trusted-contacts-list" style="margin-bottom:12px;">
    {contact_rows}
  </div>

  <!-- Share link -->
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
    const lat = pos.coords.latitude;
    const lon = pos.coords.longitude;
    const resp = await fetch('/api/sos', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{lat, lon, message: 'SOS from SafeRoute user'}})
    }});
    const data = await resp.json();
    if (data.ok) {{
      fb.style.color = '#27ae60';
      fb.textContent = '✅ ' + data.message;
      // Copy share link automatically
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
    const lat = pos.coords.latitude;
    const lon = pos.coords.longitude;
    const link = `https://maps.google.com/?q=${{lat}},${{lon}}&z=16`;
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
    """
    Returns HTML for the trusted contacts section on the Settings page.
    """
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