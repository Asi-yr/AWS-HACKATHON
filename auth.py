import os
import secrets
import jwt
import bcrypt
import sqlite3
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Blueprint, request, jsonify, current_app

load_dotenv()

auth_bp = Blueprint('auth', __name__)

# ── Config ─────────────────────────────────────────────────────────────────────
# JWT_SECRET must match app.secret_key in main.py so token-based user lookups
# remain consistent with the existing session-based auth used by the HTML UI.
# Set JWT_SECRET and FLASK_SECRET_KEY as environment variables (see .env).
JWT_SECRET      = os.environ.get('JWT_SECRET') or 'CHANGE_ME_IN_PRODUCTION'
JWT_EXPIRY_H    = 24          # real session token: 24 hours
TEMP_EXPIRY_MIN = 5           # temp token (2FA pending): 5 minutes
OTP_EXPIRY_MIN  = 2           # OTP code validity: 2 minutes
OTP_MAX_TRIES   = 3           # lock account after this many wrong OTP attempts

# ── SMTP config ────────────────────────────────────────────────────────────────
# Set these as environment variables on your machine, OR fill in directly below.
#
#   Gmail (recommended):
#     SMTP_HOST = smtp.gmail.com
#     SMTP_PORT = 587
#     SMTP_USER = your-gmail@gmail.com
#     SMTP_PASS = your-16-char-app-password   ← generate at myaccount.google.com → Security → App Passwords
#     MAIL_FROM = your-gmail@gmail.com
#
SMTP_HOST = 'smtp.gmail.com'
SMTP_PORT = 587
SMTP_USER = os.environ.get('SMTP_USER', '')   # Set SMTP_USER in your .env file
SMTP_PASS = os.environ.get('SMTP_PASS', '')   # Set SMTP_PASS in your .env file
MAIL_FROM = os.environ.get('MAIL_FROM', SMTP_USER)


# ── DB helper ──────────────────────────────────────────────────────────────────

def get_db():
    """Open a fresh SQLite connection with row_factory enabled."""
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    return conn


# ── Token helpers ──────────────────────────────────────────────────────────────

def make_token(username: str, is_temp=False) -> str:
    """
    Generate a JWT.
    - Real token:  { sub: username, exp: +24h }
    - Temp token:  { sub: username, exp: +5min, 2fa_pending: True }
    """
    payload = {
        'sub': username,
        'exp': datetime.utcnow() + (
            timedelta(minutes=TEMP_EXPIRY_MIN) if is_temp
            else timedelta(hours=JWT_EXPIRY_H)
        ),
    }
    if is_temp:
        payload['2fa_pending'] = True
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')


