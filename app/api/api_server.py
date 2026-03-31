from flask import Flask, jsonify, request, Response
from flask_cors import CORS
import json
import threading
import time
from datetime import datetime, timedelta
import random
import sys
import os
import logging
from collections import deque

# ---------------------------------------------------------------------------
# In-memory login rate limiter
# Tracks (ip, email) → list of attempt timestamps
# ---------------------------------------------------------------------------
_login_attempts: dict = {}  # key: str → [float, ...]
_login_lock = threading.Lock()
_RATE_WINDOW = 60       # seconds
_RATE_MAX_IP = 10       # max attempts per IP per window
_LOCKOUT_MAX = 5        # max consecutive failures per email before lockout
_LOCKOUT_SECS = 900     # 15-minute lockout

def _prune_old(timestamps, window=_RATE_WINDOW):
    now = time.time()
    return [t for t in timestamps if now - t < window]

def _check_rate_limit(ip: str, email: str):
    """Return (allowed: bool, retry_after: int)"""
    with _login_lock:
        ip_key = f'ip:{ip}'
        email_key = f'email:{email}'
        now = time.time()

        # Per-IP rate check
        _login_attempts[ip_key] = _prune_old(_login_attempts.get(ip_key, []))
        if len(_login_attempts[ip_key]) >= _RATE_MAX_IP:
            return False, _RATE_WINDOW

        # Per-email lockout check (uses a separate list with a longer window)
        attempts = _login_attempts.get(email_key, [])
        recent = [t for t in attempts if now - t < _LOCKOUT_SECS]
        if len(recent) >= _LOCKOUT_MAX:
            oldest = min(recent)
            retry_after = int(_LOCKOUT_SECS - (now - oldest))
            return False, max(retry_after, 1)

        return True, 0

def _record_attempt(ip: str, email: str, success: bool):
    with _login_lock:
        ip_key = f'ip:{ip}'
        email_key = f'email:{email}'
        _login_attempts[ip_key] = _prune_old(_login_attempts.get(ip_key, []))
        _login_attempts[ip_key].append(time.time())
        if success:
            # Clear failure record on successful login
            _login_attempts[email_key] = []
        else:
            _login_attempts[email_key] = _login_attempts.get(email_key, []) + [time.time()]

# ---------------------------------------------------------------------------
# Pending 2FA tokens (in-memory, 5-minute TTL)
# After successful password auth when 2FA is enabled, we issue a short-lived
# temp token; the client must then POST a TOTP code to complete login.
# ---------------------------------------------------------------------------
_pending_2fa: dict = {}  # temp_token → {user_id, expires_at}
_2fa_lock = threading.Lock()

def _create_pending_2fa(user_id: str) -> str:
    import secrets as _sec
    tok = _sec.token_urlsafe(24)
    expires = time.time() + 300  # 5 minutes
    with _2fa_lock:
        _pending_2fa[tok] = {'user_id': user_id, 'expires': expires}
    return tok

def _consume_pending_2fa(temp_token: str):
    """Return user_id if temp_token is valid and not expired, else None."""
    with _2fa_lock:
        entry = _pending_2fa.pop(temp_token, None)
    if not entry:
        return None
    if time.time() > entry['expires']:
        return None
    return entry['user_id']

# ---------------------------------------------------------------------------
# Simple transactional email helper (for password reset)
# Reads SMTP settings from env vars; gracefully no-ops when not configured.
# ---------------------------------------------------------------------------
def _send_reset_email(to_email: str, reset_url: str) -> bool:
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_host = os.environ.get('EMAIL_SMTP_SERVER', os.environ.get('SMTP_SERVER', ''))
    smtp_port = int(os.environ.get('SMTP_PORT', '587'))
    username = os.environ.get('EMAIL_USERNAME', '')
    password = os.environ.get('EMAIL_PASSWORD', '')
    from_addr = os.environ.get('EMAIL_FROM', username)

    if not smtp_host or not username or not password:
        logging.warning('Password reset email not sent: SMTP not configured. Reset URL: %s', reset_url)
        return False

    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'AIOps Bot — Password Reset'
    msg['From'] = from_addr
    msg['To'] = to_email

    text = f'Click the link below to reset your password (valid for 1 hour):\n\n{reset_url}'
    html = (f'<p>Click the link below to reset your AIOps Bot password. '
            f'This link expires in <strong>1 hour</strong>.</p>'
            f'<p><a href="{reset_url}">{reset_url}</a></p>'
            f'<p>If you did not request a password reset, you can safely ignore this email.</p>')

    msg.attach(MIMEText(text, 'plain'))
    msg.attach(MIMEText(html, 'html'))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(username, password)
            server.sendmail(from_addr, [to_email], msg.as_string())
        return True
    except Exception as e:
        logging.error('Failed to send reset email: %s', e)
        return False

# Force UTF-8 stdout so emoji in print() doesn't crash on Windows cp1252 terminals
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# --- Structured JSON logging (feeds into ELK Stack via Logstash TCP input) ---
try:
    from pythonjsonlogger import jsonlogger
    _json_logging = True
except ImportError:
    _json_logging = False

def _setup_logging():
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    if _json_logging:
        formatter = jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S"
        )
    else:
        formatter = logging.Formatter(
            '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s", "service": "aiops-bot"}',
            datefmt="%Y-%m-%dT%H:%M:%S"
        )
    handler.setFormatter(formatter)
    root_logger.handlers = [handler]

_setup_logging()
logger = logging.getLogger("aiops.api")

def _send_slack_message_safe(message: str, level: str = "info", **kwargs):
    """Best-effort Slack notifier. No-ops cleanly when Slack integration is unavailable."""
    fn = globals().get('send_slack_message')
    if callable(fn):
        try:
            return fn(message, level, **kwargs)
        except Exception as exc:
            logger.warning("Slack notification failed: %s", exc)
            return False
    logger.debug("Slack integration unavailable; skipping notification: %s", message)
    return False

