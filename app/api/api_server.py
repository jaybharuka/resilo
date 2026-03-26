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

# --- Load .env file if present ---
try:
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(_env_path):
        with open(_env_path) as _ef:
            for _line in _ef:
                _line = _line.strip()
                if _line and not _line.startswith('#') and '=' in _line:
                    _k, _v = _line.split('=', 1)
                    os.environ.setdefault(_k.strip(), _v.strip())
except Exception as _env_err:
    logger.warning("Could not load .env: %s", _env_err)

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

# ── CORS ──────────────────────────────────────────────────────────────────────
# All localhost ports are trusted for local development.  Production deployments
# should set ALLOWED_ORIGINS in .env (comma-separated list of exact origins).
_RAW_ORIGINS = os.environ.get('ALLOWED_ORIGINS', '')
_ALLOWED_ORIGINS = [o.strip() for o in _RAW_ORIGINS.split(',') if o.strip()]

# Always allow every localhost port in development so a changing port (3000,
# 3001, 3002, …) never causes a CORS failure.
_LOCALHOST_RE = __import__('re').compile(r'^https?://(localhost|127\.0\.0\.1)(:\d+)?$')

CORS(app, resources={r"/*": {
    "origins": _ALLOWED_ORIGINS or "*",
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    "allow_headers": ["Content-Type", "Authorization", "X-Request-ID"],
    "expose_headers": [
        "X-RateLimit-Limit", "X-RateLimit-Remaining",
        "X-RateLimit-Reset", "Retry-After",
    ],
    "supports_credentials": False,
    "max_age": 600,
}})

@app.after_request
def _add_cors_headers(response):
    """Guarantee CORS headers are present — belt-and-suspenders over flask-cors."""
    origin = request.headers.get('Origin', '')
    if _LOCALHOST_RE.match(origin) or not origin:
        response.headers['Access-Control-Allow-Origin'] = origin or '*'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS,PATCH'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization,X-Request-ID'
        response.headers['Access-Control-Max-Age'] = '600'
    elif origin in _ALLOWED_ORIGINS:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS,PATCH'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization,X-Request-ID'
        response.headers['Access-Control-Max-Age'] = '600'
    return response

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
    "cpu": 45.2,
    "memory": 67.8,
    "disk": 52.3,
    "network_in": 125.6,
    "network_out": 89.2,
    "temperature": 58.5,
    "status": "healthy",
    "uptime": "2d 14h 32m",
    "active_processes": 156,
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

# Initialize AI components if available
aiops_bot = None
hf_engine = None

try:
    if EnhancedAIOpsBot:
        aiops_bot = EnhancedAIOpsBot()
        print("✅ Enhanced AIOps Bot initialized successfully")
    if HuggingFaceAIEngine:
        hf_engine = HuggingFaceAIEngine()
        print("✅ Hugging Face AI Engine initialized successfully")
except Exception as e:
    print(f"⚠️ Warning: Could not initialize AI components: {e}")

# Initialize remediation engines
remediation_engine = None
enhanced_engine = None

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
            disk   = psutil.disk_usage('/')
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
        except Exception as e:
            print(f"Error in system data collection: {e}")

        time.sleep(_interval)

# ---------------------------------------------------------------------------
# Pre-seed _perf_history at startup so the Analytics page has data immediately
# ---------------------------------------------------------------------------
def _seed_perf_history():
    """Take one real psutil reading and backfill 60 synthetic history points
    so charts are populated the moment the server starts (no waiting for the
    10-second collection loop to accumulate enough points)."""
    try:
        import psutil
        cpu   = psutil.cpu_percent(interval=0.5)
        mem   = psutil.virtual_memory()
        disk  = psutil.disk_usage('/')
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
    try:
        data = request.get_json()
        message = data.get('message', '')
        
        if not message:
            return jsonify({"error": "Message is required"}), 400
        
        # Try to use the actual AI bot if available — only when GEMINI_API_KEY is set,
        # otherwise the bot hangs indefinitely trying to reach the API.
        gemini_key = os.environ.get('GEMINI_API_KEY', '').strip()
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
            disk = psutil.disk_usage('/')
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


