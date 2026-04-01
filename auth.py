import random
import jwt
import bcrypt
import sqlite3
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app

auth_bp = Blueprint('auth', __name__)

# ── Config ─────────────────────────────────────────────────────────────────────
# JWT_SECRET must match app.secret_key in main.py so token-based user lookups
# remain consistent with the existing session-based auth used by the HTML UI.
JWT_SECRET      = 'saferoute_super_secret_key'
JWT_EXPIRY_H    = 24          # real session token: 24 hours
TEMP_EXPIRY_MIN = 5           # temp token (2FA pending): 5 minutes
OTP_EXPIRY_MIN  = 2           # OTP code validity: 2 minutes
OTP_MAX_TRIES   = 3           # lock account after this many wrong OTP attempts

# Ethereal SMTP (swap for real SMTP in production)
SMTP_HOST = 'smtp.ethereal.email'
SMTP_PORT = 587
SMTP_USER = 'aisha.purdy@ethereal.email'
SMTP_PASS = 'ePczWGEXG8XDWVYggw'
MAIL_FROM = 'aisha.purdy@ethereal.email'


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
        otp    = str(random.randint(100000, 999999))
        expiry = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MIN)

        db = get_db()
        db.execute(
            '''UPDATE users
               SET otp = ?, otp_expiry = ?, otp_attempts = 0
               WHERE username = ?''',
            (otp, expiry.strftime('%Y-%m-%d %H:%M:%S'), user['username'])
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

    if otp_code != user['otp']:
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

    if len(password) < 6:
        return jsonify({'ok': False, 'message': 'Password must be at least 6 characters'}), 400

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