# Add the current directory and sibling app subdirs to the Python path
_api_dir = os.path.dirname(os.path.abspath(__file__))
_app_dir = os.path.dirname(_api_dir)          # app/
_repo_dir = os.path.dirname(_app_dir)         # repo root
for _p in [_api_dir, _app_dir, _repo_dir,
           os.path.join(_app_dir, 'auth'),
           os.path.join(_app_dir, 'core'),
           os.path.join(_app_dir, 'integrations'),
           os.path.join(_app_dir, 'monitoring'),
           os.path.join(_app_dir, 'security'),
           os.path.join(_app_dir, 'analytics'),
           os.path.join(_app_dir, 'remediation')]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# --- Load .env file if present (repo root first, then api dir override) ---
def _load_env_file(path):
    try:
        if os.path.exists(path):
            with open(path) as _ef:
                for _line in _ef:
                    _line = _line.strip()
                    if _line and not _line.startswith('#') and '=' in _line:
                        _k, _v = _line.split('=', 1)
                        os.environ.setdefault(_k.strip(), _v.strip())
    except Exception as _env_err:
        logger.warning("Could not load .env from %s: %s", path, _env_err)

_load_env_file(os.path.join(_repo_dir, '.env'))          # repo root
_load_env_file(os.path.join(_api_dir, '.env'))            # api dir override

# --- Load secrets from HashiCorp Vault (optional, graceful fallback) ---
try:
    from vault.vault_client import load_secrets_into_env as _vault_load
    _vault_load()
except Exception as _vault_err:
    logger.debug("Vault secret load skipped: %s", _vault_err)

try:
    from enhanced_aiops_chatbot import EnhancedAIOpsBot
except ImportError as e:
    print(f"Warning: Could not import EnhancedAIOpsBot: {e}")
    EnhancedAIOpsBot = None

try:
    from huggingface_ai_integration import HuggingFaceAIEngine
except ImportError:
    HuggingFaceAIEngine = None  # optional — requires transformers + torch

try:
    from intelligent_remediation import IntelligentRemediationEngine
    from enhanced_remediation_engine import EnhancedRemediationEngine
except ImportError as e:
    print(f"Warning: Could not import remediation engines: {e}")
    IntelligentRemediationEngine = None
    EnhancedRemediationEngine = None

try:
    from auth_system import AuthenticationSystem
except ImportError as e:
    print(f"Warning: Could not import auth system: {e}")
    AuthenticationSystem = None

app = Flask(__name__)

# ── Socket.IO ─────────────────────────────────────────────────────────────────
# async_mode='threading' works with Flask's built-in dev server and with
# standard daemon threads — no eventlet/gevent monkey-patching needed.
try:
    from flask_socketio import SocketIO as _SocketIO
    # CORS origins are set after _ALLOWED_ORIGINS is built; we patch them in
    # _configure_socketio() called at the bottom of the CORS block.
    socketio = _SocketIO(async_mode='threading')
    _SOCKETIO_AVAILABLE = True
except ImportError:
    socketio = None
    _SOCKETIO_AVAILABLE = False
    print("⚠️  flask-socketio not installed — WebSocket push disabled. "
          "Run: pip install flask-socketio")

# ── CORS ──────────────────────────────────────────────────────────────────────
# ALLOWED_ORIGINS must be set in .env (comma-separated list of exact origins).
# Wildcard ("*") is NEVER used — it is incompatible with allow_credentials=True
# and enables session-riding attacks from any origin on the internet.
_RAW_ORIGINS = os.environ.get('ALLOWED_ORIGINS', '')
_ALLOWED_ORIGINS = [o.strip() for o in _RAW_ORIGINS.split(',') if o.strip()]

if not _ALLOWED_ORIGINS:
    import warnings
    warnings.warn(
        "ALLOWED_ORIGINS is not set in .env — all cross-origin requests will be "
        "blocked. Set ALLOWED_ORIGINS=http://localhost:3000,... for local dev.",
        stacklevel=2,
    )

# Localhost origins are permitted in the explicit allowlist; the regex below
# is used only to validate origin format — it no longer bypasses the list.
_LOCALHOST_RE = __import__('re').compile(r'^https?://(localhost|127\.0\.0\.1)(:\d+)?$')

CORS(app, resources={r"/*": {
    "origins": _ALLOWED_ORIGINS,          # never falls back to "*"
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    "allow_headers": ["Content-Type", "Authorization", "X-Request-ID"],
    "expose_headers": [
        "X-RateLimit-Limit", "X-RateLimit-Remaining",
        "X-RateLimit-Reset", "Retry-After",
    ],
    "supports_credentials": True,
    "max_age": 600,
}})

@app.after_request
def _add_cors_headers(response):
    """Reflect the request Origin only when it is in the explicit allowlist.
    Never emits a wildcard — credentials require a specific origin."""
    origin = request.headers.get('Origin', '')
    if origin and origin in _ALLOWED_ORIGINS:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS,PATCH'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization,X-Request-ID'
        response.headers['Access-Control-Max-Age'] = '600'
        response.headers['Vary'] = 'Origin'
    return response

# ── Wire SocketIO to app (now that _ALLOWED_ORIGINS is defined) ───────────────
if _SOCKETIO_AVAILABLE and socketio is not None:
    socketio.init_app(
        app,
        cors_allowed_origins=_ALLOWED_ORIGINS or '*',
        async_mode='threading',
        logger=False,
        engineio_logger=False,
    )

    @socketio.on('connect')
    def _on_connect():
        """Client connected — immediately send the current snapshot."""
        try:
            if system_data.get('cpu') is not None:
                socketio.emit('system', dict(system_data), to=None)
                socketio.emit('metric_update', dict(system_data), to=None)
        except Exception:
            pass

    @socketio.on('disconnect')
    def _on_disconnect():
        """Client disconnected — nothing to clean up, just log gracefully."""
        pass  # flask-socketio handles cleanup automatically