def decode_token(token: str, require_temp=False):
    """
    Decode a JWT. Returns the payload dict or None if invalid/expired.
    Pass require_temp=True when validating a temp token from /verify-2fa.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        if require_temp and not payload.get('2fa_pending'):
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ── Email helper ───────────────────────────────────────────────────────────────

def _send_otp_email(to_email: str, otp: str):
    """Send the OTP via SMTP. Uses Ethereal for testing."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Your Ligtas One-Time Password'
    msg['From']    = MAIL_FROM
    msg['To']      = to_email

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:500px;margin:auto;
                padding:40px;background:linear-gradient(135deg,#0a0a0a,#111);
                border-radius:20px;border:1px solid rgba(0,217,255,0.3);">
        <h1 style="color:#00d9ff;text-align:center;margin-bottom:30px;
                   font-size:24px;letter-spacing:2px;">LIGTAS</h1>
        <div style="background:#1a1a1a;padding:30px;border-radius:15px;
                    text-align:center;border:1px solid #333;">
            <p style="color:#888;font-size:16px;margin-bottom:20px;">
                Your verification code is:
            </p>
            <div style="font-size:48px;font-weight:bold;color:#00d9ff;
                        letter-spacing:12px;margin:20px 0;">
                {otp}
            </div>
            <p style="color:#666;font-size:14px;margin-top:20px;">
                Valid for {OTP_EXPIRY_MIN} minutes only.<br>
                Do not share this code with anyone.
            </p>
        </div>
    </div>
    """

    msg.attach(MIMEText(html, 'html'))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(MAIL_FROM, to_email, msg.as_string())


# ── POST /api/auth/login ───────────────────────────────────────────────────────
#
# Flutter sends:  { username, password }
#
# Responses:
#   Normal (no 2FA):  { ok: true, token, user }
#   2FA enabled:      { ok: true, requires_2fa: true, temp_token }
#   Bad credentials:  { ok: false, message }  →  HTTP 401
#
@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    data     = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '')

    if not username or not password:
        return jsonify({'ok': False, 'message': 'Username and password are required'}), 400

    db   = get_db()
    user = db.execute(
        'SELECT username, email, password, totp_enabled FROM users WHERE username = ?',
        (username,)
    ).fetchone()
    db.close()

    if not user:
        _log_attempt(username, 'password', request.remote_addr)
        return jsonify({'ok': False, 'message': 'Invalid username or password'}), 401

    # ── Password check — support both bcrypt (new) and werkzeug (legacy) ──────
    stored_hash = user['password']
    pw_ok = False
    if stored_hash.startswith('$2b$') or stored_hash.startswith('$2a$'):
        try:
            pw_ok = bcrypt.checkpw(password.encode(), stored_hash.encode())
        except Exception:
            pw_ok = False
    else:
        # Legacy werkzeug hash (pbkdf2:sha256:...) from the original registration
        from werkzeug.security import check_password_hash as _cwph
        pw_ok = _cwph(stored_hash, password)

    if not pw_ok:
        _log_attempt(username, 'password', request.remote_addr)
        return jsonify({'ok': False, 'message': 'Invalid username or password'}), 401

    # ── 2FA path ───────────────────────────────────────────────────────────────
    if user['totp_enabled']:
        otp        = str(secrets.randbelow(900000) + 100000)  # cryptographically secure 6-digit OTP
        otp_hash   = bcrypt.hashpw(otp.encode(), bcrypt.gensalt()).decode()
        expiry     = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MIN)

        db = get_db()
        db.execute(
            '''UPDATE users
               SET otp = ?, otp_expiry = ?, otp_attempts = 0
               WHERE username = ?''',
            (otp_hash, expiry.strftime('%Y-%m-%d %H:%M:%S'), user['username'])
        )
        db.commit()
        db.close()

        try:
            _send_otp_email(user['email'], otp)
        except Exception as e:
            current_app.logger.error(f'OTP email failed: {e}')
            return jsonify({'ok': False, 'message': 'Could not send OTP email. Try again.'}), 500

        temp_token = make_token(user['username'], is_temp=True)
        return jsonify({
            'ok':           True,
            'requires_2fa': True,
            'temp_token':   temp_token,
        })

    # ── No 2FA — issue real token immediately ──────────────────────────────────
    token = make_token(user['username'])
    return jsonify({
        'ok':    True,
        'token': token,
        'user':  user['username'],
    })


# ── POST /api/auth/verify-2fa ──────────────────────────────────────────────────
#
# Flutter sends:  { temp_token, otp_code }
#
# Responses:
#   Success:         { ok: true, token, user }
#   Wrong code:      { ok: false, message }  →  HTTP 401
#   Expired/locked:  { ok: false, message }  →  HTTP 401
#
@auth_bp.route('/api/auth/verify-2fa', methods=['POST'])
def verify_2fa():
    data       = request.get_json(silent=True) or {}
    temp_token = (data.get('temp_token') or '').strip()
    otp_code   = (data.get('otp_code')   or '').strip()

    if not temp_token or not otp_code:
        return jsonify({'ok': False, 'message': 'temp_token and otp_code are required'}), 400

    payload = decode_token(temp_token, require_temp=True)
    if not payload:
        return jsonify({'ok': False, 'message': 'Session expired. Please log in again.'}), 401

    username = payload['sub']
    db       = get_db()
    user     = db.execute(
        'SELECT username, otp, otp_expiry, otp_attempts FROM users WHERE username = ?',
        (username,)
    ).fetchone()

    if not user:
        db.close()
        return jsonify({'ok': False, 'message': 'User not found.'}), 401

    if user['otp_attempts'] >= OTP_MAX_TRIES:
        db.close()
        return jsonify({
            'ok':      False,
            'message': 'Account locked — too many failed attempts. Please log in again.',
        }), 401

    if not user['otp_expiry'] or datetime.utcnow() > datetime.strptime(user['otp_expiry'], '%Y-%m-%d %H:%M:%S'):
        db.close()
        return jsonify({
            'ok':      False,
            'message': 'OTP has expired. Please log in again to request a new code.',
        }), 401

    stored_otp_hash = user['otp'] or ''
    otp_valid = False
    try:
        otp_valid = bcrypt.checkpw(otp_code.encode(), stored_otp_hash.encode())
    except Exception:
        otp_valid = False

    if not otp_valid:
        db.execute(
            'UPDATE users SET otp_attempts = otp_attempts + 1 WHERE username = ?',
            (username,)
        )
        db.commit()
        _log_attempt(username, 'otp', request.remote_addr)
        remaining = max(0, OTP_MAX_TRIES - (user['otp_attempts'] + 1))
        db.close()

        if remaining == 0:
            return jsonify({
                'ok':      False,
                'message': 'Account locked — too many failed attempts. Please log in again.',
            }), 401

        return jsonify({
            'ok':      False,
            'message': f'Invalid OTP. {remaining} attempt(s) remaining.',
        }), 401

    # ── Correct code ───────────────────────────────────────────────────────────
    db.execute(
        '''UPDATE users
           SET otp = NULL, otp_expiry = NULL, otp_attempts = 0
           WHERE username = ?''',
        (username,)
    )
    db.commit()
    db.close()

    token = make_token(username)
    return jsonify({
        'ok':    True,
        'token': token,
        'user':  username,
    })


# ── POST /api/auth/register ────────────────────────────────────────────────────
#
# Flutter sends:  { username, password, email }
#
# Responses:
#   Success:           { ok: true, token, user }  →  HTTP 201
#   Username/email taken:  { ok: false, message } →  HTTP 409
#
@auth_bp.route('/api/auth/register', methods=['POST'])
def register():
    data     = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '')
    email    = (data.get('email')    or '').strip()

    if not username or not password or not email:
        return jsonify({'ok': False, 'message': 'All fields are required'}), 400

    if len(password) < 8:
        return jsonify({'ok': False, 'message': 'Password must be at least 8 characters'}), 400

    db = get_db()
    existing = db.execute(
        'SELECT username FROM users WHERE username = ? OR email = ?',
        (username, email)
    ).fetchone()

    if existing:
        db.close()
        return jsonify({'ok': False, 'message': 'Username or email already in use'}), 409

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    db.execute(
        '''INSERT INTO users (username, email, password, totp_enabled, otp_attempts)
           VALUES (?, ?, ?, 0, 0)''',
        (username, email, hashed)
    )
    db.commit()
    db.close()

    token = make_token(username)
    return jsonify({
        'ok':    True,
        'token': token,
        'user':  username,
    }), 201


# ── POST /api/auth/logout ──────────────────────────────────────────────────────
@auth_bp.route('/api/auth/logout', methods=['POST'])
def logout():
    # JWT is stateless — client discards the token.
    return jsonify({'ok': True})


# ── GET /api/auth/me ──────────────────────────────────────────────────────────
@auth_bp.route('/api/auth/me', methods=['GET'])
def me():
    token   = _get_bearer_token()
    payload = decode_token(token)
    if not payload:
        return jsonify({'ok': False, 'message': 'Unauthorized'}), 401

    db   = get_db()
    user = db.execute(
        'SELECT username, email, totp_enabled FROM users WHERE username = ?',
        (payload['sub'],)
    ).fetchone()
    db.close()

    if not user:
        return jsonify({'ok': False, 'message': 'User not found'}), 404

    return jsonify({
        'ok':           True,
        'username':     user['username'],
        'email':        user['email'] or '',
        'totp_enabled': bool(user['totp_enabled']),
    })


# ── POST /api/auth/setup-2fa ───────────────────────────────────────────────────
#
# Called from the settings screen to enable 2FA for the account.
# Flutter sends:  Authorization: Bearer <token>
#
@auth_bp.route('/api/auth/setup-2fa', methods=['POST'])
def setup_2fa():
    token   = _get_bearer_token()
    payload = decode_token(token)
    if not payload:
        return jsonify({'ok': False, 'message': 'Unauthorized'}), 401

    db = get_db()
    db.execute(
        'UPDATE users SET totp_enabled = 1 WHERE username = ?',
        (payload['sub'],)
    )
    db.commit()
    db.close()
    return jsonify({'ok': True})


# ── POST /api/auth/disable-2fa ─────────────────────────────────────────────────
@auth_bp.route('/api/auth/disable-2fa', methods=['POST'])
def disable_2fa():
    token   = _get_bearer_token()
    payload = decode_token(token)
    if not payload:
        return jsonify({'ok': False, 'message': 'Unauthorized'}), 401

    db = get_db()
    db.execute(
        'UPDATE users SET totp_enabled = 0, otp = NULL, otp_expiry = NULL WHERE username = ?',
        (payload['sub'],)
    )
    db.commit()
    db.close()
    return jsonify({'ok': True})


# ── POST /api/auth/change-password ────────────────────────────────────────────
#
# Flutter sends:  Authorization: Bearer <token>
#                 { current_password, new_password }
#
@auth_bp.route('/api/auth/change-password', methods=['POST'])
def change_password():
    token   = _get_bearer_token()
    payload = decode_token(token)
    if not payload:
        return jsonify({'ok': False, 'message': 'Unauthorized'}), 401

    data             = request.get_json(silent=True) or {}
    current_password = (data.get('current_password') or '')
    new_password     = (data.get('new_password')     or '')

    if not current_password or not new_password:
        return jsonify({'ok': False, 'message': 'Both passwords are required'}), 400
    if len(new_password) < 8:
        return jsonify({'ok': False, 'message': 'New password must be at least 8 characters'}), 400

    username = payload['sub']
    db       = get_db()
    user     = db.execute('SELECT password FROM users WHERE username = ?', (username,)).fetchone()

    if not user:
        db.close()
        return jsonify({'ok': False, 'message': 'User not found'}), 404

    # Dual-hash verification (bcrypt new / werkzeug legacy)
    stored = user['password']
    if stored.startswith('$2b$') or stored.startswith('$2a$'):
        pw_ok = bcrypt.checkpw(current_password.encode(), stored.encode())
    else:
        from werkzeug.security import check_password_hash as _cwph
        pw_ok = _cwph(stored, current_password)

    if not pw_ok:
        db.close()
        return jsonify({'ok': False, 'message': 'Current password is incorrect'}), 401

    new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    db.execute('UPDATE users SET password = ? WHERE username = ?', (new_hash, username))
    db.commit()
    db.close()
    return jsonify({'ok': True, 'message': 'Password updated successfully'})


# ── POST /api/auth/change-email ───────────────────────────────────────────────
#
# Flutter sends:  Authorization: Bearer <token>
#                 { current_password, new_email }
#
@auth_bp.route('/api/auth/change-email', methods=['POST'])
def change_email():
    import re as _re
    token   = _get_bearer_token()
    payload = decode_token(token)
    if not payload:
        return jsonify({'ok': False, 'message': 'Unauthorized'}), 401

    data             = request.get_json(silent=True) or {}
    current_password = (data.get('current_password') or '')
    new_email        = (data.get('new_email')        or '').strip()

    if not current_password or not new_email:
        return jsonify({'ok': False, 'message': 'Password and new email are required'}), 400
    if not _re.fullmatch(r'[\w\.\+\-]+@[\w\-]+\.[a-zA-Z]{2,}', new_email):
        return jsonify({'ok': False, 'message': 'Invalid email address format'}), 400

    username = payload['sub']
    db       = get_db()
    user     = db.execute('SELECT password FROM users WHERE username = ?', (username,)).fetchone()

    if not user:
        db.close()
        return jsonify({'ok': False, 'message': 'User not found'}), 404

    # Dual-hash verification
    stored = user['password']
    if stored.startswith('$2b$') or stored.startswith('$2a$'):
        pw_ok = bcrypt.checkpw(current_password.encode(), stored.encode())
    else:
        from werkzeug.security import check_password_hash as _cwph
        pw_ok = _cwph(stored, current_password)

    if not pw_ok:
        db.close()
        return jsonify({'ok': False, 'message': 'Current password is incorrect'}), 401

    db.execute('UPDATE users SET email = ? WHERE username = ?', (new_email, username))
    db.commit()
    db.close()
    return jsonify({'ok': True, 'message': 'Email updated successfully'})


# ── Private helpers ────────────────────────────────────────────────────────────

def _log_attempt(identifier: str, attempt_type: str, ip: str):
    """Log a failed login or OTP attempt to login_logs table."""
    try:
        db = get_db()
        db.execute(
            '''INSERT INTO login_logs (identifier, attempt_type, ip_address)
               VALUES (?, ?, ?)''',
            (identifier, attempt_type, ip)
        )
        db.commit()
        db.close()
    except Exception:
        pass  # logging should never crash the app


def _get_bearer_token() -> str:
    """Extract the Bearer token from the Authorization header."""
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        return auth[7:]
    return ''