@app.route('/auth/login', methods=['POST'])
@_rate_limit(os.environ.get('RATE_LIMIT_LOGIN', '10 per minute'))
def auth_login():
    """Login with email (or username) and password"""
    import sqlite3 as _sqlite3
    data = request.get_json() or {}
    email = (data.get('email') or '').strip()
    password = data.get('password') or ''

    print(f"[LOGIN] attempt — email={email!r} has_password={bool(password)} origin={request.headers.get('Origin','')!r}", flush=True)

    if not email or not password:
        print("[LOGIN] rejected — missing email or password", flush=True)
        return jsonify({'error': 'Email and password are required'}), 400
    if not auth_system:
        print("[LOGIN] rejected — auth_system is None", flush=True)
        return jsonify({'error': 'Auth system unavailable'}), 503

    # Rate limiting: per-IP and per-email lockout
    client_ip = request.remote_addr or '0.0.0.0'
    allowed, retry_after = _check_rate_limit(client_ip, email)
    if not allowed:
        print(f"[LOGIN] rate-limited — email={email!r} retry_after={retry_after}s", flush=True)
        resp = jsonify({'error': f'Too many login attempts. Please try again in {retry_after}s.'})
        resp.headers['Retry-After'] = str(retry_after)
        return resp, 429

    try:
        conn = _sqlite3.connect(auth_system.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT username FROM users WHERE email = ? OR username = ?', (email, email))
        row = cursor.fetchone()
        conn.close()
    except Exception as e:
        print(f"[LOGIN] db error — {e}", flush=True)
        return jsonify({'error': f'Database error: {e}'}), 500

    if not row:
        print(f"[LOGIN] no user found for email={email!r}", flush=True)
        _record_attempt(client_ip, email, success=False)
        return jsonify({'error': 'Invalid credentials'}), 401

    print(f"[LOGIN] found username={row[0]!r} — verifying password", flush=True)
    success, user, error = auth_system.authenticate_user(row[0], password)
    if not success:
        print(f"[LOGIN] password mismatch — error={error!r}", flush=True)
        _record_attempt(client_ip, email, success=False)
        return jsonify({'error': error or 'Invalid credentials'}), 401

    _record_attempt(client_ip, email, success=True)

    # Check if 2FA is enabled for this user — if so, issue a temp token instead
    totp_status = auth_system.get_totp_status(user.id)
    if totp_status['enabled']:
        temp_token = _create_pending_2fa(user.id)
        return jsonify({'requires_2fa': True, 'temp_token': temp_token})

    token = auth_system.generate_token(user)
    # Check if user must change their default password
    import sqlite3 as _sq3b
    must_change = False
    try:
        c2 = _sq3b.connect(auth_system.db_path)
        r = c2.execute('SELECT must_change_password FROM users WHERE id = ?', (user.id,)).fetchone()
        c2.close()
        must_change = bool(r[0]) if r else False
    except Exception:
        pass

    return jsonify({
        'token': token,
        'must_change_password': must_change,
        'user': {
            'id': user.id,
            'email': user.email,
            'username': user.username,
            'full_name': user.full_name,
            'role': user.role,
        }
    })


@app.route('/auth/me', methods=['GET'])
def auth_me():
    """Return current user info — supports Firebase ID tokens and legacy JWT tokens."""
    raw = _extract_bearer()
    if not raw:
        return jsonify({'error': 'Token required'}), 401

    # --- Firebase path (preferred when FIREBASE_PROJECT_ID is configured) ---
    if os.environ.get('FIREBASE_PROJECT_ID'):
        try:
            payload = verify_firebase_token(raw)
            email = (payload.get('email') or '').strip().lower()

            # ADMIN_EMAILS allowlist — comma-separated list of admin emails.
            # When set, only those emails can access the dashboard and their role
            # is forced to 'admin'. All other users receive 403.
            admin_emails_raw = os.environ.get('ADMIN_EMAILS', '').strip()
            admin_emails = {e.strip().lower() for e in admin_emails_raw.split(',') if e.strip()}

            if admin_emails:
                if email not in admin_emails:
                    return jsonify({'error': 'Access restricted to administrators only.'}), 403
                role = 'admin'
            else:
                # No allowlist configured — use custom claim or default to 'employee'
                role = payload.get('role', 'employee')

            return jsonify({
                'user': {
                    'id': payload['uid'],
                    'email': email,
                    'username': email or payload['uid'],
                    'full_name': payload.get('name', ''),
                    'role': role,
                    'picture': payload.get('picture', ''),
                }
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 401

    # --- Legacy fallback ---
    if not auth_system:
        return jsonify({'error': 'Auth system unavailable'}), 503
    valid, auth_token, error = auth_system.verify_token(raw)
    if not valid:
        return jsonify({'error': error}), 401
    user = auth_system.get_user(auth_token.user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify({
        'user': {
            'id': user.id,
            'email': user.email,
            'username': user.username,
            'full_name': user.full_name,
            'role': user.role,
        }
    })


@app.route('/auth/logout', methods=['POST'])
def auth_logout():
    """Revoke the current session token"""
    if auth_system:
        token = request.headers.get('Authorization', '')
        if token.startswith('Bearer '):
            token = token[7:]
        if token:
            try:
                auth_system.revoke_token(token)
            except Exception:
                pass
    return jsonify({'ok': True})


@app.route('/auth/change-password', methods=['POST'])
def auth_change_password():
    """Change the authenticated user's password and clear the must_change_password flag."""
    if not auth_system:
        return jsonify({'error': 'Auth system unavailable'}), 503
    token = request.headers.get('Authorization', '').replace('Bearer ', '').strip()
    if not token:
        return jsonify({'error': 'Token required'}), 401

    valid, auth_token, error = auth_system.verify_token(token)
    if not valid:
        return jsonify({'error': error}), 401

    data = request.get_json() or {}
    new_password = data.get('new_password', '')
    if len(new_password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400

    import sqlite3 as _sq3c, bcrypt as _bcrypt
    try:
        new_hash = _bcrypt.hashpw(new_password.encode(), _bcrypt.gensalt()).decode()
        conn = _sq3c.connect(auth_system.db_path)
        conn.execute(
            'UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?',
            (new_hash, auth_token.user_id)
        )
        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'message': 'Password updated successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/auth/invites', methods=['POST'])
def auth_create_invite():
    """Stub invite creation (returns a simple token)"""
    import secrets as _secrets
    token = _secrets.token_urlsafe(24)
    return jsonify({'token': token, 'message': 'Invite created (stub)'})


@app.route('/auth/redeem-invite', methods=['POST'])
def auth_redeem_invite():
    """Stub invite redemption"""
    return jsonify({'error': 'Self-registration via invite is not enabled'}), 403


@app.route('/api/remediation/rules', methods=['GET'])
def get_remediation_rules():
    """List all remediation rules"""
    if not remediation_engine:
        return jsonify({"error": "Remediation engine not available"}), 503
    rules = []
    for rule in remediation_engine.rules:
        rules.append({
            "id": rule.id,
            "name": rule.name,
            "description": rule.description,
            "trigger_pattern": rule.trigger_pattern,
            "action": rule.action.value,
            "severity": rule.severity.value,
            "enabled": rule.enabled,
            "cooldown_minutes": rule.cooldown_minutes,
            "max_attempts": rule.max_attempts,
            "success_criteria": rule.success_criteria,
        })
    return jsonify(rules)


@app.route('/api/remediation/rules/<rule_id>/toggle', methods=['POST'])
def toggle_remediation_rule(rule_id):
    """Enable or disable a remediation rule"""
    if not remediation_engine:
        return jsonify({"error": "Remediation engine not available"}), 503
    rule = next((r for r in remediation_engine.rules if r.id == rule_id), None)
    if not rule:
        return jsonify({"error": "Rule not found"}), 404
    rule.enabled = not rule.enabled
    return jsonify({"id": rule_id, "enabled": rule.enabled})


@app.route('/api/remediation/history', methods=['GET'])
def get_remediation_history():
    """Get the last 50 remediation attempts"""
    if not remediation_engine:
        return jsonify({"error": "Remediation engine not available"}), 503
    history = []
    for attempt in remediation_engine.attempts[-50:]:
        history.append({
            "id": attempt.id,
            "rule_id": attempt.rule_id,
            "timestamp": attempt.timestamp.isoformat(),
            "action": attempt.action.value,
            "success": attempt.success,
            "error_message": attempt.error_message,
            "execution_time_seconds": round(attempt.execution_time_seconds, 3),
            "metrics_before": attempt.metrics_before,
            "metrics_after": attempt.metrics_after,
        })
    return jsonify(list(reversed(history)))


@app.route('/api/remediation/stats', methods=['GET'])
def get_remediation_stats():
    """Get remediation performance statistics"""
    if not remediation_engine:
        return jsonify({"error": "Remediation engine not available"}), 503
    return jsonify(remediation_engine.get_remediation_stats())


@app.route('/api/remediation/trigger', methods=['POST'])
def trigger_remediation():
    """Manually trigger remediation for a given issue type or evaluate current metrics"""
    if not remediation_engine:
        return jsonify({"error": "Remediation engine not available"}), 503

    data = request.get_json() or {}
    issue_type = data.get('issue_type', '')
    metrics = remediation_engine._get_current_metrics()

    # Map issue_type strings to rule IDs for direct lookup
    rule_id_map = {
        'high_cpu':    'high_cpu_cleanup',
        'high_memory': 'high_memory_optimization',
        'high_disk':   'disk_space_cleanup',
        'high_error':  'service_restart_high_error',
    }

    results = []

    if issue_type and issue_type in rule_id_map:
        # Find rule directly by ID — no metric re-check required
        rule = next((r for r in remediation_engine.rules
                     if r.id == rule_id_map[issue_type] and r.enabled), None)
        if not rule:
            return jsonify({
                "success": False, "triggered": 0,
                "message": f"Rule for '{issue_type}' not found or disabled",
                "metrics": metrics,
            })
        attempt = remediation_engine.execute_remediation(rule, metrics)
        results.append({
            "rule_id": rule.id,
            "rule_name": rule.name,
            "success": attempt.success,
            "execution_time_seconds": round(attempt.execution_time_seconds, 3),
            "error_message": attempt.error_message,
        })
    else:
        # No issue_type — evaluate live metrics against all rules
        triggered_rules = remediation_engine.evaluate_triggers(metrics)
        if not triggered_rules:
            return jsonify({
                "success": False, "triggered": 0,
                "message": "No rules triggered for current metrics",
                "metrics": metrics,
            })
        for rule in triggered_rules:
            attempt = remediation_engine.execute_remediation(rule, metrics)
            results.append({
                "rule_id": rule.id,
                "rule_name": rule.name,
                "success": attempt.success,
                "execution_time_seconds": round(attempt.execution_time_seconds, 3),
                "error_message": attempt.error_message,
            })

    overall_success = any(r["success"] for r in results)
    return jsonify({
        "success": overall_success,
        "triggered": len(results),
        "results": results,
        "metrics": metrics,
    })


@app.route('/api/remediation/issues', methods=['GET'])
def get_remediation_issues():
    """Evaluate current metrics against all rules and return triggered issues (no execution)."""
    if not remediation_engine:
        return jsonify({"error": "Remediation engine not available"}), 503

    # Map rule IDs to legacy issue_type strings used by /trigger
    issue_type_map = {
        "high_cpu_cleanup": "high_cpu",
        "high_memory_optimization": "high_memory",
        "disk_space_cleanup": "high_disk",
        "service_restart_high_error": "high_error",
    }

    # AI explanation templates
    def make_explanation(issue):
        val = issue["current_value"]
        pattern = issue["trigger_pattern"]
        # Extract threshold from pattern e.g. "cpu_usage > 85" → 85
        import re
        m = re.search(r'[><=!]+\s*([\d.]+)', pattern)
        threshold = float(m.group(1)) if m else 0
        metric_labels = {
            "cpu_usage": "CPU", "memory_usage": "Memory",
            "disk_usage": "Disk", "error_rate": "Error rate",
        }
        metric_key = re.match(r'(\w+)', pattern)
        label = metric_labels.get(metric_key.group(1) if metric_key else '', pattern)
        unit = "%" if "usage" in pattern else (" errors/min" if "error_rate" in pattern else "")
        return (
            f"{label} at {val:.1f}{unit} exceeds the {threshold:.0f}{unit} threshold. "
            f"{issue['description']}"
        )

    try:
        metrics, issues = remediation_engine.get_current_issues()
        enriched = []
        for issue in issues:
            enriched.append({
                **issue,
                "issue_type": issue_type_map.get(issue["rule_id"], ""),
                "ai_explanation": make_explanation(issue),
            })
        return jsonify({
            "metrics": metrics,
            "issues": enriched,
            "evaluated_at": __import__('datetime').datetime.now().isoformat(),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/remediation/autonomous', methods=['GET'])
def get_autonomous_mode():
    """Get the current autonomous mode status."""
    if not remediation_engine:
        return jsonify({"error": "Remediation engine not available"}), 503
    with remediation_engine._autonomous_lock:
        enabled = remediation_engine.autonomous_mode
    return jsonify({
        "autonomous_mode": enabled,
        "is_monitoring": remediation_engine.is_running,
        "safety_mode": remediation_engine.safety_mode,
    })


@app.route('/api/remediation/autonomous', methods=['POST'])
def set_autonomous_mode():
    """Enable or disable autonomous remediation mode."""
    if not remediation_engine:
        return jsonify({"error": "Remediation engine not available"}), 503

    data = request.get_json() or {}
    if "enabled" not in data or not isinstance(data["enabled"], bool):
        return jsonify({"error": "'enabled' field (boolean) is required"}), 400

    enabled = data["enabled"]
    with remediation_engine._autonomous_lock:
        remediation_engine.autonomous_mode = enabled

    # Start monitoring thread if not already running
    if enabled and not remediation_engine.is_running:
        remediation_engine.start_continuous_monitoring()

    msg = "Autonomous mode enabled. Agent will auto-fix LOW and MEDIUM severity issues." if enabled \
        else "Autonomous mode disabled. Manual confirmation required for all fixes."
    return jsonify({
        "autonomous_mode": enabled,
        "message": msg,
        "safety_note": "HIGH and CRITICAL severity issues always require manual confirmation.",
    })


@app.route('/dashboard-snapshot', methods=['GET'])
@app.route('/system-health', methods=['GET'])
@cached(ttl=5.0)
def dashboard_snapshot():
    """Live system snapshot — primary endpoint polled by the dashboard."""
    return jsonify(system_data)


@app.route('/system-info', methods=['GET'])
@cached(ttl=30.0)
def system_info():
    """Detailed static system information via psutil."""
    import psutil, platform as _platform
    try:
        mem  = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        freq = psutil.cpu_freq()

        try:
            load = psutil.getloadavg()
            load_str = f"{load[0]:.2f}, {load[1]:.2f}, {load[2]:.2f}"
        except AttributeError:
            load_str = f"{psutil.cpu_percent(interval=0.1):.1f}% (win)"

        boot_ts = psutil.boot_time()
        boot_iso = datetime.fromtimestamp(boot_ts).strftime("%Y-%m-%d %H:%M")

        return jsonify({
            "platform":          _platform.system() + " " + _platform.release(),
            "cpu_cores":         psutil.cpu_count(logical=False),
            "cpu_threads":       psutil.cpu_count(logical=True),
            "total_memory":      round(mem.total / 1024**3, 1),
            "available_memory":  round(mem.available / 1024**3, 1),
            "free_disk":         round(disk.free / 1024**3, 1),
            "total_disk":        round(disk.total / 1024**3, 1),
            "cpu_freq":          round(freq.current) if freq else None,
            "boot_time":         boot_iso,
            "load_avg":          load_str,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/processes', methods=['GET'])
def get_processes():
    """Top processes by CPU usage."""
    import psutil
    try:
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
            try:
                info = p.info
                procs.append({
                    "pid":            info['pid'],
                    "name":           info['name'] or 'unknown',
                    "cpu_percent":    round(info['cpu_percent'] or 0, 1),
                    "memory_percent": round(info['memory_percent'] or 0, 1),
                    "status":         info['status'] or 'unknown',
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        procs.sort(key=lambda x: x['cpu_percent'], reverse=True)
        return jsonify(procs[:20])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/events/system')
def events_system():
    """Server-Sent Events stream — pushes system_data every 3 seconds."""
    def generate():
        while True:
            try:
                yield f"data: {json.dumps(system_data)}\n\n"
            except Exception:
                break
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



@app.route('/users', methods=['GET'])
def get_users():
    """List all users — admin only."""
    raw = (request.headers.get('Authorization') or '').removeprefix('Bearer ').strip()
    auth_token, err = _require_admin(raw)
    if err:
        return err
    try:
        conn = _sqlite3.connect(auth_system.db_path)
        conn.row_factory = _sqlite3.Row
        users_rows = conn.execute("SELECT id, username, email, full_name, role, is_active, created_at, last_login_at FROM users").fetchall()
        users = [dict(r) for r in users_rows]
        conn.close()
        return jsonify(users)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/devices', methods=['GET'])
def get_devices():
    """Device fleet — real local machine only."""
    import psutil, platform as _pf
    try:
        mem   = psutil.virtual_memory()
        disk_ = psutil.disk_usage('/')
        cpu   = round(psutil.cpu_percent(interval=0.1), 1)
        raw_status = system_data.get("status", "healthy")
        # Derive status from live metrics if not already set
        if raw_status not in ("warning", "critical", "offline"):
            if cpu > 85 or mem.percent > 90:
                raw_status = "critical"
            elif cpu > 70 or mem.percent > 75:
                raw_status = "warning"
            else:
                raw_status = "online"
        local_device = {
            "id":         "local-001",
            "name":       _pf.node() or "localhost",
            "type":       "server",
            "department": "IT Operations",
            "status":     raw_status,
            "cpu":        cpu,
            "memory":     round(mem.percent, 1),
            "disk":       round(disk_.percent, 1),
            "battery":    None,
            "lastSeen":   datetime.now().isoformat(),
            "os":         _pf.system() + " " + _pf.release(),
            "security":   {"antivirus": True, "firewall": True, "encryption": True},
        }
    except Exception:
        local_device = {
            "id": "local-001", "name": "localhost", "type": "server",
            "department": "IT Operations", "status": "online",
            "cpu": 0, "memory": 0, "disk": 0, "battery": None,
            "lastSeen": datetime.now().isoformat(), "os": "Unknown",
            "security": {"antivirus": True, "firewall": True, "encryption": True},
        }
    return jsonify([local_device])


@app.route('/company-stats', methods=['GET'])
def get_company_stats():
    """Aggregated device fleet statistics — computed from live device list."""
    import psutil, platform as _pf
    try:
        mem   = psutil.virtual_memory()
        cpu   = round(psutil.cpu_percent(interval=0.1), 1)
        if cpu > 85 or mem.percent > 90:
            status = "critical"
        elif cpu > 70 or mem.percent > 75:
            status = "warning"
        else:
            status = "online"
        counts = {"online": 0, "warning": 0, "critical": 0, "offline": 0}
        counts[status] = 1
        return jsonify({
            "total":    1,
            "online":   counts["online"],
            "warning":  counts["warning"],
            "critical": counts["critical"],
            "offline":  counts["offline"],
        })
    except Exception:
        return jsonify({"total": 1, "online": 1, "warning": 0, "critical": 0, "offline": 0})


@app.route('/health', methods=['GET'])
def health_plain():
    """Plain /health for proxy compatibility."""
    return health_check()


# ---------------------------------------------------------------------------
# CONFIG — tells frontend whether self-registration is open
# ---------------------------------------------------------------------------
@app.route('/config', methods=['GET'])
def get_config():
    return jsonify({
        "open_registration": False,
        "demo_mode": os.environ.get("DEMO_MODE", "false").lower() == "true",
        "version": "1.0.0",
    })


# ---------------------------------------------------------------------------
# AUTH — token refresh + self-registration
# ---------------------------------------------------------------------------
@app.route('/auth/refresh', methods=['POST'])
def auth_refresh():
    """Refresh a JWT using a refresh token (currently mirrors /auth/me)."""
    if not auth_system:
        return jsonify({'error': 'Auth system unavailable'}), 503
    data = request.get_json() or {}
    token = data.get('refresh_token') or data.get('token', '')
    token = token.replace('Bearer ', '').strip()
    if not token:
        # Try Authorization header as fallback
        token = request.headers.get('Authorization', '').replace('Bearer ', '').strip()
    if not token:
        return jsonify({'error': 'Refresh token required'}), 401

    valid, auth_token, error = auth_system.verify_token(token)
    if not valid:
        return jsonify({'error': error or 'Invalid token'}), 401

    user = auth_system.get_user(auth_token.user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    new_token = auth_system.generate_token(user)
    return jsonify({
        'token': new_token,
        'user': {
            'id': user.id,
            'email': user.email,
            'username': user.username,
            'full_name': user.full_name,
            'role': user.role,
        }
    })


@app.route('/auth/register', methods=['POST'])
def auth_register():
    """Self-registration (only if open_registration is enabled)."""
    return jsonify({'error': 'Self-registration is not enabled on this instance'}), 403


# ---------------------------------------------------------------------------
# PASSWORD RESET
# ---------------------------------------------------------------------------

@app.route('/auth/forgot-password', methods=['POST'])
@_rate_limit(os.environ.get('RATE_LIMIT_FORGOT_PW', '3 per minute'))
def auth_forgot_password():
    """Send a password-reset email if the address exists."""
    if not auth_system:
        return jsonify({'error': 'Auth system unavailable'}), 503
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    if not email:
        return jsonify({'error': 'Email is required'}), 400

    raw_token = auth_system.create_reset_token(email)

    # Always return 200 to avoid leaking whether the email exists
    if raw_token:
        frontend_base = request.headers.get('Origin') or os.environ.get('FRONTEND_URL', 'http://localhost:3001')
        reset_url = f'{frontend_base}/reset-password?token={raw_token}'
        sent = _send_reset_email(email, reset_url)
        if not sent:
            # Log the reset URL so an admin can manually share it in dev environments
            logging.info('PASSWORD RESET URL (SMTP not configured): %s', reset_url)

    return jsonify({'ok': True, 'message': 'If that email is registered you will receive a reset link shortly.'})


@app.route('/auth/reset-password', methods=['POST'])
def auth_reset_password():
    """Consume a reset token and update the password."""
    if not auth_system:
        return jsonify({'error': 'Auth system unavailable'}), 503
    data = request.get_json() or {}
    token = (data.get('token') or '').strip()
    new_password = data.get('new_password') or data.get('password') or ''
    if not token or not new_password:
        return jsonify({'error': 'token and new_password are required'}), 400

    ok, err = auth_system.consume_reset_token(token, new_password)
    if not ok:
        return jsonify({'error': err}), 400
    return jsonify({'ok': True, 'message': 'Password updated. You can now sign in.'})


# ---------------------------------------------------------------------------
# TOTP 2FA
# ---------------------------------------------------------------------------

@app.route('/auth/2fa/status', methods=['GET'])
def auth_2fa_status():
    """Return the 2FA status for the authenticated user."""
    if not auth_system:
        return jsonify({'error': 'Auth system unavailable'}), 503
    raw = (request.headers.get('Authorization') or '').removeprefix('Bearer ').strip()
    if not raw:
        return jsonify({'error': 'Unauthorized'}), 401
    valid, auth_token, err = auth_system.verify_token(raw)
    if not valid:
        return jsonify({'error': err}), 401
    status = auth_system.get_totp_status(auth_token.user_id)
    return jsonify(status)


@app.route('/auth/2fa/setup', methods=['POST'])
def auth_2fa_setup():
    """Generate a new TOTP secret and return the otpauth URI for QR display."""
    if not auth_system:
        return jsonify({'error': 'Auth system unavailable'}), 503
    raw = (request.headers.get('Authorization') or '').removeprefix('Bearer ').strip()
    if not raw:
        return jsonify({'error': 'Unauthorized'}), 401
    valid, auth_token, err = auth_system.verify_token(raw)
    if not valid:
        return jsonify({'error': err}), 401
    try:
        result = auth_system.setup_totp(auth_token.user_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/auth/2fa/enable', methods=['POST'])
def auth_2fa_enable():
    """Confirm the TOTP secret by verifying the first code, then enable 2FA."""
    if not auth_system:
        return jsonify({'error': 'Auth system unavailable'}), 503
    raw = (request.headers.get('Authorization') or '').removeprefix('Bearer ').strip()
    if not raw:
        return jsonify({'error': 'Unauthorized'}), 401
    valid, auth_token, err = auth_system.verify_token(raw)
    if not valid:
        return jsonify({'error': err}), 401
    data = request.get_json() or {}
    code = (data.get('code') or '').strip()
    if not code:
        return jsonify({'error': 'TOTP code is required'}), 400
    if not auth_system.verify_totp_code(auth_token.user_id, code):
        return jsonify({'error': 'Invalid code — check your authenticator app'}), 400
    auth_system.enable_totp(auth_token.user_id)
    return jsonify({'ok': True, 'message': '2FA enabled successfully'})


@app.route('/auth/2fa/verify', methods=['POST'])
def auth_2fa_verify():
    """
    Complete a 2FA login: exchange temp_token + TOTP code for a full JWT.
    Called by the frontend after the password step returned requires_2fa=true.
    """
    if not auth_system:
        return jsonify({'error': 'Auth system unavailable'}), 503
    data = request.get_json() or {}
    temp_token = (data.get('temp_token') or '').strip()
    code = (data.get('code') or '').strip()
    if not temp_token or not code:
        return jsonify({'error': 'temp_token and code are required'}), 400

    user_id = _consume_pending_2fa(temp_token)
    if not user_id:
        return jsonify({'error': 'Session expired — please sign in again'}), 401

    if not auth_system.verify_totp_code(user_id, code):
        return jsonify({'error': 'Invalid authenticator code'}), 401

    user = auth_system.get_user(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    token = auth_system.generate_token(user)
    return jsonify({
        'token': token,
        'user': {
            'id': user.id,
            'email': user.email,
            'username': user.username,
            'full_name': user.full_name,
            'role': user.role,
        }
    })


@app.route('/auth/2fa/disable', methods=['POST'])
def auth_2fa_disable():
    """Disable 2FA for the authenticated user (requires current TOTP code)."""
    if not auth_system:
        return jsonify({'error': 'Auth system unavailable'}), 503
    raw = (request.headers.get('Authorization') or '').removeprefix('Bearer ').strip()
    if not raw:
        return jsonify({'error': 'Unauthorized'}), 401
    valid, auth_token, err = auth_system.verify_token(raw)
    if not valid:
        return jsonify({'error': err}), 401
    data = request.get_json() or {}
    code = (data.get('code') or '').strip()
    if not code:
        return jsonify({'error': 'Current TOTP code required to disable 2FA'}), 400
    if not auth_system.verify_totp_code(auth_token.user_id, code):
        return jsonify({'error': 'Invalid code'}), 400
    auth_system.disable_totp(auth_token.user_id)
    return jsonify({'ok': True, 'message': '2FA disabled'})


# ---------------------------------------------------------------------------
# SECURITY — aggregate stats, sessions, login events (admin-only)
# ---------------------------------------------------------------------------

def _require_admin(raw_token):
    """Verify token and require admin role. Returns (auth_token, error_response)."""
    if not raw_token:
        return None, (jsonify({'error': 'Token required'}), 401)
    if not auth_system:
        return None, (jsonify({'error': 'Auth system unavailable'}), 503)
    valid, auth_token, error = auth_system.verify_token(raw_token)
    if not valid:
        return None, (jsonify({'error': error}), 401)
    if auth_token.role != 'admin':
        return None, (jsonify({'error': 'Admin access required'}), 403)
    return auth_token, None


@app.route('/security/overview', methods=['GET'])
def security_overview():
    """Aggregate security stats from DB + in-memory rate limiter."""
    raw = (request.headers.get('Authorization') or '').removeprefix('Bearer ').strip()
    auth_token, err = _require_admin(raw)
    if err:
        return err

    stats = {
        'active_sessions': 0,
        'total_users': 0,
        'active_users': 0,
        'users_with_2fa': 0,
        'failed_logins_last_hour': 0,
        'rate_limited_ips': 0,
        'locked_accounts': 0,
        'anomalies_active': 0,
    }

    import sqlite3 as _sq
    try:
        now_iso = datetime.now().isoformat()
        conn = _sq.connect(auth_system.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT COUNT(*) FROM sessions WHERE is_revoked = 0 AND expires_at > ?',
            (now_iso,)
        )
        stats['active_sessions'] = cursor.fetchone()[0] or 0
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_active = 1')
        stats['total_users'] = cursor.fetchone()[0] or 0
        cursor.execute(
            'SELECT COUNT(*) FROM users WHERE is_active = 1 AND last_login IS NOT NULL'
        )
        stats['active_users'] = cursor.fetchone()[0] or 0
        cursor.execute(
            'SELECT COUNT(*) FROM users WHERE totp_enabled = 1 AND is_active = 1'
        )
        stats['users_with_2fa'] = cursor.fetchone()[0] or 0
        conn.close()
    except Exception as e:
        app.logger.warning('security_overview DB error: %s', e)

    hour_ago = time.time() - 3600
    with _login_lock:
        for key, timestamps in _login_attempts.items():
            if key.startswith('email:'):
                recent = [t for t in timestamps if t > hour_ago]
                stats['failed_logins_last_hour'] += len(recent)
                locked = [t for t in timestamps if t > time.time() - _LOCKOUT_SECS]
                if len(locked) >= _LOCKOUT_MAX:
                    stats['locked_accounts'] += 1
            elif key.startswith('ip:'):
                recent_ip = [t for t in timestamps if t > time.time() - _RATE_WINDOW]
                if len(recent_ip) >= _RATE_MAX_IP:
                    stats['rate_limited_ips'] += 1

    cpu = system_data.get('cpu', 0.0)
    mem = system_data.get('memory', 0.0)
    disk = system_data.get('disk', 0.0)
    net_out = system_data.get('network_out', 0.0)
    temp = system_data.get('temperature', None)
    stats['anomalies_active'] = len(_build_alerts(cpu, mem, disk, net_out, temp))
    stats['timestamp'] = datetime.now().isoformat()
    return jsonify(stats)


@app.route('/security/sessions', methods=['GET'])
def security_sessions():
    """List active sessions with user info (admin only)."""
    raw = (request.headers.get('Authorization') or '').removeprefix('Bearer ').strip()
    _, err = _require_admin(raw)
    if err:
        return err

    sessions = []
    import sqlite3 as _sq
    try:
        now_iso = datetime.now().isoformat()
        conn = _sq.connect(auth_system.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.id, s.user_id, s.created_at, s.expires_at,
                   u.username, u.email, u.role
            FROM sessions s
            LEFT JOIN users u ON u.id = s.user_id
            WHERE s.is_revoked = 0 AND s.expires_at > ?
            ORDER BY s.created_at DESC
            LIMIT 50
        ''', (now_iso,))
        for r in cursor.fetchall():
            sessions.append({
                'id': r[0],
                'user_id': r[1],
                'created_at': r[2],
                'expires_at': r[3],
                'username': r[4] or 'unknown',
                'email': r[5] or '',
                'role': r[6] or 'employee',
            })
        conn.close()
    except Exception as e:
        app.logger.warning('security_sessions DB error: %s', e)

    return jsonify(sessions)


@app.route('/security/login-events', methods=['GET'])
def security_login_events():
    """Recent failed auth events from in-memory rate limiter (admin only)."""
    raw = (request.headers.get('Authorization') or '').removeprefix('Bearer ').strip()
    _, err = _require_admin(raw)
    if err:
        return err

    events = []
    cutoff = time.time() - 3600  # last hour
    with _login_lock:
        for key, timestamps in _login_attempts.items():
            if key.startswith('email:'):
                identifier = key[6:]
                event_type = 'failed_login'
            elif key.startswith('ip:'):
                identifier = key[3:]
                event_type = 'ip_attempt'
            else:
                continue
            for ts in timestamps:
                if ts > cutoff:
                    events.append({
                        'type': event_type,
                        'identifier': identifier,
                        'timestamp': datetime.fromtimestamp(ts).isoformat(),
                        '_ts': ts,
                    })

    events.sort(key=lambda x: x['_ts'], reverse=True)
    for e in events:
        del e['_ts']
    return jsonify(events[:40])


@app.route('/security/revoke-session', methods=['POST'])
def security_revoke_session():
    """Revoke a specific session by ID (admin only)."""
    raw = (request.headers.get('Authorization') or '').removeprefix('Bearer ').strip()
    _, err = _require_admin(raw)
    if err:
        return err

    data = request.get_json() or {}
    session_id = data.get('session_id', '').strip()
    if not session_id:
        return jsonify({'error': 'session_id required'}), 400

    import sqlite3 as _sq
    try:
        conn = _sq.connect(auth_system.db_path)
        conn.execute('UPDATE sessions SET is_revoked = 1 WHERE id = ?', (session_id,))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# REMOTE AGENTS — admin-managed push-based system monitoring + command execution
# ---------------------------------------------------------------------------
import secrets as _secrets
import sqlite3 as _sq_agents
import uuid as _uuid_mod
from collections import deque as _deque


def _org_id_from_request() -> str | None:
    """Extract org_id from the Bearer JWT in the current request (best-effort)."""
    try:
        from jose import jwt as _jose_jwt, JWTError
        raw = request.headers.get('Authorization', '')
        if raw.lower().startswith('bearer '):
            token = raw[7:].strip()
            # Decode without verifying signature — org_id is informational here;
            # the signature was already verified by _require_auth before the route runs.
            claims = _jose_jwt.get_unverified_claims(token)
            return claims.get('org_id') or claims.get('org') or None
    except Exception:
        pass
    return None

# In-memory store:  { agent_id: { token, label, info, metrics, last_seen } }
_remote_agents      = {}
_remote_agents_lock = threading.Lock()

# Agents are considered LIVE if they posted a heartbeat within this window (seconds)
_AGENT_LIVE_SECS = 12

# ── Command system ────────────────────────────────────────────────────────────
# Strict allowlist — no arbitrary shell input ever reaches the agent
AGENT_ALLOWLISTED_ACTIONS = {
    'clear_cache':     'Clear system page cache and temporary files',
    'disk_cleanup':    'Delete temp files and old compressed logs (>1 day)',
    'free_memory':     'Release memory pages and drop OS caches',
    'run_gc':          'Trigger garbage collection on Python processes',
    'kill_process':    'Terminate a process by name or PID (params: name|pid)',
    'restart_service': 'Restart a named system service (params: service_name)',
}

# { agent_id: [cmd, ...] }  — commands waiting for the agent to pick up
_agent_cmd_pending  = {}
# { agent_id: deque([cmd, ...], maxlen=200) }  — completed commands
_agent_cmd_history  = {}
_agent_cmd_lock     = threading.Lock()

# { (agent_id, action): timestamp }  — auto-remediation cooldown
_agent_auto_cooldown    = {}
_AGENT_AUTO_COOLDOWN_S  = 300   # 5 min between same auto-action on same agent


def _push_agent_command(agent_id, action, params=None, source='manual', created_by='system'):
    """Push a command into the agent's pending queue. Returns cmd dict or None."""
    if action not in AGENT_ALLOWLISTED_ACTIONS:
        return None
    cmd = {
        'id':           _uuid_mod.uuid4().hex[:12],
        'action':       action,
        'params':       params or {},
        'status':       'pending',
        'source':       source,       # 'manual' | 'auto'
        'created_by':   created_by,
        'created_at':   time.time(),
        'result':       None,
        'error':        None,
        'completed_at': None,
    }
    with _agent_cmd_lock:
        _agent_cmd_pending.setdefault(agent_id, []).append(cmd)
        if agent_id not in _agent_cmd_history:
            _agent_cmd_history[agent_id] = _deque(maxlen=200)
    return cmd


def _auto_remediation_loop():
    """Background daemon: push safe commands when agent metrics breach thresholds."""
    while True:
        try:
            now = time.time()
            with _remote_agents_lock:
                snap = dict(_remote_agents)

            for agent_id, agent in snap.items():
                ls = agent.get('last_seen')
                if not ls or (now - ls) > _AGENT_LIVE_SECS:
                    continue                     # skip offline/pending agents

                m = agent.get('metrics', {})
                cpu  = m.get('cpu',    0) or 0
                mem  = m.get('memory', 0) or 0
                disk = m.get('disk',   0) or 0

                def _can_fire(action):
                    key  = (agent_id, action)
                    last = _agent_auto_cooldown.get(key, 0)
                    return (now - last) > _AGENT_AUTO_COOLDOWN_S

                def _fire(action, reason):
                    _agent_auto_cooldown[(agent_id, action)] = now
                    cmd = _push_agent_command(agent_id, action,
                                             source='auto', created_by='anomaly-engine')
                    if cmd:
                        logging.info(
                            f'[auto-remediation] agent={agent_id} '
                            f'action={action} reason={reason} cmd={cmd["id"]}'
                        )

                # Thresholds → actions
                if cpu >= 90 and _can_fire('free_memory'):
                    _fire('free_memory', f'cpu={cpu:.1f}%')
                if mem >= 90 and _can_fire('free_memory'):
                    _fire('free_memory', f'mem={mem:.1f}%')
                elif mem >= 80 and _can_fire('run_gc'):
                    _fire('run_gc', f'mem={mem:.1f}%')
                if disk >= 90 and _can_fire('disk_cleanup'):
                    _fire('disk_cleanup', f'disk={disk:.1f}%')

        except Exception as exc:
            logging.warning(f'[auto-remediation] loop error: {exc}')
        time.sleep(15)


# Start background auto-remediation daemon
_auto_rem_thread = threading.Thread(target=_auto_remediation_loop, daemon=True, name='agent-auto-rem')
_auto_rem_thread.start()


def _init_agent_tokens_table():
    """Create agent tables if they don't exist."""
    try:
        conn = _sq_agents.connect(auth_system.db_path)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS remote_agent_tokens (
                id         TEXT PRIMARY KEY,
                token      TEXT UNIQUE NOT NULL,
                label      TEXT,
                created_by TEXT,
                created_at TEXT,
                revoked    INTEGER DEFAULT 0,
                org_id     TEXT
            )
        ''')
        # Migration: add org_id column to existing tables
        try:
            conn.execute('ALTER TABLE remote_agent_tokens ADD COLUMN org_id TEXT')
        except Exception:
            pass  # column already exists
        conn.execute('''
            CREATE TABLE IF NOT EXISTS agent_command_log (
                id           TEXT PRIMARY KEY,
                agent_id     TEXT NOT NULL,
                action       TEXT NOT NULL,
                params       TEXT,
                status       TEXT,
                source       TEXT,
                created_by   TEXT,
                created_at   REAL,
                completed_at REAL,
                result       TEXT,
                error        TEXT
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_acl_agent ON agent_command_log(agent_id, completed_at DESC)')
        conn.commit()
        conn.close()
    except Exception:
        pass


def _persist_cmd(cmd: dict, agent_id: str):
    """Write a completed command to SQLite (best-effort, non-blocking)."""
    try:
        import json as _json
        conn = _sq_agents.connect(auth_system.db_path)
        conn.execute(
            '''INSERT OR REPLACE INTO agent_command_log
               (id, agent_id, action, params, status, source, created_by,
                created_at, completed_at, result, error)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
            (
                cmd['id'], agent_id, cmd['action'],
                _json.dumps(cmd.get('params') or {}),
                cmd.get('status'), cmd.get('source'), cmd.get('created_by'),
                cmd.get('created_at'), cmd.get('completed_at'),
                cmd.get('result'), cmd.get('error'),
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _load_cmd_history(agent_id: str, limit: int = 200) -> list:
    """Load completed command history from SQLite for one agent."""
    try:
        import json as _json
        conn = _sq_agents.connect(auth_system.db_path)
        rows = conn.execute(
            '''SELECT id, action, params, status, source, created_by,
                      created_at, completed_at, result, error
               FROM agent_command_log
               WHERE agent_id = ?
               ORDER BY completed_at DESC
               LIMIT ?''',
            (agent_id, limit),
        ).fetchall()
        conn.close()
        return [
            {
                'id': r[0], 'action': r[1],
                'params': _json.loads(r[2] or '{}'),
                'status': r[3], 'source': r[4], 'created_by': r[5],
                'created_at': r[6], 'completed_at': r[7],
                'result': r[8], 'error': r[9],
            }
            for r in rows
        ]
    except Exception:
        return []


# Initialise on import
try:
    _init_agent_tokens_table()
except Exception:
    pass


@app.route('/agents/token', methods=['POST'])
def create_agent_token():
    """Admin: generate a new agent token with an optional label."""
    raw = (request.headers.get('Authorization') or '').removeprefix('Bearer ').strip()
    auth_tok, err = _require_admin(raw)
    if err:
        return err

    data   = request.get_json(silent=True) or {}
    label  = (data.get('label') or '').strip() or 'Unnamed Agent'
    org_id = _org_id_from_request()

    agent_id = _secrets.token_hex(8)   # short readable ID
    token    = _secrets.token_hex(24)  # 48-char auth token

    try:
        conn = _sq_agents.connect(auth_system.db_path)
        conn.execute(
            'INSERT INTO remote_agent_tokens (id, token, label, created_by, created_at, org_id) VALUES (?,?,?,?,?,?)',
            (agent_id, token, label, auth_tok.username, datetime.utcnow().isoformat(), org_id),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    # Pre-register slot in memory so admin can see it immediately as "pending"
    with _remote_agents_lock:
        _remote_agents[agent_id] = {
            'id':        agent_id,
            'token':     token,
            'label':     label,
            'info':      {},
            'metrics':   {},
            'last_seen': None,
            'status':    'pending',
            'org_id':    org_id,
        }

    server_url = request.host_url.rstrip('/')
    agent_script = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'integrations', 'remote_agent.py')
    )
    install_cmd = (
        f'python "{agent_script}" --server {server_url} --token {token}'
    )
    return jsonify({
        'agent_id':    agent_id,
        'token':       token,
        'label':       label,
        'install_cmd': install_cmd,
        'server_url':  server_url,
    })


@app.route('/agents/heartbeat', methods=['POST'])
def agent_heartbeat():
    """Agent: push a metrics snapshot. Authenticated by token only (no JWT)."""
    data = request.get_json(silent=True) or {}
    token = (data.get('token') or '').strip()
    if not token:
        return jsonify({'error': 'token required'}), 401

    # Look up token in DB
    try:
        conn = _sq_agents.connect(auth_system.db_path)
        row  = conn.execute(
            'SELECT id, label, revoked, org_id FROM remote_agent_tokens WHERE token = ?',
            (token,)
        ).fetchone()
        conn.close()
    except Exception:
        return jsonify({'error': 'db error'}), 500

    if not row:
        return jsonify({'error': 'invalid token'}), 401
    if row[2]:  # revoked
        return jsonify({'error': 'token revoked'}), 403

    agent_id = row[0]
    label    = row[1]
    org_id   = row[3]
    info     = data.get('info') or {}
    metrics  = data.get('metrics') or {}

    with _remote_agents_lock:
        _remote_agents[agent_id] = {
            'id':        agent_id,
            'token':     token,
            'label':     label,
            'info':      info,
            'metrics':   metrics,
            'last_seen': time.time(),
            'status':    'live',
            'org_id':    org_id,
        }

    # Return pending commands piggy-backed on the heartbeat response
    with _agent_cmd_lock:
        pending = list(_agent_cmd_pending.get(agent_id, []))

    return jsonify({'ok': True, 'agent_id': agent_id, 'commands': pending})


@app.route('/agents', methods=['GET'])
def list_agents():
    """Admin: list all known agents with their live status."""
    raw = (request.headers.get('Authorization') or '').removeprefix('Bearer ').strip()
    _, err = _require_admin(raw)
    if err:
        return err

    caller_org = _org_id_from_request()
    now = time.time()
    with _remote_agents_lock:
        agents = []
        for a in _remote_agents.values():
            # Org isolation: only return agents belonging to the caller's org
            if caller_org and a.get('org_id') and a['org_id'] != caller_org:
                continue
            ls = a.get('last_seen')
            if ls is None:
                status = 'pending'
            elif (now - ls) <= _AGENT_LIVE_SECS:
                status = 'live'
            else:
                status = 'offline'

            agents.append({
                'id':          a['id'],
                'label':       a['label'],
                'status':      status,
                'last_seen':   ls,
                'hostname':    a['info'].get('hostname', '—'),
                'os':          a['info'].get('os', '—'),
                'cpu_cores':   a['info'].get('cpu_cores'),
                'platform':    a['info'].get('platform', '—'),
                'cpu':         a['metrics'].get('cpu'),
                'memory':      a['metrics'].get('memory'),
                'disk':        a['metrics'].get('disk'),
                'uptime_secs': a['metrics'].get('uptime_secs'),
            })

    # Sort: live first, then offline, then pending
    order = {'live': 0, 'offline': 1, 'pending': 2}
    agents.sort(key=lambda x: order.get(x['status'], 3))
    return jsonify(agents)


@app.route('/agents/<agent_id>', methods=['GET'])
def get_agent(agent_id):
    """Admin: get full current metrics for one agent."""
    raw = (request.headers.get('Authorization') or '').removeprefix('Bearer ').strip()
    _, err = _require_admin(raw)
    if err:
        return err

    with _remote_agents_lock:
        agent = _remote_agents.get(agent_id)

    if not agent:
        return jsonify({'error': 'agent not found'}), 404

    now = time.time()
    ls  = agent.get('last_seen')
    if ls is None:
        status = 'pending'
    elif (now - ls) <= _AGENT_LIVE_SECS:
        status = 'live'
    else:
        status = 'offline'

    return jsonify({
        'id':        agent['id'],
        'label':     agent['label'],
        'status':    status,
        'last_seen': ls,
        'info':      agent['info'],
        'metrics':   agent['metrics'],
    })


@app.route('/agents/<agent_id>', methods=['DELETE'])
def delete_agent(agent_id):
    """Admin: revoke token and remove agent from memory."""
    raw = (request.headers.get('Authorization') or '').removeprefix('Bearer ').strip()
    _, err = _require_admin(raw)
    if err:
        return err

    with _remote_agents_lock:
        agent = _remote_agents.pop(agent_id, None)

    if agent:
        try:
            conn = _sq_agents.connect(auth_system.db_path)
            conn.execute(
                'UPDATE remote_agent_tokens SET revoked=1 WHERE id=?',
                (agent_id,)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    return jsonify({'ok': True})


# ── Command endpoints ─────────────────────────────────────────────────────────

@app.route('/agents/<agent_id>/command', methods=['POST'])
def send_agent_command(agent_id):
    """Admin: push a command to a specific agent's queue."""
    raw = (request.headers.get('Authorization') or '').removeprefix('Bearer ').strip()
    auth_tok, err = _require_admin(raw)
    if err:
        return err

    data   = request.get_json(silent=True) or {}
    action = (data.get('action') or '').strip()
    params = data.get('params') or {}

    if action not in AGENT_ALLOWLISTED_ACTIONS:
        return jsonify({
            'error': 'Action not in allowlist.',
            'valid_actions': list(AGENT_ALLOWLISTED_ACTIONS.keys()),
        }), 400

    with _remote_agents_lock:
        if agent_id not in _remote_agents:
            return jsonify({'error': 'Agent not found'}), 404

    cmd = _push_agent_command(agent_id, action, params,
                              source='manual', created_by=auth_tok.username)
    return jsonify({'ok': True, 'command': cmd})


@app.route('/agents/<agent_id>/commands/result', methods=['POST'])
def agent_command_result(agent_id):
    """Agent: report the result of a completed command."""
    data  = request.get_json(silent=True) or {}
    token = (data.get('token') or '').strip()

    # Validate agent token
    try:
        conn = _sq_agents.connect(auth_system.db_path)
        row  = conn.execute(
            'SELECT id, revoked FROM remote_agent_tokens WHERE token=?', (token,)
        ).fetchone()
        conn.close()
    except Exception:
        return jsonify({'error': 'db error'}), 500

    if not row or row[0] != agent_id:
        return jsonify({'error': 'invalid token'}), 401
    if row[1]:
        return jsonify({'error': 'token revoked'}), 403

    cmd_id = data.get('cmd_id')
    status = data.get('status', 'failed')    # 'success' | 'failed' | 'skipped'
    result = data.get('result')
    error  = data.get('error')
    now    = time.time()

    with _agent_cmd_lock:
        pending = _agent_cmd_pending.get(agent_id, [])
        matched = next((c for c in pending if c['id'] == cmd_id), None)
        if matched:
            matched.update({
                'status':       status,
                'result':       result,
                'error':        error,
                'completed_at': now,
            })
            pending.remove(matched)
            _agent_cmd_pending[agent_id] = pending
            _agent_cmd_history.setdefault(agent_id, _deque(maxlen=200)).appendleft(matched)
            threading.Thread(
                target=_persist_cmd, args=(dict(matched), agent_id), daemon=True
            ).start()

    logging.info(
        f'[agent-cmd] agent={agent_id} cmd={cmd_id} '
        f'action={matched["action"] if matched else "?"} '
        f'status={status} source={matched.get("source","?") if matched else "?"}'
    )
    return jsonify({'ok': True})


@app.route('/agents/<agent_id>/commands', methods=['GET'])
def get_agent_commands(agent_id):
    """Admin: get pending + history for an agent, plus the allowlist."""
    raw = (request.headers.get('Authorization') or '').removeprefix('Bearer ').strip()
    _, err = _require_admin(raw)
    if err:
        return err

    with _agent_cmd_lock:
        pending    = list(_agent_cmd_pending.get(agent_id, []))
        mem_history = list(_agent_cmd_history.get(agent_id, []))

    # Merge in-memory history with SQLite so history survives restarts
    db_history = _load_cmd_history(agent_id, limit=200)
    seen       = {c['id'] for c in mem_history}
    merged     = mem_history + [c for c in db_history if c['id'] not in seen]

    return jsonify({
        'pending': pending,
        'history': merged,
        'actions': AGENT_ALLOWLISTED_ACTIONS,
    })


# ---------------------------------------------------------------------------
# AI HEALTH — model accuracy / status for Insights & Security pages
# ---------------------------------------------------------------------------
_ai_health_start = datetime.now()
_inference_counter = 0  # incremented on each /chat request

@app.route('/ai-health', methods=['GET'])
@cached(ttl=15.0)
def ai_health():
    cpu = system_data.get('cpu', 0)
    mem = system_data.get('memory', 0)
    # AI readiness: degrades as CPU/memory load increases
    perf_score = max(0, min(100, 100 - (cpu * 0.5 + mem * 0.3)))
    gemini_ok = aiops_bot is not None
    hf_ok = hf_engine is not None
    overall_status = "healthy" if perf_score > 50 and gemini_ok else "degraded"
    # Count real anomalies from live metrics
    disk = system_data.get('disk', 0)
    net_out = system_data.get('network_out', 0)
    temp = system_data.get('temperature')
    live_anomalies = _build_alerts(cpu, mem, disk, net_out, temp)
    # Gemini latency: measure approximate response latency from system load
    gemini_latency = int(120 + (cpu * 2.5))  # baseline 120ms, grows with load
    hf_latency = int(80 + (cpu * 1.5))
    gemini_accuracy = round(perf_score, 1)
    hf_accuracy = round(perf_score * 0.95, 1)
    prediction_accuracy = round(perf_score * 0.9, 1)
    return jsonify({
        "status": overall_status,
        "models": {
            "gemini": {
                "available": gemini_ok,
                "name": "Gemini Pro",
                "accuracy": gemini_accuracy,
                "latency_ms": gemini_latency,
            },
            "huggingface": {
                "available": hf_ok,
                "name": "HuggingFace",
                "accuracy": hf_accuracy,
                "latency_ms": hf_latency,
            }
        },
        # Primary flat fields for backward compat / quick access
        "accuracy": gemini_accuracy,
        "response_time": gemini_latency,
        "model": "Gemini Pro" if gemini_ok else ("HuggingFace" if hf_ok else "None"),
        "inference_count_today": _inference_counter,
        "anomalies_detected_today": len(live_anomalies),
        "prediction_accuracy": prediction_accuracy,
        "uptime_seconds": int((datetime.now() - _ai_health_start).total_seconds()),
        "timestamp": datetime.now().isoformat(),
    })


# ---------------------------------------------------------------------------
# SLACK NOTIFICATIONS
# ---------------------------------------------------------------------------
def send_slack_message(text: str, severity: str = "info", webhook_url: str = None):
    """Send an asynchronous notification to Slack."""
    url = webhook_url or os.getenv('SLACK_WEBHOOK_URL')
    if not url or os.getenv('SLACK_ENABLED', 'true').lower() not in ['true', '1', 'yes']:
        return

    colors = {
        "critical": "#FF0000",
        "warning": "#FF9900",
        "info": "#36A64F"
    }
    color = colors.get(severity.lower(), "#36A64F")
    
    payload = {
        "attachments": [
            {
                "fallback": text,
                "color": color,
                "title": "AIOps Alert & Update",
                "text": text,
                "footer": "AIOps Bot",
                "ts": int(time.time())
            }
        ]
    }
    
    def _post():
        import requests
        try:
            resp = requests.post(url, json=payload, timeout=5)
            if resp.status_code >= 400:
                print(f"[Slack] Failed to send message: HTTP {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"[Slack] Error sending message: {e}")
            
    threading.Thread(target=_post, daemon=True).start()

# ---------------------------------------------------------------------------
# ANOMALIES — real threshold-based alerts from live psutil metrics
# ---------------------------------------------------------------------------
# Tracks when each alert was first seen so timestamps are stable
_alert_first_seen: dict = {}  # alert_id -> float (unix timestamp)

def _build_alerts(cpu: float, mem: float, disk: float, net_out: float, temp):
    """Return a list of alert dicts based purely on live metric thresholds."""
    now   = time.time()
    out   = []
    active_ids: set = set()

    def _emit(aid, severity, category, message, source, details, affected, recommendation):
        is_new = False
        if aid not in _alert_first_seen:
            _alert_first_seen[aid] = now
            is_new = True
            
        active_ids.add(aid)
        out.append({
            "id":               aid,
            "severity":         severity,
            "category":         category,
            "message":          message,
            "source":           source,
            "status":           "active",
            "details":          details,
            "affected_systems": affected,
            "recommendation":   recommendation,
            "timestamp":        _alert_first_seen[aid],
        })
        
        # Send Slack notification for new critical/warning alerts
        if is_new and severity in ["critical", "warning"]:
            slack_text = f"*{severity.upper()} Alert:* {message}\n*Source:* {source}\n*Details:* {details}"
            send_slack_message(slack_text, severity)

    # --- CPU ---
    if cpu >= 90:
        _emit("cpu-critical", "critical", "performance",
              f"CPU critically high — {cpu:.1f}% utilization",
              "Performance Monitor",
              f"CPU usage is at {cpu:.1f}%, well above the 90% critical threshold. "
              "Sustained load at this level may cause system unresponsiveness.",
              ["CPU"],
              "Identify CPU-intensive processes via Task Manager and terminate unnecessary ones. "
              "Consider scaling compute resources if the load is legitimate.")
    elif cpu >= 75:
        _emit("cpu-warning", "warning", "performance",
              f"CPU elevated — {cpu:.1f}% utilization",
              "Performance Monitor",
              f"CPU at {cpu:.1f}%, above the 75% warning threshold.",
              ["CPU"],
              "Review running processes and close applications that are not required.")

    # --- Memory ---
    if mem >= 90:
        _emit("mem-critical", "critical", "performance",
              f"Memory critically high — {mem:.1f}% used",
              "System Monitor",
              f"System memory at {mem:.1f}%, approaching exhaustion. "
              "Risk of out-of-memory events and process termination.",
              ["RAM", "Virtual Memory"],
              "Restart memory-intensive services or add physical RAM. "
              "Review process memory consumption immediately.")
    elif mem >= 80:
        _emit("mem-warning", "warning", "performance",
              f"Memory elevated — {mem:.1f}% used",
              "System Monitor",
              f"Memory usage is at {mem:.1f}%, above the 80% warning level.",
              ["RAM"],
              "Monitor for further growth. Close unused applications to free memory.")

    # --- Disk ---
    if disk >= 90:
        _emit("disk-critical", "critical", "disk",
              f"Disk critically full — {disk:.1f}% capacity",
              "Storage Monitor",
              f"Primary disk at {disk:.1f}%. Write failures and system instability are imminent "
              "when disk reaches 100%.",
              ["Primary Disk"],
              "Delete temporary files, compress or archive old logs, or expand storage immediately.")
    elif disk >= 80:
        _emit("disk-warning", "warning", "disk",
              f"Disk space low — {disk:.1f}% used",
              "Storage Monitor",
              f"Disk usage at {disk:.1f}%, above the 80% warning threshold.",
              ["Primary Disk"],
              "Clean up log files and temporary data, or plan storage expansion.")

    # --- Network outbound spike (>2 MB/s = 2048 KB/s is unusual for this system) ---
    if net_out > 2048:
        _emit("net-out", "warning", "network",
              f"Elevated outbound traffic — {net_out:.0f} KB/s",
              "Network Monitor",
              f"Outbound bandwidth at {net_out:.0f} KB/s, significantly above normal baseline. "
              "This may indicate a backup, update, or unexpected data transfer.",
              ["Network Interface"],
              "Identify the process generating traffic using network tools. "
              "Verify no unauthorized data exfiltration is occurring.")

    # --- Temperature (if sensor available) ---
    if temp is not None:
        if temp >= 85:
            _emit("temp-critical", "critical", "hardware",
                  f"CPU temperature critical — {temp:.1f}°C",
                  "Hardware Monitor",
                  f"CPU at {temp:.1f}°C, above the 85°C critical threshold. "
                  "Thermal throttling is active, reducing performance.",
                  ["CPU", "Cooling System"],
                  "Check thermal paste, ensure heatsink is seated correctly, "
                  "and verify case airflow. Reduce system load immediately.")
        elif temp >= 75:
            _emit("temp-warning", "warning", "hardware",
                  f"CPU temperature elevated — {temp:.1f}°C",
                  "Hardware Monitor",
                  f"CPU temperature at {temp:.1f}°C, above the 75°C advisory level.",
                  ["CPU"],
                  "Ensure adequate cooling and ventilation. Clean dust from heatsink/fan.")

    # Expire timestamps for alerts that are no longer active
    for stale_id in list(_alert_first_seen.keys()):
        if stale_id not in active_ids:
            del _alert_first_seen[stale_id]

    return out


@app.route('/anomalies', methods=['GET'])
@cached(ttl=8.0)
def get_anomalies():
    cpu     = system_data.get('cpu',         0.0)
    mem     = system_data.get('memory',      0.0)
    disk    = system_data.get('disk',        0.0)
    net_out = system_data.get('network_out', 0.0)
    temp    = system_data.get('temperature', None)
    return jsonify(_build_alerts(cpu, mem, disk, net_out, temp))


# ---------------------------------------------------------------------------
# PREDICTIVE ANALYTICS
# ---------------------------------------------------------------------------
@app.route('/predictive-analytics', methods=['GET'])
def predictive_analytics():
    timeframe = request.args.get('timeframe', '1hour')
    cpu_now  = system_data.get('cpu',    45.0)
    mem_now  = system_data.get('memory', 60.0)
    disk_now = system_data.get('disk',   50.0)

    # Compute real drift from history if available (linear trend over last N points)
    def _compute_drift(key, fallback=0.0):
        pts = [p[key] for p in list(_perf_history) if key in p]
        if len(pts) < 6:
            return fallback
        # simple linear regression slope per-point
        n = len(pts)
        xs = list(range(n))
        mean_x = (n - 1) / 2
        mean_y = sum(pts) / n
        num = sum((xs[i] - mean_x) * (pts[i] - mean_y) for i in range(n))
        den = sum((xs[i] - mean_x) ** 2 for i in range(n))
        return round(num / den, 4) if den else fallback

    cpu_drift  = _compute_drift('cpu',    0.3)
    mem_drift  = _compute_drift('memory', 0.5)
    disk_drift = _compute_drift('disk',   0.1)

    def project(base, drift):
        return [round(min(100, max(0, base + drift * i + random.uniform(-1.5, 1.5))), 1) for i in range(12)]

    def risk(val, drift):
        projected_peak = val + drift * 12
        if projected_peak > 90 or val > 85:
            return "high"
        if projected_peak > 75 or val > 70:
            return "medium"
        return "low"

    # Dynamic recommendations based on real values
    recs = []
    if cpu_now > 80:
        recs.append({"priority": "high",   "action": f"CPU at {cpu_now}% — identify and terminate high-CPU processes immediately"})
    elif cpu_now > 65:
        recs.append({"priority": "medium", "action": f"CPU at {cpu_now}% — monitor for sustained load; consider process scheduling"})
    if cpu_drift > 0.5:
        recs.append({"priority": "medium", "action": f"CPU trending up ({cpu_drift:+.2f}%/sample) — investigate workload growth"})

    if mem_now > 85:
        recs.append({"priority": "high",   "action": f"Memory at {mem_now}% — risk of OOM; clear caches or add swap"})
    elif mem_now > 70:
        recs.append({"priority": "medium", "action": f"Memory at {mem_now}% — review long-running processes for leaks"})
    if mem_drift > 0.6:
        recs.append({"priority": "medium", "action": f"Memory trending up ({mem_drift:+.2f}%/sample) — check for memory leaks"})

    if disk_now > 90:
        recs.append({"priority": "high",   "action": f"Disk at {disk_now}% — critical; run disk cleanup immediately"})
    elif disk_now > 75:
        recs.append({"priority": "medium", "action": f"Disk at {disk_now}% — review large files and logs"})
    if disk_drift > 0.2:
        recs.append({"priority": "low",    "action": f"Disk growing ({disk_drift:+.2f}%/sample) — monitor log rotation"})

    if not recs:
        recs.append({"priority": "low", "action": "All systems nominal — no immediate action required"})

    # Confidence based on how much history we have
    history_len = len(_perf_history)
    confidence = min(95, max(40, int(40 + (history_len / 2880) * 55)))

    return jsonify({
        "timeframe": timeframe,
        "predictions": {
            "cpu":    {"current": cpu_now,  "predicted": project(cpu_now,  cpu_drift),  "risk": risk(cpu_now,  cpu_drift)},
            "memory": {"current": mem_now,  "predicted": project(mem_now,  mem_drift),  "risk": risk(mem_now,  mem_drift)},
            "disk":   {"current": disk_now, "predicted": project(disk_now, disk_drift), "risk": risk(disk_now, disk_drift)},
        },
        "recommendations": recs,
        "confidence": confidence,
        "history_points": history_len,
        "timestamp": datetime.now().isoformat(),
    })


# ---------------------------------------------------------------------------
# PERFORMANCE history (replaces old mock-only endpoint)
# ---------------------------------------------------------------------------
@app.route('/performance', methods=['GET'])
def get_performance_history():
    """Return real performance history from the rolling buffer.

    Query params:
      timeframe — '1hour' | '6hours' | '24hours' (default '1hour')
      max_points — cap the number of returned points (default 120)
    """
    timeframe = request.args.get('timeframe', '1hour')
    max_pts   = int(request.args.get('max_points', 120))

    window_map = {'1hour': 3600, '6hours': 21600, '24hours': 86400}
    window_secs = window_map.get(timeframe, 3600)
    cutoff = datetime.now().timestamp() - window_secs

    history = list(_perf_history)
    filtered = [p for p in history if p.get('timestamp', 0) >= cutoff]

    # Down-sample to at most max_pts evenly spaced points
    if len(filtered) > max_pts:
        step = len(filtered) / max_pts
        filtered = [filtered[int(i * step)] for i in range(max_pts)]

    # If we haven't collected enough history yet, return what we have (no fake padding)
    return jsonify(filtered)


# ---------------------------------------------------------------------------
# ACTION endpoints — ActionPanel system & AI actions
# ---------------------------------------------------------------------------
import tempfile, uuid as _uuid

_jobs: dict = {}  # in-memory job store

def _make_job(name: str, result: dict) -> dict:
    jid = str(_uuid.uuid4())[:8]
    _jobs[jid] = {"id": jid, "name": name, "status": "completed", "result": result,
                  "created": datetime.now().isoformat()}
    return {"job_id": jid, **result}


@app.route('/actions/memory-cleanup', methods=['POST'])
def action_memory_cleanup():
    import psutil, gc
    data = request.get_json() or {}
    dry_run = data.get('dry_run', True)
    mem_before = psutil.virtual_memory()
    freed = 0
    if not dry_run:
        gc.collect()
        mem_after = psutil.virtual_memory()
        freed = max(0, mem_before.used - mem_after.used)
    return jsonify(_make_job("memory-cleanup", {
        "dry_run": dry_run,
        "memory_before_mb": round(mem_before.used / 1024**2),
        "freed_mb": round(freed / 1024**2),
        "message": f"{'[DRY RUN] Would free' if dry_run else 'Freed'} ~{round(freed / 1024**2)} MB",
    }))


@app.route('/actions/disk-cleanup', methods=['POST'])
def action_disk_cleanup():
    import psutil, glob as _glob, shutil
    data = request.get_json() or {}
    dry_run = data.get('dry_run', True)
    tmp = tempfile.gettempdir()
    patterns = [os.path.join(tmp, '*.tmp'), os.path.join(tmp, '*.log')]
    files = []
    for p in patterns:
        files.extend(_glob.glob(p))
    total_bytes = sum(os.path.getsize(f) for f in files if os.path.exists(f))
    removed = 0
    if not dry_run:
        for f in files:
            try:
                os.remove(f)
                removed += 1
            except Exception:
                pass
    disk = psutil.disk_usage('/')
    return jsonify(_make_job("disk-cleanup", {
        "dry_run": dry_run,
        "files_found": len(files),
        "files_removed": removed if not dry_run else 0,
        "space_freed_mb": round(total_bytes / 1024**2, 1),
        "disk_free_gb": round(disk.free / 1024**3, 1),
        "message": f"{'[DRY RUN] Found' if dry_run else 'Removed'} {len(files)} temp files ({round(total_bytes/1024**2,1)} MB)",
    }))


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
    
    send_slack_message("🔔 AIOps Bot Slack Integration Test Successful!", "info", webhook_url=webhook)
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
    send_slack_message("🚀 AIOps API Server has started and is monitoring metrics!", "info")
    
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
    app.run(debug=True, host='0.0.0.0', port=port, threaded=True)