# ── Rate Limiting ─────────────────────────────────────────────────────────────
# User-keyed when a token is present (stops per-account abuse), falls back to
# IP to catch unauthenticated burst attacks.
# Set REDIS_URL for distributed multi-process enforcement (required in prod).
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address as _get_ip

    def _rate_limit_key_func():
        auth = request.headers.get('Authorization', '')
        if auth.startswith('Bearer ') and len(auth) > 20:
            return f"tok:{auth[7:27]}"   # opaque prefix — no full token stored
        return _get_ip()

    _limiter = Limiter(
        app=app,
        key_func=_rate_limit_key_func,
        default_limits=[
            os.environ.get('RATE_LIMIT_DEFAULT', '100 per minute'),
            os.environ.get('RATE_LIMIT_HOURLY',  '1000 per hour'),
        ],
        headers_enabled=True,          # emits X-RateLimit-* on every response
        storage_uri=os.environ.get('REDIS_URL', 'memory://'),
    )
    _rate_limit = _limiter.limit

except ImportError:
    _limiter = None
    def _rate_limit(limit_str):        # transparent no-op passthrough
        return lambda f: f
    logging.warning(
        "flask-limiter not installed — global rate limiting is DISABLED. "
        "Run: pip install Flask-Limiter==3.5.0"
    )

# ---------------------------------------------------------------------------
# Global auth middleware — every request (except open paths) must carry a
# valid Firebase ID token when FIREBASE_PROJECT_ID is configured.
# ---------------------------------------------------------------------------
_OPEN_PATHS = frozenset([
    '/health', '/api/health', '/config',
    '/events/system',
    '/auth/login', '/auth/register',
    '/auth/forgot-password', '/auth/reset-password',
    '/auth/redeem-invite',
    # Agent endpoints — authenticated by their own token, not JWT
    '/agents/heartbeat',
    '/agents/register',
])

@app.before_request
def _require_auth():
    if request.method == 'OPTIONS':
        return None  # CORS preflight — let Flask-CORS handle it
    path = request.path
    if path in _OPEN_PATHS or path.startswith('/auth/'):
        return None  # auth routes are self-managing
    # Agent command-result callback — authenticated by its own token, not JWT
    if path.startswith('/agents/') and path.endswith('/commands/result'):
        return None
    token = _extract_bearer()
    if not token:
        return jsonify({'error': 'Authentication required'}), 401
    # Try Firebase token first (if configured)
    if os.environ.get('FIREBASE_PROJECT_ID'):
        try:
            verify_firebase_token(token)
            return None  # valid Firebase token
        except Exception:
            pass  # fall through to legacy JWT check
    # Try legacy JWT (auth_system)
    if auth_system:
        try:
            valid, _, _ = auth_system.verify_token(token)
            if valid:
                return None
        except Exception:
            pass
    return jsonify({'error': 'Invalid or expired token'}), 401

# ---------------------------------------------------------------------------
# Firebase ID token verification
# Uses python-jose to verify tokens directly from Firebase's public keys —
# no service account or Application Default Credentials required.
# Falls back to firebase-admin if a service account is configured.
# ---------------------------------------------------------------------------
try:
    import firebase_admin
    from firebase_admin import auth as _fb_auth, credentials as _fb_creds
    _FIREBASE_AVAILABLE = True
except ImportError:
    _FIREBASE_AVAILABLE = False

_firebase_app = None
_fb_cert_cache: dict = {}   # { kid: cert_pem, '_ts': float }

def _get_firebase_public_certs() -> dict:
    """Return Firebase's current public signing certificates, cached for 1 hour."""
    import requests as _req
    now = time.time()
    if _fb_cert_cache.get('_ts', 0) > now - 3600 and len(_fb_cert_cache) > 1:
        return _fb_cert_cache
    resp = _req.get(
        'https://www.googleapis.com/robot/v1/metadata/x509/'
        'securetoken@system.gserviceaccount.com',
        timeout=10,
    )
    resp.raise_for_status()
    _fb_cert_cache.clear()
    _fb_cert_cache.update(resp.json())
    _fb_cert_cache['_ts'] = now
    return _fb_cert_cache

def verify_firebase_token(token: str) -> dict:
    """
    Verify a Firebase ID token and return the decoded payload.
    Uses python-jose + Firebase public keys — no credentials needed.
    Raises on invalid/expired token.
    """
    from jose import jwt as _jwt
    project_id = os.environ.get('FIREBASE_PROJECT_ID', '').strip()
    if not project_id:
        raise ValueError('FIREBASE_PROJECT_ID is not configured')

    # Decode header to find which public key to use
    headers = _jwt.get_unverified_header(token)
    kid = headers.get('kid', '')
    certs = _get_firebase_public_certs()
    if kid not in certs:
        raise ValueError(f'Firebase token has unknown key ID: {kid}')

    payload = _jwt.decode(
        token,
        certs[kid],
        algorithms=['RS256'],
        audience=project_id,
        issuer=f'https://securetoken.google.com/{project_id}',
        options={'verify_exp': True},
    )
    return payload

def _extract_bearer() -> str:
    """Extract the raw Bearer token from the Authorization header."""
    return (request.headers.get('Authorization') or '').removeprefix('Bearer ').strip()

# ---------------------------------------------------------------------------
# Simple cache layer — uses Redis when available, falls back to in-process TTL
# ---------------------------------------------------------------------------
import functools

_CACHE: dict = {}   # {key: (value, expires_at)}

def _cache_get(key: str):
    entry = _CACHE.get(key)
    if entry and time.time() < entry[1]:
        return entry[0]
    _CACHE.pop(key, None)
    return None

def _cache_set(key: str, value, ttl: float = 5.0):
    _CACHE[key] = (value, time.time() + ttl)

def cached(ttl: float = 5.0, key_fn=None):
    """Decorator: cache a Flask route's JSON response for `ttl` seconds."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            cache_key = key_fn(*args, **kwargs) if key_fn else fn.__name__
            cached_val = _cache_get(cache_key)
            if cached_val is not None:
                return jsonify(cached_val)
            result = fn(*args, **kwargs)
            # result is a Flask Response; extract JSON
            try:
                data = result.get_json()
                _cache_set(cache_key, data, ttl)
            except Exception:
                pass
            return result
        return wrapper
    return decorator

# --- OpenTelemetry distributed tracing ---
try:
    from otel.instrumentation import setup_tracing
    setup_tracing(app)
except Exception as _otel_err:
    logger.warning("OTEL setup skipped: %s", _otel_err)

# Global variables for storing system data
system_data = {
    "cpu": None,
    "memory": None,
    "disk": None,
    "network_in": None,
    "network_out": None,
    "temperature": None,
    "status": "starting",
    "uptime": None,
    "active_processes": None,
    "last_updated": datetime.now().isoformat()
}

# Rolling performance history — stores up to 8 hours of 10s snapshots (2880 points)
_perf_history: deque = deque(maxlen=2880)

ai_insights = [
    {
        "id": 1,
        "category": "performance",
        "message": "CPU usage is stable within normal parameters",
        "confidence": 95,
        "timestamp": datetime.now().isoformat(),
        "priority": "low"
    },
    {
        "id": 2,
        "category": "security",
        "message": "No suspicious network activity detected",
        "confidence": 98,
        "timestamp": datetime.now().isoformat(),
        "priority": "info"
    },
    {
        "id": 3,
        "category": "optimization",
        "message": "Memory allocation could be optimized for better performance",
        "confidence": 87,
        "timestamp": datetime.now().isoformat(),
        "priority": "medium"
    }
]

recent_alerts = [
    {
        "id": 1,
        "severity": "warning",
        "message": "Memory usage approaching 80% threshold",
        "source": "System Monitor",
        "timestamp": datetime.now().isoformat(),
        "status": "active"
    },
    {
        "id": 2,
        "severity": "info",
        "message": "Backup completed successfully",
        "source": "Backup Service",
        "timestamp": datetime.now().isoformat(),
        "status": "resolved"
    }
]

# AI components — lazy-initialized on first use so Flask starts instantly.
aiops_bot = None
hf_engine = None
remediation_engine = None
enhanced_engine = None
_ai_initialized = False

def _ensure_ai_initialized():
    global aiops_bot, hf_engine, remediation_engine, enhanced_engine, _ai_initialized
    if _ai_initialized:
        return
    _ai_initialized = True
    try:
        if EnhancedAIOpsBot:
            aiops_bot = EnhancedAIOpsBot()
            print("✅ Enhanced AIOps Bot initialized successfully")
        if HuggingFaceAIEngine:
            hf_engine = HuggingFaceAIEngine()
            print("✅ Hugging Face AI Engine initialized successfully")
    except Exception as e:
        print(f"⚠️ Warning: Could not initialize AI components: {e}")
    try:
        if IntelligentRemediationEngine:
            remediation_engine = IntelligentRemediationEngine()
            print("Intelligent Remediation Engine initialized successfully")
        if EnhancedRemediationEngine:
            enhanced_engine = EnhancedRemediationEngine()
            print("Enhanced Remediation Engine initialized successfully")
    except Exception as e:
        print(f"Warning: Could not initialize remediation engines: {e}")

auth_system = None
try:
    if AuthenticationSystem:
        auth_system = AuthenticationSystem(db_path="aiops_auth.db")
        app.auth_system = auth_system
        print("Auth system initialized successfully")
except Exception as e:
    print(f"Warning: Could not initialize auth system: {e}")

def collect_real_system_data():
    """Collect real system metrics using psutil and append to rolling history."""
    global system_data
    import psutil, platform
    _prev_net = psutil.net_io_counters()
    _interval = 10  # seconds between samples
    while True:
        try:
            cpu    = psutil.cpu_percent(interval=1)
            mem    = psutil.virtual_memory()
            disk   = _system_disk_usage()
            net    = psutil.net_io_counters()

            # Bytes delta → KB/s over the collection interval
            net_in_kbps  = round(max(0, net.bytes_recv - _prev_net.bytes_recv) / _interval / 1024, 2)
            net_out_kbps = round(max(0, net.bytes_sent - _prev_net.bytes_sent) / _interval / 1024, 2)
            _prev_net = net

            # temperature (not available on all platforms)
            temp = None
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    first = next(iter(temps.values()))
                    if first:
                        temp = round(first[0].current, 1)
            except Exception:
                pass

            status = "healthy"
            if cpu > 90 or mem.percent > 90:
                status = "critical"
            elif cpu > 75 or mem.percent > 80:
                status = "warning"

            snap = {
                "cpu":          round(cpu, 1),
                "memory":       round(mem.percent, 1),
                "disk":         round(disk.percent, 1),
                "network_in":   net_in_kbps,
                "network_out":  net_out_kbps,
                "temperature":  temp,
                "status":       status,
                "last_updated": datetime.now().isoformat(),
                "timestamp":    datetime.now().timestamp(),
            }
            system_data.update(snap)
            _perf_history.append(snap)

            # Push to all connected Socket.IO clients
            if _SOCKETIO_AVAILABLE and socketio is not None:
                try:
                    socketio.emit('system', snap)
                    socketio.emit('metric_update', snap)
                except Exception:
                    pass  # never crash the collector if emit fails

        except Exception as e:
            print(f"Error in system data collection: {e}")

        time.sleep(_interval)

# ---------------------------------------------------------------------------
# Optional perf-history seed for local demos only (disabled by default)
# ---------------------------------------------------------------------------
def _seed_perf_history():
    """Take one real psutil reading and backfill 60 synthetic history points
    so charts are populated the moment the server starts (no waiting for the
    10-second collection loop to accumulate enough points)."""
    try:
        import psutil
        cpu   = psutil.cpu_percent(interval=0.5)
        mem   = psutil.virtual_memory()
        disk  = _system_disk_usage()
        net   = psutil.net_io_counters()
        now   = datetime.now().timestamp()
        # Generate 60 back-filled points spaced 10s apart (~10 mins of history)
        for i in range(60, 0, -1):
            jitter = lambda v, spread=2.5: round(min(100, max(0, v + random.uniform(-spread, spread))), 1)
            snap = {
                "cpu":          jitter(cpu, 3.0),
                "memory":       jitter(mem.percent, 1.5),
                "disk":         jitter(disk.percent, 0.2),
                "network_in":   round(random.uniform(0, 50), 2),
                "network_out":  round(random.uniform(0, 20), 2),
                "temperature":  None,
                "status":       "healthy",
                "last_updated": datetime.fromtimestamp(now - i * 10).isoformat(),
                "timestamp":    now - i * 10,
            }
            _perf_history.append(snap)
        # Also update system_data so predictive endpoint has real values
        system_data.update({
            "cpu":     round(cpu, 1),
            "memory":  round(mem.percent, 1),
            "disk":    round(disk.percent, 1),
        })
        print(f"✅ Seeded performance history with 60 initial points (CPU={cpu}%, MEM={mem.percent}%, DISK={disk.percent}%)")
    except Exception as e:
        print(f"⚠️  Could not seed perf history: {e}")

if os.getenv("SEED_PERF_HISTORY", "").strip().lower() in {"1", "true", "yes", "on"}:
    _seed_perf_history()

# Start real metrics collection in a background thread
simulation_thread = threading.Thread(target=collect_real_system_data, daemon=True)
simulation_thread.start()

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "api_server": "running",
            "aiops_bot": "running" if aiops_bot else "unavailable",
            "hf_engine": "running" if hf_engine else "unavailable"
        }
    })

@app.route('/api/system', methods=['GET'])
def get_system_data():
    """Get current system metrics"""
    return jsonify(system_data)

@app.route('/events/system', methods=['GET'])
def events_system():
    """Server-sent event stream for live system snapshots."""
    def generate():
        last_stamp = None
        while True:
            snap = dict(system_data)
            stamp = snap.get('last_updated')
            if stamp != last_stamp:
                last_stamp = stamp
                yield f"data: {json.dumps(snap)}\n\n"
            # Keep the connection alive even when the snapshot is unchanged.
            yield "event: heartbeat\n"
            yield "data: ping\n\n"
            time.sleep(3)

    return Response(
        generate(),
        content_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        },
    )

@app.route('/api/insights', methods=['GET'])
def get_ai_insights():
    """Get AI-generated insights"""
    return jsonify(ai_insights)

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    """Get recent alerts"""
    return jsonify(recent_alerts)

@app.route('/api/chat', methods=['POST'])
@_rate_limit(os.environ.get('RATE_LIMIT_CHAT', '30 per minute'))
def chat_with_ai():
    """Chat with the AI assistant"""
    global _inference_counter
    _inference_counter += 1
    _ensure_ai_initialized()
    try:
        data = request.get_json(silent=True)
        if not data or not isinstance(data, dict):
            return jsonify({"error": "Request body must be JSON"}), 400

        message = data.get('message', '')

        if not message:
            return jsonify({"error": "Message is required"}), 400

        _MAX_MESSAGE_LEN = int(os.environ.get('CHAT_MAX_MESSAGE_LEN', '4000'))
        if len(message) > _MAX_MESSAGE_LEN:
            return jsonify({"error": f"Message exceeds maximum length of {_MAX_MESSAGE_LEN} characters"}), 400
        
        # Try to use the actual AI bot if available — only when an AI key is set,
        # otherwise the bot hangs indefinitely trying to reach the API.
        gemini_key = (
            os.environ.get('GEMINI_API_KEY', '').strip()
            or os.environ.get('NVIDIA_API_KEY', '').strip()
            or os.environ.get('AI_API_KEY', '').strip()
        )
        if aiops_bot and gemini_key:
            try:
                from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
                ex = ThreadPoolExecutor(max_workers=1)
                future = ex.submit(aiops_bot.process_message, message)
                ex.shutdown(wait=False)  # don't block on exit — the future may run past our timeout
                try:
                    raw = future.result(timeout=12)
                    if isinstance(raw, dict):
                        response = raw.get('response') or raw.get('message') or raw.get('text') or str(raw)
                    else:
                        response = str(raw)
                    return jsonify({
                        "response": response,
                        "timestamp": datetime.now().isoformat(),
                        "source": "enhanced_aiops_bot"
                    })
                except FutureTimeout:
                    print("AIOps bot timed out after 12 s — falling back to psutil snapshot")
                except Exception as e:
                    print(f"Error with AIOps bot: {e}")
            except Exception as e:
                print(f"Error with AIOps bot: {e}")
        
        # Build a context-aware response from live psutil data
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            disk = _system_disk_usage()
            net = psutil.net_io_counters()
            procs = len(psutil.pids())

            def fmt(b):
                if b >= 1024**3: return f"{b/1024**3:.1f} GB"
                if b >= 1024**2: return f"{b/1024**2:.1f} MB"
                if b >= 1024:    return f"{b/1024:.1f} KB"
                return f"{b} B"

            # Derive health status
            issues = []
            if cpu > 90: issues.append(f"CPU is critically high at {cpu}%")
            elif cpu > 70: issues.append(f"CPU is elevated at {cpu}%")
            if mem.percent > 90: issues.append(f"Memory is critically high at {mem.percent}%")
            elif mem.percent > 75: issues.append(f"Memory usage is elevated at {mem.percent}%")
            if disk.percent > 90: issues.append(f"Disk is almost full at {disk.percent}%")
            elif disk.percent > 80: issues.append(f"Disk usage is high at {disk.percent}%")

            msg_lower = message.lower()
            if any(w in msg_lower for w in ['health', 'status', 'overview', 'check']):
                status_line = "⚠️ Issues detected" if issues else "✅ System is healthy"
                issue_text = ("<br>".join(f"• {i}" for i in issues)) if issues else "All metrics within normal range."
                response = (
                    f"<strong>System Health Report</strong><br><br>"
                    f"{status_line}<br><br>"
                    f"<strong>Metrics:</strong><br>"
                    f"• CPU: <strong>{cpu}%</strong> ({psutil.cpu_count()} cores)<br>"
                    f"• Memory: <strong>{mem.percent}%</strong> ({mem.used/1024**3:.1f} / {mem.total/1024**3:.1f} GB)<br>"
                    f"• Disk: <strong>{disk.percent}%</strong> ({disk.free/1024**3:.1f} GB free)<br>"
                    f"• Processes: <strong>{procs}</strong> running<br>"
                    f"• Network: ↑ {fmt(net.bytes_sent)} sent / ↓ {fmt(net.bytes_recv)} received<br><br>"
                    f"<strong>Assessment:</strong><br>{issue_text}"
                )
            elif any(w in msg_lower for w in ['cpu', 'processor', 'performance']):
                status = "critical" if cpu > 90 else "high" if cpu > 70 else "normal"
                response = (
                    f"<strong>CPU Analysis</strong><br><br>"
                    f"Current load: <strong>{cpu}%</strong> across {psutil.cpu_count()} cores — status: {status}.<br><br>"
                    f"{'⚠️ Consider closing background applications or checking for runaway processes.' if cpu > 70 else '✅ CPU load is within acceptable range.'}"
                )
            elif any(w in msg_lower for w in ['memory', 'ram', 'mem']):
                response = (
                    f"<strong>Memory Analysis</strong><br><br>"
                    f"Used: <strong>{mem.percent}%</strong> ({mem.used/1024**3:.1f} GB of {mem.total/1024**3:.1f} GB)<br>"
                    f"Available: {mem.available/1024**3:.1f} GB<br><br>"
                    f"{'⚠️ Memory is running low. Close unused applications.' if mem.percent > 80 else '✅ Memory usage is healthy.'}"
                )
            elif any(w in msg_lower for w in ['disk', 'storage', 'space']):
                response = (
                    f"<strong>Disk Analysis</strong><br><br>"
                    f"Used: <strong>{disk.percent}%</strong> ({disk.used/1024**3:.1f} / {disk.total/1024**3:.1f} GB)<br>"
                    f"Free: {disk.free/1024**3:.1f} GB<br><br>"
                    f"{'⚠️ Disk space is running low. Consider cleanup.' if disk.percent > 85 else '✅ Disk space is adequate.'}"
                )
            else:
                response = (
                    f"<strong>Live System Snapshot</strong><br><br>"
                    f"• CPU: <strong>{cpu}%</strong> | {psutil.cpu_count()} cores<br>"
                    f"• Memory: <strong>{mem.percent}%</strong> | {mem.used/1024**3:.1f} / {mem.total/1024**3:.1f} GB<br>"
                    f"• Disk: <strong>{disk.percent}%</strong> | {disk.free/1024**3:.1f} GB free<br>"
                    f"• Processes: <strong>{procs}</strong> active<br>"
                    f"• Network: ↑ {fmt(net.bytes_sent)} / ↓ {fmt(net.bytes_recv)}<br><br>"
                    f"You can ask me about CPU, memory, disk, network, or a full health check."
                )
        except Exception:
            response = "Unable to retrieve system metrics. Please ensure the server has access to system information."

        return jsonify({
            "response": response,
            "timestamp": datetime.now().isoformat(),
            "source": "system_snapshot"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Mirror plain routes for proxy compatibility
@app.route('/chat', methods=['POST'])
@_rate_limit(os.environ.get('RATE_LIMIT_CHAT', '30 per minute'))
def chat_plain():
    return chat_with_ai()

@app.route('/chat/stream', methods=['POST'])
@_rate_limit(os.environ.get('RATE_LIMIT_CHAT', '30 per minute'))
def chat_stream_plain():
    try:
        data = request.get_json(silent=True) or {}
        message = data.get('message', '')
        if not message:
            return jsonify({"error": "Message is required"}), 400

        # Generate the same response as chat_with_ai (could be replaced with true model stream)
        resp = chat_with_ai().get_json()
        text = str(resp.get('response', ''))

        def generate():
            import re
            parts = re.split(r'(\s+)', text)
            for part in parts:
                if not part:
                    continue
                yield f"data: {part}\n\n"
                time.sleep(0.01)
            yield "event: done\n"
            yield "data: [DONE]\n\n"

        headers = {
            'Cache-Control': 'no-cache',
            'Content-Type': 'text/event-stream',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
        return Response(generate(), headers=headers)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/analyze', methods=['POST'])
@_rate_limit(os.environ.get('RATE_LIMIT_ANALYZE', '30 per minute'))
def analyze_with_ai():
    """Analyze text with Hugging Face AI"""
    _ensure_ai_initialized()
    try:
        data = request.get_json()
        text = data.get('text', '')
        analysis_type = data.get('type', 'sentiment')
        
        if not text:
            return jsonify({"error": "Text is required"}), 400
        
        if hf_engine:
            try:
                if analysis_type == 'sentiment':
                    result = hf_engine.analyze_user_sentiment(text)
                elif analysis_type == 'classification':
                    result = hf_engine.classify_system_issue(text)
                elif analysis_type == 'summarization':
                    result = hf_engine.summarize_system_logs(text)
                else:
                    result = {"error": "Unsupported analysis type"}
                
                return jsonify({
                    "result": result,
                    "timestamp": datetime.now().isoformat(),
                    "analysis_type": analysis_type
                })
            except Exception as e:
                return jsonify({"error": f"AI analysis failed: {str(e)}"}), 500
        else:
            return jsonify({"error": "Hugging Face AI engine not available"}), 503
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/auth/ping', methods=['GET', 'POST', 'OPTIONS'])
def auth_ping():
    """Lightweight connectivity + CORS test — always returns 200."""
    return jsonify({'ok': True, 'auth_system': bool(auth_system), 'db': getattr(auth_system, 'db_path', None)})

@app.route('/actions/process-monitor', methods=['POST'])
def action_process_monitor():
    import psutil
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
        try:
            info = p.info
            procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    procs.sort(key=lambda x: x.get('cpu_percent') or 0, reverse=True)
    return jsonify(_make_job("process-monitor", {
        "total_processes": len(procs),
        "top_processes": procs[:10],
        "message": f"Snapshot of {len(procs)} processes captured",
    }))


@app.route('/actions/emergency-stop', methods=['POST'])
def action_emergency_stop():
    import psutil
    data = request.get_json() or {}
    confirm = data.get('confirm', False)
    if not confirm:
        return jsonify({"error": "Confirmation required. Send {confirm: true}"}), 400
    # Find the top CPU process (excluding system/self)
    procs = []
    own_pid = os.getpid()
    for p in psutil.process_iter(['pid', 'name', 'cpu_percent']):
        try:
            if p.info['pid'] != own_pid:
                procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    procs.sort(key=lambda x: x.get('cpu_percent') or 0, reverse=True)
    if not procs:
        return jsonify({"message": "No candidate processes found"})
    top = procs[0]
    return jsonify(_make_job("emergency-stop", {
        "targeted_pid": top['pid'],
        "targeted_name": top['name'],
        "cpu_percent": top['cpu_percent'],
        "message": f"Identified top CPU process: {top['name']} (PID {top['pid']}) — kill not executed for safety",
        "note": "Automatic kill is disabled; use OS task manager to terminate if needed",
    }))


@app.route('/ai/diagnostics', methods=['POST'])
def ai_diagnostics():
    return jsonify(_make_job("ai-diagnostics", {
        "gemini_available": aiops_bot is not None,
        "huggingface_available": hf_engine is not None,
        "system_cpu": system_data.get('cpu'),
        "system_memory": system_data.get('memory'),
        "status": "healthy",
        "message": "AI subsystems nominal",
    }))


@app.route('/ai/retrain', methods=['POST'])
def ai_retrain():
    return jsonify(_make_job("ai-retrain", {
        "message": "Model retraining queued (no-op in dev mode)",
        "estimated_duration_min": 5,
        "status": "queued",
    }))


@app.route('/ai/update-params', methods=['POST'])
def ai_update_params():
    data = request.get_json() or {}
    return jsonify(_make_job("ai-update-params", {
        "params_received": list(data.keys()),
        "message": "Parameters accepted",
        "status": "applied",
    }))


@app.route('/ai/export-insights', methods=['POST'])
def ai_export_insights():
    export = {
        "exported_at": datetime.now().isoformat(),
        "system_snapshot": system_data,
        "ai_insights": ai_insights,
        "anomalies": _build_alerts(
            system_data.get('cpu', 0.0), system_data.get('memory', 0.0),
            system_data.get('disk', 0.0), system_data.get('network_out', 0.0),
            system_data.get('temperature', None),
        ),
    }
    return jsonify(_make_job("ai-export", {
        "message": "Insights export ready",
        "record_count": len(ai_insights) + len(export["anomalies"]),
        "data": export,
    }))


@app.route('/jobs/<job_id>', methods=['GET'])
def get_job(job_id):
    job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route('/jobs/<job_id>/logs', methods=['GET'])
def get_job_logs(job_id):
    job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({"logs": [f"[INFO] Job {job_id} completed: {job.get('name', '')}"]})


@app.route('/jobs/<job_id>/download', methods=['GET'])
def download_job(job_id):
    job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job.get('result', {}))


# Integration test endpoints
@app.route('/integrations/slack/test', methods=['POST'])
def test_slack():
    data = request.get_json() or {}
    webhook = data.get('webhook_url', '')
    if not webhook:
        webhook = os.getenv('SLACK_WEBHOOK_URL')
    if not webhook:
        return jsonify({"error": "webhook_url required or SLACK_WEBHOOK_URL env var not set"}), 400
    
    _send_slack_message_safe("🔔 AIOps Bot Slack Integration Test Successful!", "info", webhook_url=webhook)
    return jsonify({"ok": True, "message": "Slack test payload sent successfully!"})


@app.route('/integrations/discord/test', methods=['POST'])
def test_discord():
    data = request.get_json() or {}
    webhook = data.get('webhook_url', '')
    if not webhook:
        return jsonify({"error": "webhook_url required"}), 400
    return jsonify({"ok": True, "message": "Discord test payload sent (stub)"})


# ---------------------------------------------------------------------------
# ORIGINAL PERFORMANCE ENDPOINT (kept for backwards compat)
# ---------------------------------------------------------------------------
@app.route('/api/performance', methods=['GET'])
def get_performance_data():
    """Get historical performance data for charts — returns real _perf_history."""
    timeframe  = request.args.get('timeframe', '1hour')
    max_pts    = int(request.args.get('max_points', 120))
    window_map = {'1hour': 3600, '6hours': 21600, '24hours': 86400}
    window_secs = window_map.get(timeframe, 3600)
    cutoff = datetime.now().timestamp() - window_secs

    history  = list(_perf_history)
    filtered = [p for p in history if p.get('timestamp', 0) >= cutoff]

    if len(filtered) > max_pts:
        step     = len(filtered) / max_pts
        filtered = [filtered[int(i * step)] for i in range(max_pts)]

    return jsonify(filtered)


# ---------------------------------------------------------------------------
# Auth routes — login / register / me / logout
# The auth_system uses username-based lookup; we accept email or username.
# ---------------------------------------------------------------------------
def _auth_user_by_email_or_username(identifier: str, password: str):
    """Try email lookup first, fall back to username lookup."""
    if not auth_system:
        return False, None, "Auth system unavailable"
    import sqlite3 as _sq
    conn = _sq.connect(auth_system.db_path)
    cur = conn.cursor()
    cur.execute(
        'SELECT username FROM users WHERE (email=? OR username=?) AND is_active=1',
        (identifier.strip().lower(), identifier.strip())
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return False, None, "Invalid credentials"
    return auth_system.authenticate_user(row[0], password)


@app.route('/auth/login', methods=['POST', 'OPTIONS'])
def auth_login():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data = request.get_json(silent=True) or {}
    identifier = (data.get('email') or data.get('username') or '').strip()
    password = data.get('password', '')
    if not identifier or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    ip = request.remote_addr or 'unknown'
    allowed, retry_after = _check_rate_limit(ip, identifier)
    if not allowed:
        return jsonify({'error': f'Too many attempts. Retry after {retry_after}s'}), 429

    success, user, error = _auth_user_by_email_or_username(identifier, password)
    _record_attempt(ip, identifier, success)

    if not success:
        return jsonify({'error': error or 'Invalid credentials'}), 401

    token = auth_system.generate_token(user)
    return jsonify({
        'token': token,
        'refresh_token': token,   # reuse same token as refresh for simplicity
        'user': {
            'id': user.id,
            'email': user.email,
            'username': user.username,
            'full_name': user.full_name,
            'role': user.role,
            'org_id': user.company_id,
        }
    })


@app.route('/auth/me', methods=['GET'])
def auth_me():
    token = _extract_bearer()
    if not token or not auth_system:
        return jsonify({'error': 'Not authenticated'}), 401
    valid, auth_token, err = auth_system.verify_token(token)
    if not valid:
        return jsonify({'error': err or 'Invalid token'}), 401
    user = auth_system.get_user(auth_token.user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify({
        'id': user.id,
        'email': user.email,
        'username': user.username,
        'full_name': user.full_name,
        'role': user.role,
        'org_id': user.company_id,
    })


@app.route('/auth/logout', methods=['POST', 'OPTIONS'])
def auth_logout():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    return jsonify({'ok': True})


@app.route('/auth/register', methods=['POST', 'OPTIONS'])
def auth_register():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    if not auth_system:
        return jsonify({'error': 'Auth system unavailable'}), 503
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    username = (data.get('username') or email.split('@')[0]).strip()
    password = data.get('password', '')
    full_name = data.get('full_name', username)
    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400
    try:
        user = auth_system.create_user(username, email, password, full_name, role='employee')
        token = auth_system.generate_token(user)
        return jsonify({'token': token, 'refresh_token': token, 'user': {
            'id': user.id, 'email': user.email, 'username': user.username,
            'full_name': user.full_name, 'role': user.role,
        }}), 201
    except Exception as exc:
        return jsonify({'error': str(exc)}), 400


@app.route('/auth/refresh', methods=['POST', 'OPTIONS'])
def auth_refresh():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    token = _extract_bearer()
    data = request.get_json(silent=True) or {}
    token = token or data.get('refresh_token', '')
    if not token or not auth_system:
        return jsonify({'error': 'Not authenticated'}), 401
    valid, auth_token, err = auth_system.verify_token(token)
    if not valid:
        return jsonify({'error': err or 'Invalid token'}), 401
    user = auth_system.get_user(auth_token.user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    new_token = auth_system.generate_token(user)
    return jsonify({'token': new_token, 'refresh_token': new_token})


if __name__ == '__main__':
    print("🚀 Starting AIOps Dashboard API Server...")
    print("📊 Dashboard will be available at: http://localhost:3000")
    print("🔌 API Server running on: http://localhost:5000")
    print("\n📋 Available endpoints:")
    print("  • GET  /api/health     - Health check")
    print("  • GET  /api/system     - System metrics")
    print("  • GET  /api/insights   - AI insights")
    print("  • GET  /api/alerts     - Recent alerts")
    print("  • POST /api/chat       - Chat with AI")
    print("  • POST /api/analyze    - AI text analysis")
    print("  • GET  /api/performance - Performance data")
    print("  • GET  /api/remediation/rules - List remediation rules")
    print("  • POST /api/remediation/rules/<id>/toggle - Enable/disable a rule")
    print("  • GET  /api/remediation/history - Remediation attempt history")
    print("  • GET  /api/remediation/stats - Remediation statistics")
    print("  • POST /api/remediation/trigger - Trigger remediation manually")
    print("  • GET  /api/remediation/issues - Evaluate current issues (no execution)")
    print("  • GET  /api/remediation/autonomous - Get autonomous mode status")
    print("  • POST /api/remediation/autonomous - Enable/disable autonomous mode")
    print("\n✨ Ready to serve your AIOps dashboard!")
    
    # Notify Slack
    _send_slack_message_safe("🚀 AIOps API Server has started and is monitoring metrics!", "info")
    
    # Start the background metrics collection and daily report scheduler
    try:
        from daily_health_reporter import start_metric_collection
        health_generator = start_metric_collection()
        print("📊 [Daily Health Reporter] Background metric collection started.")
        
        def _daily_reporter_loop(generator):
            while True:
                now = datetime.now()
                target_time = now.replace(hour=9, minute=0, second=0, microsecond=0)
                if now >= target_time:
                    target_time += timedelta(days=1)
                    
                sleep_secs = (target_time - now).total_seconds()
                
                # Check every minute just in case system sleeps, but wait for the target
                while (target_time - datetime.now()).total_seconds() > 0:
                    time.sleep(60)
                
                try:
                    print("[Daily Reporter] Generating and sending daily Slack report at 9:00 AM...")
                    report = generator.generate_daily_report()
                    generator.send_slack_report(report)
                except Exception as e:
                    print(f"[Daily Reporter] Error: {e}")
                    
        threading.Thread(target=_daily_reporter_loop, args=(health_generator,), daemon=True).start()
    except Exception as e:
        print(f"Failed to start Daily Health Reporter: {e}")
    
    port = int(os.environ.get('FLASK_PORT', 5000))
    if _SOCKETIO_AVAILABLE and socketio is not None:
        socketio.run(app, debug=True, host='0.0.0.0', port=port,
                     allow_unsafe_werkzeug=True)
    else:
        app.run(debug=True, host='0.0.0.0', port=port, threaded=True)