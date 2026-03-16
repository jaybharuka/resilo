"""
AIOps AI Chatbot Backend
Intelligent system analysis and response generation using Google Gemini AI
"""

import json
import sys
import time
import psutil
import subprocess
import threading
import os
from datetime import datetime, timedelta
import platform as py_platform
from flask import Flask, request, jsonify, render_template_string, Response, send_file
import secrets
from flask_cors import CORS
from urllib.parse import urlparse
import requests
import tempfile
import shutil
import ctypes
import sqlite3
import hashlib
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
try:
    import google.generativeai as genai
except Exception:
    genai = None
import yaml
from pathlib import Path
try:
    from enhanced_ai_system import initialize_enhanced_ai
except Exception:
    def initialize_enhanced_ai(api_key: str):
        return None

app = Flask(__name__)

# --- Logging: rotate app logs for production hardening ---
try:
    import logging
    from logging.handlers import RotatingFileHandler
    logs_dir = os.path.join(os.getcwd(), 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    file_handler = RotatingFileHandler(os.path.join(logs_dir, 'backend.log'), maxBytes=2*1024*1024, backupCount=3)
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    file_handler.setFormatter(formatter)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
except Exception as _log_e:
    try:
        print(f"[LOG] Setup warning: {_log_e}")
    except Exception:
        pass

# Allow cross-origin requests from loopback and local network (LAN) by default.
# You can further customize by setting ALLOWED_ORIGINS env var to a comma-separated list, e.g.:
#   ALLOWED_ORIGINS="http://localhost:3000,http://127.0.0.1:3000,http://192.168.29.75:3000"
def _build_allowed_origins():
    env_val = os.getenv('ALLOWED_ORIGINS', '')
    env_list = [o.strip() for o in env_val.split(',') if o.strip()]
    defaults = [
        'http://localhost:3000', 'http://127.0.0.1:3000',
        'http://localhost:3001', 'http://127.0.0.1:3001',
        'http://localhost:3002', 'http://127.0.0.1:3002',
    ]
    # Also include common LAN patterns if the server has a 192.168.x.x address
    try:
        lan_host = None
        # Prefer the address Flask announces during boot if provided via env
        lan_host = os.getenv('LAN_HOST') or None
        if not lan_host:
            # Best-effort: derive LAN host from hostname resolution
            import socket
            hn = socket.gethostname()
            ip = socket.gethostbyname(hn)
            if ip.startswith('192.168.'):
                lan_host = ip
        if lan_host:
            defaults.extend([
                f'http://{lan_host}:3000', f'http://{lan_host}:3001', f'http://{lan_host}:3002'
            ])
    except Exception:
        pass
    return set(defaults + env_list)

_ALLOWED_ORIGINS = _build_allowed_origins()

# Flask-CORS configuration: allow regex for localhost/127.0.0.1 and 192.168.* on common ports
CORS(
    app,
    resources={
        r"/*": {
            "origins": list(_ALLOWED_ORIGINS) + [r"http://(localhost|127\.0\.0\.1|192\.168\.[0-9]{1,3}\.[0-9]{1,3})(:[0-9]{2,5})?"],
        }
    },
    supports_credentials=True,
    expose_headers=["Authorization"],
    allow_headers=["Authorization", "Content-Type", "content-type", "Accept", "X-Requested-With"],
)

# --- Explicit CORS middleware (belt-and-suspenders) ---
def _origin_allowed(origin: str) -> bool:
    if not origin:
        return False
    # Direct match from configured list
    if origin in _ALLOWED_ORIGINS:
        return True
    try:
        u = urlparse(origin)
        host = (u.hostname or '').lower()
        port = str(u.port or '')
        if host in ('localhost', '127.0.0.1') and port in ('3000','3001','3002',''):
            return True
        if host.startswith('192.168.') and port in ('3000','3001','3002',''):
            return True
    except Exception:
        pass
    return False

@app.before_request
def _handle_cors_preflight():
    # If this is a CORS preflight request, return an empty 204 with CORS headers
    if request.method == 'OPTIONS':
        from flask import make_response
        resp = make_response("")
        origin = request.headers.get('Origin')
        allowed = _origin_allowed(origin)
        try:
            print(f"[CORS] Preflight {request.path} origin={origin} allowed={allowed}")
        except Exception:
            pass
        if allowed:
            resp.headers['Access-Control-Allow-Origin'] = origin
            resp.headers['Vary'] = 'Origin'
            resp.headers['Access-Control-Allow-Credentials'] = 'true'
            resp.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type, content-type, Accept, X-Requested-With'
            resp.headers['Access-Control-Expose-Headers'] = 'Authorization'
            resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            resp.headers['Access-Control-Max-Age'] = '600'
        return resp, 204

@app.after_request
def _add_cors_headers(resp):
    try:
        origin = request.headers.get('Origin')
        allowed = _origin_allowed(origin)
        try:
            # Log only for non-OPTIONS to reduce noise
            if request.method != 'OPTIONS':
                print(f"[CORS] {request.method} {request.path} origin={origin} allowed={allowed}")
        except Exception:
            pass
        if allowed:
            resp.headers['Access-Control-Allow-Origin'] = origin
            resp.headers['Vary'] = 'Origin'
            resp.headers['Access-Control-Allow-Credentials'] = 'true'
            resp.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type, content-type, Accept, X-Requested-With'
            resp.headers['Access-Control-Expose-Headers'] = 'Authorization'
            resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            resp.headers['Access-Control-Max-Age'] = '600'
    except Exception:
        pass
    return resp

# --- Security/Auth configuration ---
SECRET_KEY = os.getenv('SECRET_KEY') or os.getenv('AIOPS_SECRET_KEY') or 'dev-secret-change-me'
ACCESS_TOKEN_TTL = int(os.getenv('ACCESS_TOKEN_TTL_SECONDS', '1800'))  # 30m
REFRESH_TOKEN_TTL = int(os.getenv('REFRESH_TOKEN_TTL_SECONDS', '2592000'))  # 30d
TOKEN_ISSUER = 'aiops-bot'
ts = URLSafeTimedSerializer(SECRET_KEY)

DB_PATH = os.getenv('AIOPS_DB_PATH', os.path.join(os.getcwd(), 'aiops_auth.db'))

def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _migrate_db():
    try:
        conn = _db()
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    name TEXT,
                    role TEXT NOT NULL DEFAULT 'employee',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS refresh_tokens (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS invites (
                    token TEXT PRIMARY KEY,
                    email TEXT,
                    role TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT,
                    used_by INTEGER,
                    FOREIGN KEY(used_by) REFERENCES users(id)
                )
                """
            )
    finally:
        try:
            conn.close()
        except Exception:
            pass

def _bootstrap_admin():
    email = os.getenv('ADMIN_EMAIL')
    pwd = os.getenv('ADMIN_PASSWORD')
    name = os.getenv('ADMIN_NAME', 'Admin')
    if not email or not pwd:
        return
    conn = _db()
    try:
        cur = conn.execute('SELECT id FROM users WHERE email = ?', (email,))
        row = cur.fetchone()
        if row:
            return
        pw_hash = generate_password_hash(pwd)
        conn.execute(
            'INSERT INTO users (email, password_hash, name, role, created_at) VALUES (?, ?, ?, ?, ?)',
            (email, pw_hash, name, 'admin', datetime.utcnow().isoformat())
        )
        conn.commit()
        print(f"[AUTH] Bootstrapped admin user {email}")
    except Exception as e:
        print(f"[AUTH] Bootstrap admin error: {e}")
    finally:
        conn.close()

_migrate_db()
_bootstrap_admin()

# --- Helpers to normalize AI output for frontend rendering ---
import re

def _strip_code_fences(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    # Remove leading and trailing triple backtick fences with optional language hint
    text = re.sub(r"^```[a-zA-Z0-9+\-_.]*\s*", "", text.strip())
    text = re.sub(r"```\s*$", "", text)
    return text.strip()

def _strip_outer_html_body(text: str) -> str:
    # Remove outer <html> and <body> wrappers if present, keep inner content
    cleaned = re.sub(r"\s*</?html[^>]*>\s*", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*</?body[^>]*>\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()

def normalize_ai_html(text: str) -> str:
    try:
        s = _strip_code_fences(text)
        s = _strip_outer_html_body(s)
        return s
    except Exception:
        return str(text)

class AIOpsAIChatbot:
    def __init__(self):
        self.load_config()
        self.setup_ai()
        self.system_data = {}
        self.start_system_monitoring()
        # Conversation memory (simple list of turns)
        self.conversation_history = []  # [{'role','content','ts'}]
        self.max_history = 14
        self.base_system_prompt = os.environ.get('AIOPS_SYSTEM_PROMPT', 'You are AIOps Guardian, an expert Site Reliability & Performance assistant.')

    def reset_history(self):
        self.conversation_history = []

    def add_history(self, role: str, content: str):
        try:
            self.conversation_history.append({'role': role, 'content': content, 'ts': datetime.utcnow().isoformat()})
            if len(self.conversation_history) > self.max_history * 2:
                self.conversation_history = self.conversation_history[-self.max_history*2:]
        except Exception as e:
            print(f"History add error: {e}")

    def build_metrics_context(self, system_data: dict) -> str:
        try:
            if not system_data:
                return '{}'
            subset = {
                'timestamp': system_data.get('timestamp'),
                'cpu': {
                    'usage_percent': system_data.get('cpu', {}).get('usage_percent'),
                    'count': system_data.get('cpu', {}).get('count')
                },
                'memory': {
                    'percent': system_data.get('memory', {}).get('percent'),
                    'used_gb': system_data.get('memory', {}).get('used_gb'),
                    'available_gb': system_data.get('memory', {}).get('available_gb')
                },
                'disk': {
                    'percent': system_data.get('disk', {}).get('percent'),
                    'free_gb': system_data.get('disk', {}).get('free_gb')
                },
                'top_processes': [
                    {
                        'name': p.get('name'),
                        'cpu_percent': p.get('cpu_percent'),
                        'memory_percent': p.get('memory_percent')
                    } for p in (system_data.get('top_processes') or [])[:5]
                ],
                'recent_events': system_data.get('recent_events') or []
            }
            return json.dumps(subset, ensure_ascii=False)
        except Exception:
            return '{}'
    
    def load_config(self):
        """Load enterprise configuration for AI services"""
        try:
            config_path = Path("enterprise_config.yaml")
            if config_path.exists():
                with open(config_path, 'r') as f:
                    self.config = yaml.safe_load(f)
                    print("[OK] Enterprise config loaded")
            else:
                print("[WARN] No enterprise config found, using demo mode")
                self.config = {'demo_mode': True}
        except Exception as e:
            print(f"[ERROR] Config error: {e}")
            self.config = {'demo_mode': True}
    
    def setup_ai(self):
        """Initialize Google Gemini AI"""
        try:
            env_key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
            config_key = None
            if not env_key and not self.config.get('demo_mode') and 'google_cloud' in self.config:
                config_key = self.config['google_cloud'].get('api_key')
            api_key = env_key or config_key
            if api_key and genai is not None:
                genai.configure(api_key=api_key)
                model_name = os.environ.get('GEMINI_MODEL_NAME', 'gemini-1.5-pro')
                try:
                    self.ai_model = genai.GenerativeModel(model_name)
                except Exception:
                    self.ai_model = genai.GenerativeModel('gemini-1.5-flash')
                self.enhanced_ai = initialize_enhanced_ai(api_key)
                self.ai_enabled = True
                print(f"[OK] Gemini AI enabled (model={getattr(self.ai_model, 'model_name', model_name)})")
            else:
                print("[INFO] Running in template (demo) mode - no Gemini key present")
                self.ai_enabled = False
                self.enhanced_ai = None
        except Exception as e:
            print(f"[WARN] AI setup warning: {e}")
            self.ai_enabled = False
            self.enhanced_ai = None
    
    def start_system_monitoring(self):
        """Start background system monitoring"""
        # Low-frequency monitor preserved for AI context; primary realtime via sampler below
        def monitor():
            while True:
                try:
                    self.system_data = self.collect_system_data()
                    time.sleep(60)
                except Exception as e:
                    print(f"Monitor error: {e}")
                    time.sleep(60)
        
        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
        print("[OK] System monitoring started")

# (sampler moved below, after class definition)
    
    def collect_system_data(self):
        """Collect comprehensive system information"""
        try:
            # CPU Information
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()
            
            # Memory Information
            memory = psutil.virtual_memory()
            
            # Disk Information
            disk = psutil.disk_usage('/')
            
            # Network Information
            network = psutil.net_io_counters()
            
            # Process Information
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    proc_info = proc.info
                    if proc_info['cpu_percent'] > 1 or proc_info['memory_percent'] > 1:
                        processes.append(proc_info)
                except:
                    continue
            
            # Sort by CPU usage
            processes = sorted(processes, key=lambda x: x['cpu_percent'], reverse=True)[:10]
            
            # Recent System Events (Windows Event Log sample)
            recent_events = self.get_recent_events()
            
            return {
                'timestamp': datetime.now().isoformat(),
                'cpu': {
                    'usage_percent': cpu_percent,
                    'count': cpu_count,
                    'frequency': cpu_freq.current if cpu_freq else None
                },
                'memory': {
                    'total_gb': round(memory.total / (1024**3), 2),
                    'used_gb': round(memory.used / (1024**3), 2),
                    'available_gb': round(memory.available / (1024**3), 2),
                    'percent': memory.percent
                },
                'disk': {
                    'total_gb': round(disk.total / (1024**3), 2),
                    'used_gb': round(disk.used / (1024**3), 2),
                    'free_gb': round(disk.free / (1024**3), 2),
                    'percent': (disk.used / disk.total) * 100
                },
                'network': {
                    'bytes_sent': network.bytes_sent,
                    'bytes_recv': network.bytes_recv,
                    'packets_sent': network.packets_sent,
                    'packets_recv': network.packets_recv
                },
                'top_processes': processes,
                'recent_events': recent_events
            }
        except Exception as e:
            print(f"Error collecting system data: {e}")
            return {'error': str(e), 'timestamp': datetime.now().isoformat()}
    
    def get_recent_events(self):
        """Get recent system events (Windows focus)"""
        try:
            # Simple approach - check running processes for anomalies
            events = []
            
            # Check high CPU processes
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
                try:
                    if proc.info['cpu_percent'] > 50:
                        events.append({
                            'type': 'high_cpu',
                            'message': f"High CPU usage: {proc.info['name']} ({proc.info['cpu_percent']:.1f}%)",
                            'severity': 'warning'
                        })
                except:
                    continue
            
            # Check memory usage
            memory = psutil.virtual_memory()
            if memory.percent > 80:
                events.append({
                    'type': 'high_memory',
                    'message': f"High memory usage: {memory.percent:.1f}%",
                    'severity': 'warning'
                })
            
            # Check disk space
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            if disk_percent > 85:
                events.append({
                    'type': 'low_disk',
                    'message': f"Low disk space: {disk_percent:.1f}% used",
                    'severity': 'error'
                })
            
            return events[:5]  # Return top 5 events
            
        except Exception as e:
            return [{'type': 'error', 'message': f"Event collection error: {e}", 'severity': 'info'}]
    
    def analyze_user_query(self, user_message):
        """Analyze user query and determine intent"""
        message_lower = user_message.lower()
        
        intents = {
            'performance': ['performance', 'slow', 'speed', 'lag', 'fast'],
            'memory': ['memory', 'ram', 'out of memory'],
            'cpu': ['cpu', 'processor', 'usage'],
            'disk': ['disk', 'storage', 'space', 'full'],
            'network': ['network', 'internet', 'connection', 'wifi'],
            'processes': ['process', 'running', 'application', 'program'],
            'errors': ['error', 'problem', 'issue', 'crash', 'bug'],
            'general': ['status', 'health', 'check', 'overview']
        }
        
        detected_intents = []
        for intent, keywords in intents.items():
            if any(keyword in message_lower for keyword in keywords):
                detected_intents.append(intent)
        
        return detected_intents if detected_intents else ['general']
    
    def generate_ai_response(self, user_message, system_data, intents):
        """Generate AI response using Gemini or smart templates"""
        # Intercept small talk / greetings so we don't dump a full system analysis
        if self._is_small_talk(user_message, intents):
            reply = self._small_talk_reply(user_message, system_data)
            # ensure stored in history even if AI disabled
            self.add_history('assistant', reply)
            return reply

        if self.ai_enabled:
            return self.generate_gemini_response(user_message, system_data, intents)
        else:
            return self.generate_template_response(user_message, system_data, intents)

    def _is_small_talk(self, user_message: str, intents) -> bool:
        msg = (user_message or '').strip().lower()
        if not msg:
            return False
        # If user already triggered a concrete intent (not just general) skip
        if intents and any(i for i in intents if i != 'general'):
            return False
        greetings = [
            'hi', 'hey', 'hello', 'hola', 'yo', 'sup', 'good morning', 'good evening', 'good afternoon',
            'how are you', 'how r u', 'how are u', 'whats up', "what's up", 'how is it going', 'how are things'
        ]
        # System keywords that should force analysis even if greeting included
        system_keywords = ['cpu', 'memory', 'disk', 'performance', 'network', 'error', 'status', 'health']
        if any(k in msg for k in system_keywords):
            return False
        matched = [g for g in greetings if g in msg]
        is_st = bool(matched) and len(msg) <= 60
        try:
            print(f"[SMALL_TALK_DEBUG] message='{msg}' matched={matched} is_small_talk={is_st}")
        except Exception:
            pass
        return is_st

    def _small_talk_reply(self, user_message: str, system_data: dict) -> str:
        # Provide a concise friendly greeting plus a teaser of key metrics
        try:
            cpu = system_data.get('cpu', {}).get('usage_percent')
            mem = system_data.get('memory', {}).get('percent')
            disk = system_data.get('disk', {}).get('percent')
            parts = []
            if isinstance(cpu, (int, float)):
                parts.append(f"CPU {cpu:.1f}%")
            if isinstance(mem, (int, float)):
                parts.append(f"Memory {mem:.1f}%")
            if isinstance(disk, (int, float)):
                parts.append(f"Disk {disk:.1f}% used")
            metric_line = ' | '.join(parts) if parts else 'system metrics available'
            return (
                "👋 <strong>Hello!</strong><br>I'm online and monitoring your system. "
                f"Current snapshot: {metric_line}.<br>"
                "Ask me something like: <em>performance analysis</em>, <em>memory issues</em>, "
                "<em>disk space</em>, or just say <em>troubleshoot</em> to begin a deeper check." 
            )
        except Exception:
            return "👋 <strong>Hello!</strong><br>I'm ready. Ask for performance, memory, disk, or say 'overview'."
    
    def generate_gemini_response(self, user_message, system_data, intents):
        """Generate response using Gemini with memory & metrics guardrails"""
        try:
            metrics_json = self.build_metrics_context(system_data or {})
            recent_turns = self.conversation_history[-10:]
            mode = getattr(self, '_last_mode', 'default')
            mode_suffix = ''
            if mode == 'troubleshoot':
                mode_suffix = 'Focus on root cause analysis with hypotheses & verification steps.'
            elif mode == 'optimize':
                mode_suffix = 'Highlight performance optimizations & preventive recommendations.'
            elif mode == 'summary':
                mode_suffix = 'Start with a one-sentence executive summary.'

            system_rules = f"""
{self.base_system_prompt}\n\nSTRICT INSTRUCTIONS:\n1. ONLY cite metrics inside <SYSTEM_METRICS>.\n2. If info not present there, say it's unavailable.\n3. Output lightweight HTML (<strong>, <br>, bullet •).\n4. If applicable sections: <strong>Answer</strong>, Key Metrics, Recommended Actions, Risk Level, Next Step.\n5. Stay focused on user query. {mode_suffix}\n\n<SYSTEM_METRICS>{metrics_json}</SYSTEM_METRICS>\n"""

            if self.enhanced_ai:
                try:
                    response = self.enhanced_ai.generate_intelligent_response(
                        user_message=user_message,
                        system_data=system_data,
                        conversation_history=recent_turns,
                        system_prompt=system_rules,
                        mode=mode
                    )
                    self.add_history('assistant', response)
                    return response
                except Exception as ee:
                    print(f"Enhanced AI fallback: {ee}")

            history_text = ''
            for h in recent_turns:
                role_tag = 'User' if h['role'] == 'user' else 'Assistant'
                history_text += f"[{role_tag}] {h['content']}\n"
            full_prompt = f"""{system_rules}\nConversation History:\n{history_text}\n[User] {user_message}\nProvide answer now:"""
            try:
                if hasattr(self.ai_model, 'start_chat'):
                    gem_hist = []
                    for h in recent_turns:
                        role = 'user' if h['role'] == 'user' else 'model'
                        gem_hist.append({'role': role, 'parts': [h['content'][:8000]]})
                    chat = self.ai_model.start_chat(history=gem_hist)
                    gem_resp = chat.send_message(full_prompt)
                    text = getattr(gem_resp, 'text', None) or getattr(gem_resp, 'candidates', [{}])[0].get('content', '')
                else:
                    gem_resp = self.ai_model.generate_content(full_prompt)
                    text = getattr(gem_resp, 'text', str(gem_resp))
            except Exception as ee:
                print(f"Gemini primary call failed: {ee}")
                raise
            self.add_history('assistant', text)
            return text
        except Exception as e:
            print(f"Enhanced Gemini AI error: {e}")
            return self.generate_template_response(user_message, system_data, intents)
    
    def generate_template_response(self, user_message, system_data, intents):
        """Generate enhanced smart template response based on actual system data"""
        
        primary_intent = intents[0] if intents else 'general'
        message_lower = user_message.lower()
        
        # Enhanced intent detection for specific questions
        if any(word in message_lower for word in ['attention', 'problem', 'issue', 'wrong', 'needs', 'fix']):
            return self._analyze_problematic_areas(system_data, user_message)
        elif any(word in message_lower for word in ['performance', 'slow', 'speed', 'lag', 'fast']):
            return self._analyze_performance_issues(system_data, user_message)
        elif any(word in message_lower for word in ['memory', 'ram', 'out of memory']):
            return self._analyze_memory_detailed(system_data, user_message)
        elif any(word in message_lower for word in ['cpu', 'processor', 'usage']):
            return self._analyze_cpu_detailed(system_data, user_message)
        elif any(word in message_lower for word in ['disk', 'storage', 'space', 'full']):
            return self._analyze_disk_detailed(system_data, user_message)
        elif any(word in message_lower for word in ['network', 'internet', 'connection', 'wifi']):
            return self._analyze_network_detailed(system_data, user_message)
        elif any(word in message_lower for word in ['error', 'crash', 'bug']):
            return self._analyze_errors_detailed(system_data, user_message)
        else:
            return self._analyze_system_overview_intelligent(system_data, user_message)
    
    def _analyze_problematic_areas(self, system_data, user_message):
        """Analyze and identify specific problematic areas"""
        issues = []
        recommendations = []
        
        cpu_usage = system_data.get('cpu', {}).get('usage_percent', 0)
        memory_usage = system_data.get('memory', {}).get('percent', 0)
        disk_usage = system_data.get('disk', {}).get('percent', 0)
        events = system_data.get('recent_events', [])
        
        # Identify actual problems with specific thresholds
        if memory_usage > 85:
            issues.append(f"🔴 <strong>Critical Memory Usage:</strong> {memory_usage:.1f}% used")
            recommendations.append("Immediately close unnecessary applications or restart your computer")
        elif memory_usage > 75:
            issues.append(f"⚠️ <strong>High Memory Usage:</strong> {memory_usage:.1f}% used")
            recommendations.append("Close some applications to free up memory")
        
        if cpu_usage > 80:
            issues.append(f"🔴 <strong>High CPU Load:</strong> {cpu_usage:.1f}% usage")
            recommendations.append("Identify and close CPU-intensive processes")
        
        if disk_usage > 90:
            issues.append(f"🔴 <strong>Critical Disk Space:</strong> {disk_usage:.1f}% full")
            recommendations.append("Delete unnecessary files immediately")
        elif disk_usage > 85:
            issues.append(f"⚠️ <strong>Low Disk Space:</strong> {disk_usage:.1f}% full")
            recommendations.append("Clean up temporary files and old downloads")
        
        # Check for system events
        if events:
            critical_events = [e for e in events if e.get('severity') == 'error']
            if critical_events:
                issues.append(f"🚨 <strong>System Errors:</strong> {len(critical_events)} critical issues detected")
        
        if not issues:
            return f"""✅ <strong>Great News!</strong><br><br>
I've thoroughly analyzed your system and found <strong>no areas requiring immediate attention</strong>.<br><br>
<strong>Current Status:</strong><br>
• CPU Usage: {cpu_usage:.1f}% (Healthy)<br>
• Memory Usage: {memory_usage:.1f}% (Normal)<br>
• Disk Space: {disk_usage:.1f}% used (Adequate)<br><br>
Your system is running optimally! 🎉"""
        
        response = f"🔍 <strong>System Analysis - Areas Needing Attention:</strong><br><br>"
        
        for i, issue in enumerate(issues, 1):
            response += f"{i}. {issue}<br>"
        
        response += f"<br><strong>🛠️ Recommended Actions:</strong><br>"
        for i, rec in enumerate(recommendations, 1):
            response += f"{i}. {rec}<br>"
        
        if len(issues) > 1:
            response += f"<br><strong>Priority:</strong> Address the memory usage first as it has the biggest impact on performance."
        
        return response
    
    def _analyze_performance_issues(self, system_data, user_message):
        """Detailed performance analysis"""
        cpu_usage = system_data.get('cpu', {}).get('usage_percent', 0)
        memory_usage = system_data.get('memory', {}).get('percent', 0)
        disk_usage = system_data.get('disk', {}).get('percent', 0)
        top_processes = system_data.get('top_processes', [])[:3]
        
        # Calculate performance score
        cpu_score = max(0, 100 - cpu_usage)
        memory_score = max(0, 100 - memory_usage)
        disk_score = max(0, 100 - disk_usage)
        overall_score = int((cpu_score + memory_score + disk_score) / 3)
        
        response = f"⚡ <strong>Performance Analysis Complete:</strong><br><br>"
        response += f"📊 <strong>Overall Performance Score: {overall_score}/100</strong><br><br>"
        
        # Identify bottlenecks
        bottlenecks = []
        if memory_usage > 75:
            bottlenecks.append(f"Memory ({memory_usage:.1f}% used)")
        if cpu_usage > 70:
            bottlenecks.append(f"CPU ({cpu_usage:.1f}% used)")
        if disk_usage > 85:
            bottlenecks.append(f"Storage ({disk_usage:.1f}% full)")
        
        if bottlenecks:
            response += f"🚨 <strong>Performance Bottlenecks:</strong><br>"
            for bottleneck in bottlenecks:
                response += f"• {bottleneck}<br>"
            response += "<br>"
        
        # Top resource consumers
        if top_processes:
            response += f"🔝 <strong>Top Resource Consumers:</strong><br>"
            for proc in top_processes:
                response += f"• {proc.get('name', 'Unknown')}: CPU {proc.get('cpu_percent', 0):.1f}%, RAM {proc.get('memory_percent', 0):.1f}%<br>"
            response += "<br>"
        
        # Specific recommendations
        response += f"� <strong>Performance Recommendations:</strong><br>"
        if memory_usage > 75:
            response += f"1. <strong>Memory Optimization:</strong> Close browser tabs and unused applications<br>"
        if cpu_usage > 70:
            response += f"2. <strong>CPU Relief:</strong> End high-CPU processes or restart applications<br>"
        if disk_usage > 85:
            response += f"3. <strong>Storage Cleanup:</strong> Delete temporary files and clear downloads folder<br>"
        
        if overall_score > 80:
            response += f"✅ <strong>Overall:</strong> Your system performance is good!"
        elif overall_score > 60:
            response += f"⚠️ <strong>Overall:</strong> Performance is acceptable but could be improved."
        else:
            response += f"🔴 <strong>Overall:</strong> System performance needs immediate attention."
        
        return response
    
    def _analyze_memory_detailed(self, system_data, user_message):
        """Detailed memory analysis"""
        memory = system_data.get('memory', {})
        memory_usage = memory.get('percent', 0)
        memory_used = memory.get('used_gb', 0)
        memory_total = memory.get('total_gb', 0)
        memory_available = memory.get('available_gb', 0)
        
        response = f"🧠 <strong>Detailed Memory Analysis:</strong><br><br>"
        response += f"📊 <strong>Memory Statistics:</strong><br>"
        response += f"• Total RAM: {memory_total:.1f} GB<br>"
        response += f"• Used: {memory_used:.1f} GB ({memory_usage:.1f}%)<br>"
        response += f"• Available: {memory_available:.1f} GB<br><br>"
        
        # Memory status assessment
        if memory_usage > 90:
            status = "🔴 Critical"
            advice = "Immediate action required - restart applications or reboot system"
        elif memory_usage > 80:
            status = "⚠️ High"
            advice = "Close unnecessary applications to free up memory"
        elif memory_usage > 65:
            status = "🟡 Elevated"
            advice = "Consider closing some browser tabs or unused programs"
        else:
            status = "✅ Normal"
            advice = "Memory usage is healthy"
        
        response += f"🎯 <strong>Memory Status:</strong> {status}<br>"
        response += f"💡 <strong>Recommendation:</strong> {advice}<br><br>"
        
        # Memory-intensive processes
        top_processes = system_data.get('top_processes', [])
        memory_hogs = [p for p in top_processes if p.get('memory_percent', 0) > 3][:3]
        
        if memory_hogs:
            response += f"🔝 <strong>Memory-Intensive Processes:</strong><br>"
            for proc in memory_hogs:
                response += f"• {proc.get('name', 'Unknown')}: {proc.get('memory_percent', 0):.1f}% RAM<br>"
        
        return response

    def _analyze_cpu_detailed(self, system_data, user_message):
        """Detailed CPU analysis"""
        cpu = system_data.get('cpu', {})
        cpu_usage = float(cpu.get('usage_percent') or 0)
        cores = system_data.get('cpu', {}).get('count') or psutil.cpu_count()
        freq = system_data.get('cpu', {}).get('frequency') or (psutil.cpu_freq().current if psutil.cpu_freq() else None)
        top = sorted(system_data.get('top_processes', []), key=lambda p: p.get('cpu_percent', 0), reverse=True)[:5]

        status = '✅ Normal'
        advice = 'CPU usage is within normal range.'
        if cpu_usage > 90:
            status = '🔴 Critical'
            advice = 'Close CPU-heavy apps or consider restarting problematic processes.'
        elif cpu_usage > 75:
            status = '⚠️ High'
            advice = 'Identify high-CPU processes and close unnecessary ones.'

        resp = f"🧮 <strong>CPU Analysis</strong><br><br>"
        resp += f"• Usage: {cpu_usage:.1f}%<br>"
        resp += f"• Cores (logical): {cores}<br>"
        if freq:
            resp += f"• Frequency: {float(freq):.0f} MHz<br>"
        resp += f"<br>🎯 <strong>Status:</strong> {status}<br>💡 <strong>Recommendation:</strong> {advice}<br><br>"
        if top:
            resp += "🔝 <strong>Top CPU Processes:</strong><br>"
            for p in top:
                resp += f"• {p.get('name','?')} — {p.get('cpu_percent',0):.1f}% CPU<br>"
        return resp

    def _analyze_disk_detailed(self, system_data, user_message):
        """Detailed Disk/Storage analysis"""
        disk = system_data.get('disk', {})
        used_pct = float(disk.get('percent') or 0)
        total = disk.get('total_gb')
        free = disk.get('free_gb')
        status = '✅ Adequate'
        advice = 'Disk usage is healthy.'
        if used_pct > 95:
            status = '🔴 Critical'
            advice = 'Free up space immediately: clear temp files, large downloads, or uninstall unused apps.'
        elif used_pct > 85:
            status = '⚠️ Low Space'
            advice = 'Clean temporary files and move large files to external storage.'
        resp = f"💾 <strong>Storage Analysis</strong><br><br>"
        if total is not None and free is not None:
            resp += f"• Total: {total:.1f} GB<br>• Free: {free:.1f} GB<br>"
        resp += f"• Used: {used_pct:.1f}%<br><br>"
        resp += f"🎯 <strong>Status:</strong> {status}<br>💡 <strong>Recommendation:</strong> {advice}<br>"
        return resp

    def _analyze_network_detailed(self, system_data, user_message):
        """Detailed Network analysis"""
        net = system_data.get('network', {})
        recv = int(net.get('bytes_recv') or 0)
        sent = int(net.get('bytes_sent') or 0)
        pkts_in = int(net.get('packets_recv') or 0)
        pkts_out = int(net.get('packets_sent') or 0)
        resp = f"🌐 <strong>Network Overview</strong><br><br>"
        resp += f"• Bytes Received: {recv:,}<br>• Bytes Sent: {sent:,}<br>"
        resp += f"• Packets In: {pkts_in:,} • Packets Out: {pkts_out:,}<br><br>"
        resp += "💡 If you experience slowness: check Wi‑Fi signal, restart router, or limit background downloads."
        return resp

    def _analyze_errors_detailed(self, system_data, user_message):
        """Highlight recent error-like events"""
        events = system_data.get('recent_events', [])
        critical = [e for e in events if e.get('severity') in ('error','critical')]
        warnings = [e for e in events if e.get('severity') == 'warning']
        resp = "🚨 <strong>Errors & Warnings</strong><br><br>"
        if not (critical or warnings):
            resp += "No recent critical issues detected. ✅"
            return resp
        if critical:
            resp += "<strong>Critical:</strong><br>"
            for e in critical:
                resp += f"• {e.get('message','')}<br>"
            resp += "<br>"
        if warnings:
            resp += "<strong>Warnings:</strong><br>"
            for e in warnings[:5]:
                resp += f"• {e.get('message','')}<br>"
        return resp
    
    def _analyze_system_overview_intelligent(self, system_data, user_message):
        """Intelligent system overview based on actual conditions"""
        cpu_usage = system_data.get('cpu', {}).get('usage_percent', 0)
        memory_usage = system_data.get('memory', {}).get('percent', 0)
        disk_usage = system_data.get('disk', {}).get('percent', 0)
        
        # Count actual issues
        issues_count = 0
        if memory_usage > 80: issues_count += 1
        if cpu_usage > 75: issues_count += 1
        if disk_usage > 85: issues_count += 1
        
        response = f"🤖 <strong>Intelligent System Overview:</strong><br><br>"
        
        if issues_count == 0:
            response += f"✅ <strong>System Status: Excellent</strong><br><br>"
            response += f"All major components are operating within optimal ranges:<br>"
            response += f"• CPU: {cpu_usage:.1f}% (Efficient)<br>"
            response += f"• Memory: {memory_usage:.1f}% (Healthy)<br>"
            response += f"• Storage: {disk_usage:.1f}% used (Adequate)<br><br>"
            response += f"🎉 Your system is running smoothly! No immediate action needed."
        else:
            response += f"⚠️ <strong>System Status: {issues_count} area(s) need attention</strong><br><br>"
            
            # Show status with context
            response += f"📊 <strong>Component Analysis:</strong><br>"
            response += f"• CPU: {cpu_usage:.1f}% {'⚠️ (High)' if cpu_usage > 75 else '✅ (Normal)'}<br>"
            response += f"• Memory: {memory_usage:.1f}% {'⚠️ (High)' if memory_usage > 80 else '✅ (Normal)'}<br>"
            response += f"• Storage: {disk_usage:.1f}% {'⚠️ (Low Space)' if disk_usage > 85 else '✅ (Adequate)'}<br><br>"
            
            response += f"💡 <strong>Next Steps:</strong> Ask me 'what needs attention?' for detailed troubleshooting."
        
        return response

# Initialize the chatbot
chatbot = AIOpsAIChatbot()

# --- High-frequency sampler for snapshot/SSE (module-level) ---
_SAMPLER_LOCK = threading.Lock()
_LAST_SNAPSHOT = None  # type: ignore
_SAMPLER_INTERVAL = float(os.getenv('SAMPLER_INTERVAL_SECONDS', '1.5'))

def _take_snapshot() -> dict:
    try:
        cpu_pct = psutil.cpu_percent(interval=0.0)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        net = psutil.net_io_counters()
        procs = []
        for p in psutil.process_iter(['pid','name','cpu_percent','memory_percent']):
            try:
                info = p.info
                if (info.get('cpu_percent') or 0) > 0.5 or (info.get('memory_percent') or 0) > 0.5:
                    procs.append({
                        'pid': info.get('pid'),
                        'name': info.get('name'),
                        'cpu_percent': float(info.get('cpu_percent') or 0.0),
                        'memory_percent': float(info.get('memory_percent') or 0.0)
                    })
            except Exception:
                continue
        procs.sort(key=lambda x: x.get('cpu_percent', 0), reverse=True)
        procs = procs[:20]
        status = 'healthy'
        if cpu_pct > 90 or mem.percent > 90:
            status = 'critical'
        elif cpu_pct > 75 or mem.percent > 80:
            status = 'warning'
        return {
            'timestamp': datetime.utcnow().isoformat(),
            'cpu': round(cpu_pct, 2),
            'memory': round(mem.percent, 2),
            'disk': round((disk.used / disk.total) * 100, 2),
            'network_in': net.bytes_recv,
            'network_out': net.bytes_sent,
            'status': status,
            'top_processes': procs
        }
    except Exception as e:
        return {'error': str(e), 'timestamp': datetime.utcnow().isoformat()}

def _sampler_loop():
    global _LAST_SNAPSHOT
    while True:
        snap = _take_snapshot()
        with _SAMPLER_LOCK:
            _LAST_SNAPSHOT = snap
        time.sleep(max(0.3, _SAMPLER_INTERVAL))

_sampler_thread = threading.Thread(target=_sampler_loop, daemon=True)
_sampler_thread.start()
print('[OK] Realtime sampler started')

# Optional privileged mode for performing real system actions
# Enabled by environment variable ALLOW_SYSTEM_ACTIONS or by passing --allow-actions CLI flag
ALLOW_SYSTEM_ACTIONS = str(os.getenv('ALLOW_SYSTEM_ACTIONS', 'true')).lower() in ('1', 'true', 'yes')
if '--allow-actions' in sys.argv:
    ALLOW_SYSTEM_ACTIONS = True

# -----------------------------
# Background job management (for AI Actions)
# -----------------------------
JOBS_LOCK = threading.Lock()
JOBS = {}  # job_id -> {type, status, progress, started_at, updated_at, result, error, logs: [..], artifact}
EXPORTS_DIR = Path("exports")
try:
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

def _new_job(job_type: str, params: dict | None = None) -> str:
    job_id = secrets.token_hex(8)
    now = datetime.now().isoformat()
    with JOBS_LOCK:
        JOBS[job_id] = {
            'id': job_id,
            'type': job_type,
            'params': params or {},
            'status': 'queued',
            'progress': 0,
            'started_at': now,
            'updated_at': now,
            'logs': [],
            'artifact': None,
            'result': None,
            'error': None,
        }
    return job_id

def _job_log(job_id: str, msg: str):
    with JOBS_LOCK:
        j = JOBS.get(job_id)
        if not j:
            return
        j['logs'].append(f"{datetime.now().strftime('%H:%M:%S')} | {msg}")
        j['updated_at'] = datetime.now().isoformat()

def _job_update(job_id: str, **updates):
    with JOBS_LOCK:
        j = JOBS.get(job_id)
        if not j:
            return
        j.update(updates)
        j['updated_at'] = datetime.now().isoformat()

def _run_in_thread(job_id: str, target):
    def runner():
        try:
            _job_update(job_id, status='running', progress=1)
            target(job_id)
            if JOBS.get(job_id, {}).get('status') not in ('failed', 'succeeded'):
                _job_update(job_id, status='succeeded', progress=100)
        except Exception as e:
            _job_log(job_id, f"Error: {e}")
            _job_update(job_id, status='failed', error=str(e))
    t = threading.Thread(target=runner, daemon=True)
    t.start()
    return t

def _simulate_steps(job_id: str, steps: list[tuple[str, float]]):
    total = len(steps)
    for idx, (label, delay) in enumerate(steps, start=1):
        _job_log(job_id, label)
        # spread progress evenly
        prog = int(idx / total * 98)  # leave tail for finalization
        _job_update(job_id, progress=prog)
        try:
            time.sleep(max(0.05, delay))
        except Exception:
            pass

def _retrain_job(job_id: str):
    steps = [
        ("Loading training data", 0.6),
        ("Preprocessing & feature engineering", 0.7),
        ("Initializing model", 0.4),
        ("Training epoch 1/3", 0.6),
        ("Training epoch 2/3", 0.6),
        ("Training epoch 3/3", 0.6),
        ("Evaluating on validation set", 0.5),
        ("Publishing new model", 0.4),
    ]
    _simulate_steps(job_id, steps)
    _job_update(job_id, result={'message': 'Retraining complete', 'metrics': {'accuracy': 0.92, 'f1': 0.90}})

def _diagnostics_job(job_id: str):
    # Collect a few snapshots
    snapshots = []
    for i in range(5):
        try:
            snap = {
                'cpu': psutil.cpu_percent(interval=0.1),
                'memory': psutil.virtual_memory().percent,
                'disk': (psutil.disk_usage('/').used / psutil.disk_usage('/').total) * 100,
                'ts': datetime.now().isoformat()
            }
            snapshots.append(snap)
            _job_log(job_id, f"Snapshot {i+1}/5: CPU {snap['cpu']:.1f}% MEM {snap['memory']:.1f}% DISK {snap['disk']:.1f}%")
            _job_update(job_id, progress=int(((i+1)/5)*98))
        except Exception as e:
            _job_log(job_id, f"Snapshot error: {e}")
    _job_update(job_id, result={'summary': 'Diagnostics complete', 'snapshots': snapshots})

def _export_job(job_id: str):
    # Export current insights/system snapshot to a JSON file
    data = {
        'systemData': chatbot.system_data,
        'generated_at': datetime.now().isoformat(),
        'host': py_platform.node(),
    }
    _job_log(job_id, "Preparing insights payload")
    _job_update(job_id, progress=20)
    out_path = EXPORTS_DIR / f"insights_{job_id}.json"
    try:
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        _job_log(job_id, f"Wrote {out_path}")
        _job_update(job_id, progress=95, artifact=str(out_path))
    except Exception as e:
        _job_log(job_id, f"Export error: {e}")
        _job_update(job_id, status='failed', error=str(e))
        return
    _job_update(job_id, result={'artifact': str(out_path)})

# --- Safe cleanup helpers (Windows-friendly) ---
def _dir_size_bytes(path: str) -> int:
    total = 0
    for root, dirs, files in os.walk(path, topdown=False):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total += os.path.getsize(fp)
            except Exception:
                pass
    return total

def _safe_clean_dir(path: str):
    """Attempt to remove files and directories under path without raising.
    Returns (freed_bytes, removed_items)."""
    freed = 0
    removed = 0
    if not os.path.isdir(path):
        return 0, 0
    for entry in os.listdir(path):
        fp = os.path.join(path, entry)
        try:
            if os.path.isfile(fp) or os.path.islink(fp):
                try:
                    size = os.path.getsize(fp)
                except Exception:
                    size = 0
                try:
                    os.remove(fp)
                    freed += size
                    removed += 1
                except Exception:
                    pass
            elif os.path.isdir(fp):
                try:
                    # Measure size before removal for a better freed estimate
                    size_before = _dir_size_bytes(fp)
                except Exception:
                    size_before = 0
                try:
                    shutil.rmtree(fp, ignore_errors=True)
                    # If still exists, skip counting; otherwise count estimated size
                    if not os.path.exists(fp):
                        freed += size_before
                        removed += 1
                except Exception:
                    pass
        except Exception:
            continue
    return freed, removed

def _clear_recycle_bin_windows():
    """Try to clear Recycle Bin for current user using PowerShell. Non-fatal if it fails."""
    try:
        subprocess.run([
            'powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command',
            'Clear-RecycleBin -Force -ErrorAction SilentlyContinue'
        ], check=False, capture_output=True)
    except Exception:
        pass

# --- Authentication & Rate limiting ---
LOGIN_RATE_LIMIT_MAX = int(os.getenv('LOGIN_RATE_LIMIT_MAX', '10'))  # 10 attempts
LOGIN_RATE_LIMIT_WINDOW = int(os.getenv('LOGIN_RATE_LIMIT_WINDOW', '600'))  # 10 minutes
_LOGIN_ATTEMPTS = {}  # ip -> [epoch_seconds,...]

def _issue_access_token(user: dict) -> str:
    payload = {
        'sub': str(user['id']),
        'email': user['email'],
        'role': user.get('role', 'employee'),
        'iss': TOKEN_ISSUER,
        'type': 'access'
    }
    return ts.dumps(payload)

def _issue_refresh_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    exp = now + timedelta(seconds=REFRESH_TOKEN_TTL)
    conn = _db()
    try:
        with conn:
            conn.execute(
                'INSERT OR REPLACE INTO refresh_tokens (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)',
                (token, user_id, now.isoformat(), exp.isoformat())
            )
    finally:
        conn.close()
    return token

def _verify_access_token(token: str):
    try:
        data = ts.loads(token, max_age=ACCESS_TOKEN_TTL)
        if data.get('type') != 'access' or data.get('iss') != TOKEN_ISSUER:
            return None
        return data
    except (BadSignature, SignatureExpired):
        return None
    except Exception:
        return None

def _require_user_from_token():
    auth = request.headers.get('Authorization', '')
    token = auth[7:] if auth.startswith('Bearer ') else None
    if not token:
        return None
    data = _verify_access_token(token)
    if not data:
        return None
    conn = _db()
    try:
        cur = conn.execute('SELECT id, email, name, role FROM users WHERE id = ?', (int(data['sub']),))
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        conn.close()

def auth_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = _require_user_from_token()
        if not user:
            return jsonify({'error': 'Unauthorized'}), 401
        request.user = user  # type: ignore[attr-defined]
        return fn(*args, **kwargs)
    return wrapper

def role_required(role: str):
    def deco(fn):
        from functools import wraps
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = _require_user_from_token()
            if not user:
                return jsonify({'error': 'Unauthorized'}), 401
            if str(user.get('role')) != role:
                return jsonify({'error': 'forbidden', 'message': 'insufficient_role'}), 403
            request.user = user  # type: ignore[attr-defined]
            return fn(*args, **kwargs)
        return wrapper
    return deco

@app.route('/')
def index():
        """Serve the chatbot interface"""
        try:
                with open('aiops_chatbot.html', 'r', encoding='utf-8') as f:
                        return f.read()
        except Exception:
                # Minimal fallback UI if the HTML file isn't present
                return (
                        """
                        <!doctype html>
                        <html>
                            <head>
                                <meta charset="utf-8" />
                                <title>AIOps Bot Backend</title>
                                <style>
                                    body { font-family: system-ui, Arial, sans-serif; margin: 2rem; }
                                    code { background: #f4f4f4; padding: 0.2rem 0.4rem; border-radius: 4px; }
                                </style>
                            </head>
                            <body>
                                <h1>🚀 AIOps Bot Backend</h1>
                                <p>This is the backend service. Try the JSON endpoints:</p>
                                <ul>
                                    <li><a href="/health">/health</a></li>
                                    <li><a href="/system-health">/system-health</a></li>
                                    <li><a href="/processes">/processes</a></li>
                                    <li><a href="/system-info">/system-info</a></li>
                                </ul>
                                <p>To enable real system actions (cleanup, process termination), set <code>ALLOW_SYSTEM_ACTIONS=true</code> and restart.</p>
                            </body>
                        </html>
                        """,
                        200,
                        {"Content-Type": "text/html; charset=utf-8"}
                )

@app.route('/api/chat', methods=['POST'])
def chat():
    """Handle chat messages"""
    try:
        data = request.get_json()
        user_message = data.get('message', '')
        mode = (data.get('mode') or 'default').lower().strip()
        clear_history = bool(data.get('clear_history'))
        
        if not user_message:
            return jsonify({'error': 'No message provided'}), 400
        if clear_history:
            chatbot.reset_history()
        chatbot._last_mode = mode
        chatbot.add_history('user', user_message)

        # Route-level small talk interception (belt & suspenders) to ensure greetings don't trigger full analysis
        try:
            raw = user_message.strip().lower()
            st_flag = chatbot._is_small_talk(user_message, [])
            print(f"[SMALL_TALK_DEBUG] route=/api/chat detected={st_flag} raw='{raw}'")
            if st_flag:
                reply = chatbot._small_talk_reply(user_message, chatbot.system_data)
                chatbot.add_history('assistant', reply)
                return jsonify({
                    'response': normalize_ai_html(reply),
                    'intents': ['small_talk'],
                    'systemData': chatbot.system_data,
                    'timestamp': datetime.now().isoformat(),
                    'mode': mode,
                    'history_size': len(chatbot.conversation_history),
                    'small_talk': True,
                    'backend_small_talk': True
                })
        except Exception as e:
            print(f"[SMALL_TALK_DEBUG] interception error: {e}")
        
        # Analyze user intent
        intents = chatbot.analyze_user_query(user_message)
        
        # Get current system data
        system_data = chatbot.system_data
        
        # Generate AI response
        ai_response = chatbot.generate_ai_response(user_message, system_data, intents)
        ai_response = normalize_ai_html(ai_response)
        
        # Post-generation fallback: if it should have been small talk but produced a long analysis, replace.
        if chatbot._is_small_talk(user_message, []) and not ai_response.startswith("👋"):
            print("[SMALL_TALK_DEBUG] post-generation fallback applied")
            fallback_reply = chatbot._small_talk_reply(user_message, system_data)
            ai_response = normalize_ai_html(fallback_reply)
        return jsonify({
            'response': ai_response,
            'intents': intents,
            'systemData': system_data,
            'timestamp': datetime.now().isoformat(),
            'mode': mode,
            'history_size': len(chatbot.conversation_history),
            'small_talk': ai_response.startswith("👋"),
            'backend_small_talk': ai_response.startswith("👋")
        })
        
    except Exception as e:
        print(f"Chat error: {e}")
        return jsonify({
            'response': f"🤖 I encountered an error while analyzing your request: {str(e)}<br><br>Please try asking something else, like 'check system status' or 'analyze performance'.",
            'error': str(e)
        }), 500

# Mirror route without /api prefix for compatibility with frontend/Node proxy
@app.route('/chat', methods=['POST'])
def chat_plain():
    return chat()

# SSE streaming endpoint: streams the generated response token-by-token
@app.route('/chat/stream', methods=['POST'])
def chat_stream():
    try:
        data = request.get_json(silent=True) or {}
        user_message = data.get('message', '')
        mode = (data.get('mode') or 'default').lower().strip()
        if data.get('clear_history'):
            chatbot.reset_history()
        chatbot._last_mode = mode
        if user_message:
            chatbot.add_history('user', user_message)
        if not user_message:
            return jsonify({'error': 'No message provided'}), 400

        # Early small-talk streaming shortcut: send single chunk then done
        try:
            if chatbot._is_small_talk(user_message, []):
                reply = normalize_ai_html(chatbot._small_talk_reply(user_message, chatbot.system_data))
                chatbot.add_history('assistant', reply)
                def gen_small():
                    yield f"data: {reply}\n\n"
                    yield "event: done\n"
                    yield "data: [DONE]\n\n"
                headers = {
                    'Cache-Control': 'no-cache',
                    'Content-Type': 'text/event-stream',
                    'Connection': 'keep-alive',
                    'X-Accel-Buffering': 'no'
                }
                return Response(gen_small(), headers=headers)
        except Exception as e:
            print(f"Small talk stream interception error: {e}")

        # Analyze and generate full response first (can be swapped to a true model stream later)
        intents = chatbot.analyze_user_query(user_message)
        system_data = chatbot.system_data
        ai_response = chatbot.generate_ai_response(user_message, system_data, intents)
        ai_response = normalize_ai_html(ai_response)
        if not chatbot.ai_enabled:
            chatbot.add_history('assistant', ai_response)

        def generate():
            # Stream response in chunks via SSE
            try:
                text = str(ai_response)
                # Split by words but keep whitespace
                import re
                parts = re.split(r'(\s+)', text)
                last_beat = time.time()
                for part in parts:
                    if not part:
                        continue
                    payload = part
                    yield f"data: {payload}\n\n"
                    # Tiny delay to avoid flooding (optional)
                    time.sleep(0.01)
                    # Heartbeat every ~10s to keep proxies alive
                    if time.time() - last_beat > 10:
                        yield "event: heartbeat\n"
                        yield "data: ping\n\n"
                        last_beat = time.time()
                # Signal completion
                yield "event: done\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                yield f"data: {{\"error\": \"{str(e)}\"}}\n\n"

        headers = {
            'Cache-Control': 'no-cache',
            'Content-Type': 'text/event-stream',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
        return Response(generate(), headers=headers)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---- Auth endpoints (real) ----
def _get_body():
    data = request.get_json(silent=True)
    if isinstance(data, dict):
        return data
    return request.form.to_dict() if request.form else {}

@app.route('/auth/register', methods=['POST'])
def auth_register():
    # Guard: allow registration only if explicitly enabled via env or no users exist
    open_registration = str(os.getenv('OPEN_REGISTRATION', 'true')).lower() in ('1','true','yes')
    body = _get_body()
    email = str(body.get('email') or '').strip().lower()
    password = str(body.get('password') or '').strip()
    name = str(body.get('name') or '').strip() or email.split('@')[0].title()
    role = str(body.get('role') or 'employee').strip().lower()
    if not email or not password:
        return jsonify({'error': 'email_and_password_required'}), 400
    conn = _db()
    try:
        cur = conn.execute('SELECT COUNT(1) AS c FROM users')
        total = int(cur.fetchone()['c'])
        if total > 0 and not open_registration:
            return jsonify({'error': 'registration_closed'}), 403
        pw_hash = generate_password_hash(password)
        with conn:
            conn.execute('INSERT INTO users (email, password_hash, name, role, created_at) VALUES (?, ?, ?, ?, ?)',
                         (email, pw_hash, name, ('admin' if total == 0 and role != 'employee' else role), datetime.utcnow().isoformat()))
        return jsonify({'ok': True}), 201
    except sqlite3.IntegrityError:
        return jsonify({'error': 'email_exists'}), 409
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/auth/invites', methods=['POST'])
@auth_required
@role_required('admin')
def create_invite():
    try:
        body = _get_body()
        role = str(body.get('role') or 'employee').strip().lower()
        email = str(body.get('email') or '').strip().lower() or None
        ttl = int(body.get('ttl_seconds') or 7*24*3600)  # default 7 days
        token = secrets.token_urlsafe(24)
        now = datetime.utcnow()
        exp = now + timedelta(seconds=ttl)
        conn = _db()
        try:
            with conn:
                conn.execute(
                    'INSERT INTO invites (token, email, role, created_at, expires_at) VALUES (?, ?, ?, ?, ?)',
                    (token, email, (role if role in ('admin','employee') else 'employee'), now.isoformat(), exp.isoformat())
                )
        finally:
            conn.close()
        return jsonify({'token': token, 'role': role, 'email': email, 'expires_at': exp.isoformat()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/auth/redeem-invite', methods=['POST'])
def redeem_invite():
    try:
        body = _get_body()
        token = str(body.get('token') or '')
        email = str(body.get('email') or '').strip().lower()
        password = str(body.get('password') or '').strip()
        name = str(body.get('name') or '').strip() or (email.split('@')[0].title() if email else '')
        if not token or not email or not password:
            return jsonify({'error': 'token_email_password_required'}), 400
        conn = _db()
        try:
            cur = conn.execute('SELECT token, role, expires_at, used_at FROM invites WHERE token = ?', (token,))
            inv = cur.fetchone()
            if not inv:
                return jsonify({'error': 'invalid_invite'}), 400
            if inv['used_at']:
                return jsonify({'error': 'invite_used'}), 400
            if datetime.fromisoformat(inv['expires_at']) < datetime.utcnow():
                return jsonify({'error': 'invite_expired'}), 400
            # create user
            pw_hash = generate_password_hash(password)
            try:
                with conn:
                    conn.execute('INSERT INTO users (email, password_hash, name, role, created_at) VALUES (?, ?, ?, ?, ?)',
                                 (email, pw_hash, name, inv['role'], datetime.utcnow().isoformat()))
            except sqlite3.IntegrityError:
                return jsonify({'error': 'email_exists'}), 409
            cur2 = conn.execute('SELECT id, email, name, role FROM users WHERE email = ?', (email,))
            u = cur2.fetchone()
            with conn:
                conn.execute('UPDATE invites SET used_at = ?, used_by = ? WHERE token = ?', (datetime.utcnow().isoformat(), u['id'], token))
            user = {'id': u['id'], 'email': u['email'], 'name': u['name'], 'role': u['role']}
            access = _issue_access_token(user)
            rtok = _issue_refresh_token(u['id'])
            return jsonify({'token': access, 'refresh_token': rtok, 'user': user})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/auth/login', methods=['POST'])
def auth_login():
    body = _get_body()
    email = str(body.get('email') or '').strip().lower()
    password = str(body.get('password') or '').strip()
    if not email or not password:
        return jsonify({'error': 'email_and_password_required'}), 400
    # Rate limiting by IP
    try:
        ip = request.headers.get('X-Forwarded-For', request.remote_addr) or 'unknown'
    except Exception:
        ip = 'unknown'
    now = time.time()
    arr = _LOGIN_ATTEMPTS.get(ip, [])
    arr = [t for t in arr if now - t < LOGIN_RATE_LIMIT_WINDOW]
    if len(arr) >= LOGIN_RATE_LIMIT_MAX:
        return jsonify({'error': 'too_many_attempts'}), 429
    arr.append(now)
    _LOGIN_ATTEMPTS[ip] = arr

    conn = _db()
    try:
        cur = conn.execute('SELECT id, email, password_hash, name, role FROM users WHERE email = ?', (email,))
        row = cur.fetchone()
        if not row or not check_password_hash(row['password_hash'], password):
            return jsonify({'error': 'invalid_credentials'}), 401
        user = {'id': row['id'], 'email': row['email'], 'name': row['name'], 'role': row['role']}
        access_token = _issue_access_token(user)
        refresh_token = _issue_refresh_token(row['id'])
        return jsonify({'token': access_token, 'refresh_token': refresh_token, 'user': user, 'expires_in': ACCESS_TOKEN_TTL})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/auth/me', methods=['GET'])
@auth_required
def auth_me():
    return jsonify({'user': request.user})

@app.route('/auth/logout', methods=['POST'])
@auth_required
def auth_logout():
    # Invalidate refresh token presented in body (optional)
    body = _get_body()
    rtoken = body.get('refresh_token')
    if rtoken:
        conn = _db()
        try:
            with conn:
                conn.execute('DELETE FROM refresh_tokens WHERE token = ?', (rtoken,))
        finally:
            conn.close()
    return jsonify({'ok': True})

@app.route('/auth/refresh', methods=['POST'])
def auth_refresh():
    body = _get_body()
    rtoken = str(body.get('refresh_token') or '')
    # Backward-compatible behavior: if no refresh_token provided but a valid access token is present,
    # issue a new access token (session extension semantics)
    if not rtoken:
        user = _require_user_from_token()
        if user:
            access = _issue_access_token(user)
            return jsonify({'token': access, 'refresh_token': body.get('refresh_token'), 'user': user, 'expires_in': ACCESS_TOKEN_TTL})
        return jsonify({'error': 'missing_refresh_token'}), 400
    conn = _db()
    try:
        cur = conn.execute('SELECT user_id, expires_at FROM refresh_tokens WHERE token = ?', (rtoken,))
        row = cur.fetchone()
        if not row:
            return jsonify({'error': 'invalid_refresh_token'}), 401
        if datetime.fromisoformat(row['expires_at']) < datetime.utcnow():
            with conn:
                conn.execute('DELETE FROM refresh_tokens WHERE token = ?', (rtoken,))
            return jsonify({'error': 'refresh_token_expired'}), 401
        cur2 = conn.execute('SELECT id, email, name, role FROM users WHERE id = ?', (row['user_id'],))
        u = cur2.fetchone()
        if not u:
            return jsonify({'error': 'user_not_found'}), 404
        user = {'id': u['id'], 'email': u['email'], 'name': u['name'], 'role': u['role']}
        access = _issue_access_token(user)
        # rotate refresh if requested
        rotate = str(body.get('rotate', 'true')).lower() in ('1','true','yes')
        if rotate:
            with conn:
                conn.execute('DELETE FROM refresh_tokens WHERE token = ?', (rtoken,))
            new_refresh = _issue_refresh_token(u['id'])
        else:
            new_refresh = rtoken
        return jsonify({'token': access, 'refresh_token': new_refresh, 'user': user, 'expires_in': ACCESS_TOKEN_TTL})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/status')
def status():
    """Get current system status"""
    return jsonify({
        'status': 'running',
        'ai_enabled': chatbot.ai_enabled,
        'system_data': chatbot.system_data,
        'timestamp': datetime.now().isoformat()
    })

# Simple health endpoint for frontend checks
@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

# ---- Frontend-compatible endpoints (no /api prefix) ----
@app.route('/system-health', methods=['GET'])
def system_health():
    """Return normalized system health snapshot"""
    try:
        # Collect a quick live snapshot to avoid stale data
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        net = psutil.net_io_counters()
        cpu_percent = psutil.cpu_percent(interval=0.1)
        procs = len(psutil.pids())
        try:
            temps = psutil.sensors_temperatures()
            # choose first available temperature reading
            temp_val = None
            for arr in temps.values():
                if arr:
                    temp_val = getattr(arr[0], 'current', None)
                    if temp_val is not None:
                        break
        except Exception:
            temp_val = None

        status = 'healthy'
        if cpu_percent > 90 or mem.percent > 90 or (temp_val or 0) > 75:
            status = 'critical'
        elif cpu_percent > 75 or mem.percent > 80 or (temp_val or 0) > 65:
            status = 'warning'

        return jsonify({
            'cpu': round(cpu_percent, 2),
            'memory': round(mem.percent, 2),
            'disk': round((disk.used / disk.total) * 100, 2),
            'network_in': net.bytes_recv,
            'network_out': net.bytes_sent,
            'temperature': temp_val,
            'status': status,
            'uptime': f"{int(psutil.boot_time())}",
            'active_processes': procs,
            'last_updated': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/dashboard-snapshot', methods=['GET'])
def dashboard_snapshot():
    """Return the latest cached snapshot from the sampler with minimal overhead."""
    try:
        with _SAMPLER_LOCK:
            snap = dict(_LAST_SNAPSHOT) if isinstance(_LAST_SNAPSHOT, dict) else None
        if not snap:
            snap = _take_snapshot()
        return jsonify(snap)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/events/system')
def events_system():
    """SSE feed of system snapshots."""
    try:
        def gen():
            last_ts = None
            while True:
                with _SAMPLER_LOCK:
                    snap = dict(_LAST_SNAPSHOT) if isinstance(_LAST_SNAPSHOT, dict) else None
                if snap and snap.get('timestamp') != last_ts:
                    last_ts = snap.get('timestamp')
                    yield f"data: {json.dumps(snap)}\n\n"
                # heartbeat every 10s
                yield "event: heartbeat\n"
                yield "data: ping\n\n"
                time.sleep(max(0.5, _SAMPLER_INTERVAL))
        headers = {
            'Cache-Control': 'no-cache',
            'Content-Type': 'text/event-stream',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
        return Response(gen(), headers=headers)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/processes', methods=['GET'])
def processes():
    """Return top processes by CPU and memory"""
    try:
        with _SAMPLER_LOCK:
            snap = dict(_LAST_SNAPSHOT) if isinstance(_LAST_SNAPSHOT, dict) else None
        if snap and 'top_processes' in snap:
            return jsonify(snap['top_processes'][:20])
        # fallback to live
        out = []
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
            info = p.info
            out.append({
                'pid': info.get('pid'),
                'name': info.get('name'),
                'cpu_percent': float(info.get('cpu_percent') or 0.0),
                'memory_percent': float(info.get('memory_percent') or 0.0),
                'status': info.get('status') or 'running'
            })
        out.sort(key=lambda x: x.get('cpu_percent', 0), reverse=True)
        return jsonify(out[:20])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/system-info', methods=['GET'])
def system_info():
    """Return system platform and specs"""
    try:
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        freq = psutil.cpu_freq()
        # load average is not available on Windows; guard it
        try:
            load_avg = os.getloadavg()  # type: ignore[attr-defined]
            load_avg_display = ", ".join([f"{x:.2f}" for x in load_avg])
        except Exception:
            load_avg_display = 'N/A'
        return jsonify({
            'platform': py_platform.platform(),
            'cpu_cores': psutil.cpu_count(logical=True),
            'total_memory': round(mem.total / (1024**3), 2),
            'available_memory': round(mem.available / (1024**3), 2),
            'free_disk': round(disk.free / (1024**3), 2),
            'cpu_freq': round((freq.current if freq else 0.0), 2),
            'boot_time': datetime.fromtimestamp(psutil.boot_time()).isoformat(),
            'load_avg': load_avg_display
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/ai-health', methods=['GET'])
def ai_health():
    """Summarize AI health (synthetic but dynamic)"""
    try:
        # Derive a pseudo accuracy based on system steadiness
        sysdata = chatbot.system_data or {}
        cpu = float(sysdata.get('cpu', {}).get('usage_percent') or 50)
        mem = float(sysdata.get('memory', {}).get('percent') or 50)
        # Lower load => higher accuracy proxy
        accuracy = max(60, min(99, 100 - ((cpu + mem) / 3)))
        response_time = int(100 + (cpu + mem))  # ms
        status = 'healthy'
        if accuracy < 70 or response_time > 400:
            status = 'critical'
        elif accuracy < 80 or response_time > 250:
            status = 'warning'
        return jsonify({'status': status, 'accuracy': int(accuracy), 'response_time': response_time})
    except Exception as e:
        return jsonify({'status': 'unknown', 'error': str(e)}), 500

@app.route('/anomalies', methods=['GET'])
def anomalies():
    """Return detected system anomalies (derived from recent events)"""
    try:
        events = chatbot.get_recent_events()
        # Map to expected shape
        mapped = []
        for idx, ev in enumerate(events):
            mapped.append({
                'id': idx + 1,
                'type': ev.get('type', 'event'),
                'description': ev.get('message', ''),
                'severity': ev.get('severity', 'info'),
                'timestamp': datetime.now().isoformat()
            })
        return jsonify(mapped)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/predictive-analytics', methods=['GET'])
def predictive_analytics():
    """Return simple predictive insights"""
    try:
        timeframe = request.args.get('timeframe', '1hour')
        sysdata = chatbot.system_data or {}
        cpu = float(sysdata.get('cpu', {}).get('usage_percent') or 50)
        mem = float(sysdata.get('memory', {}).get('percent') or 50)
        disk = float(sysdata.get('disk', {}).get('percent') or 50)
        preds = [
            {'metric': 'cpu', 'timeframe': timeframe, 'prediction': f"CPU expected to be {min(100.0, cpu + 5):.1f}%", 'confidence': 78},
            {'metric': 'memory', 'timeframe': timeframe, 'prediction': f"Memory expected to be {min(100.0, mem + 3):.1f}%", 'confidence': 74},
            {'metric': 'disk', 'timeframe': timeframe, 'prediction': f"Disk usage trending {min(100.0, disk + 1):.1f}%", 'confidence': 69}
        ]
        return jsonify(preds)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/devices', methods=['GET'])
def devices():
    """Return a minimal device inventory list. In demo mode, synthesize from processes and platform info."""
    try:
        sysinfo = chatbot.system_data or {}
        hostname = py_platform.node() or 'local-machine'
        os_name = py_platform.system()
        os_ver = py_platform.version()
        mem = psutil.virtual_memory()
        cpu_pct = float(sysinfo.get('cpu', {}).get('usage_percent') or psutil.cpu_percent(interval=0.0))
        mem_pct = float(sysinfo.get('memory', {}).get('percent') or mem.percent)
        disk = psutil.disk_usage('/')
        disk_pct = float((disk.used / disk.total) * 100.0) if disk.total else 0.0
        status = 'online'
        device = {
            'id': hostname,
            'name': hostname,
            'type': 'desktop',
            'os': f"{os_name}",
            'version': os_ver,
            'employee': 'Local User',
            'department': 'Engineering',
            'status': status,
            'lastSeen': datetime.now().isoformat(),
            'ipAddress': None,
            'location': None,
            'specs': {
                'cpu': f"{psutil.cpu_count()} cores",
                'memory': f"{round(mem.total/(1024**3),1)} GB",
                'storage': f"{round(disk.total/(1024**3),1)} GB"
            },
            'performance': {
                'cpu': round(cpu_pct, 1),
                'memory': round(mem_pct, 1),
                'disk': round(disk_pct, 1)
            },
            'security': {
                'antivirus': True,
                'firewall': True,
                'encrypted': False,
                'lastUpdate': datetime.now().isoformat()
            },
            'installed': True
        }
        return jsonify([device])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/company-stats', methods=['GET'])
def company_stats():
    """Return aggregate device stats. If only local device is known, compute trivially."""
    try:
        # Call the local function directly rather than HTTP to avoid recursion/hosting issues
        with app.test_request_context('/devices'):
            dev_resp = devices()
        device_list = []
        try:
            device_list = dev_resp.get_json(force=True)
        except Exception:
            device_list = []
        total = len(device_list) if isinstance(device_list, list) else 0
        online = sum(1 for d in device_list if d.get('status') == 'online') if total else 0
        offline = total - online
        warning = sum(1 for d in device_list if d.get('status') == 'warning') if total else 0
        critical = sum(1 for d in device_list if d.get('status') == 'critical') if total else 0
        return jsonify({
            'totalDevices': total,
            'onlineDevices': online,
            'offlineDevices': offline,
            'warningDevices': warning,
            'criticalDevices': critical,
            'updated_at': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/performance', methods=['GET'])
def performance():
    """Return mini time series performance data"""
    try:
        series = []
        now = time.time()
        # 24 points, 1-minute apart
        for i in range(24):
            ts = now - (60 * (23 - i))
            series.append({
                'timestamp': ts,
                'cpu': psutil.cpu_percent(interval=0.0),
                'memory': psutil.virtual_memory().percent,
                'disk': (psutil.disk_usage('/').used / psutil.disk_usage('/').total) * 100,
                'network_in': psutil.net_io_counters().bytes_recv,
                'network_out': psutil.net_io_counters().bytes_sent,
                'temperature': None
            })
        return jsonify(series)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/analyze', methods=['POST'])
def analyze():
    """Simple analysis placeholder (sentiment-ish)"""
    try:
        data = request.get_json(silent=True) or {}
        text = data.get('text', '')
        atype = data.get('type', 'sentiment')
        if not text:
            return jsonify({'error': 'Text is required'}), 400
        score = 0
        lower = text.lower()
        if any(w in lower for w in ['good', 'great', 'excellent', 'fast', 'healthy']):
            score += 1
        if any(w in lower for w in ['bad', 'slow', 'issue', 'error', 'problem', 'critical']):
            score -= 1
        result = {'score': score, 'type': atype}
        return jsonify({'result': result, 'timestamp': datetime.now().isoformat(), 'analysis_type': atype})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---- System Actions (no auth; demo acks with real context) ----
@app.route('/actions/memory-cleanup', methods=['POST'])
@auth_required
@role_required('admin')
def action_memory_cleanup():
    try:
        # Optional JSON body for extra flags
        data = request.get_json(silent=True) or {}
        aggressive_flag = bool(data.get('aggressive') or request.args.get('aggressive'))
        include_browser_cache = bool(data.get('include_browser_cache'))
        trim_working_sets = bool(data.get('trim_working_sets', False)) and aggressive_flag and os.name == 'nt'
        dry_run = bool(data.get('dry_run'))

        mem = psutil.virtual_memory()
        disk_before = psutil.disk_usage('/')
        before = {
            'memory_percent': round(mem.percent, 2),
            'memory_available_gb': round(mem.available / (1024**3), 2),
            'memory_used_gb': round(mem.used / (1024**3), 2),
            'disk_free_gb': round(disk_before.free / (1024**3), 2),
            'disk_percent': round((disk_before.used / disk_before.total) * 100, 2)
        }

        if not ALLOW_SYSTEM_ACTIONS:
            return jsonify({
                'status': 'forbidden',
                'message': 'Real cleanup is disabled. Set ALLOW_SYSTEM_ACTIONS=true and restart the backend to enable.',
                'hint': "PowerShell: $env:ALLOW_SYSTEM_ACTIONS='true'; python aiops_chatbot_backend.py",
                'before': before,
                'timestamp': datetime.now().isoformat()
            }), 403

        # --------------------
        # BUILD CLEANUP TARGETS
        # --------------------
        targets = set()
        user_temp = tempfile.gettempdir()
        appdata_temp = os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'Temp')
        targets.update({user_temp, appdata_temp})

        # Aggressive mode tries a few more (permission dependent)
        if aggressive_flag:
            win_tmp = os.path.join(os.getenv('SystemRoot', 'C:\\Windows'), 'Temp')
            targets.add(win_tmp)
            # Browser caches (best‑effort, may fail silently)
            if include_browser_cache:
                chrome_cache = os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'Google', 'Chrome', 'User Data', 'Default', 'Cache')
                edge_cache = os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'Microsoft', 'Edge', 'User Data', 'Default', 'Cache')
                targets.update({chrome_cache, edge_cache})

        # Collect sample of files prior to deletion for transparency (top 15 by size per target)
        sample_before = []
        for t in list(targets):
            if not os.path.isdir(t):
                continue
            try:
                entries = []
                for root, dirs, files in os.walk(t):
                    for f in files:
                        fp = os.path.join(root, f)
                        try:
                            sz = os.path.getsize(fp)
                            entries.append((fp, sz))
                        except Exception:
                            continue
                    # Do not recurse too deep for speed (only one level for aggressive large dirs)
                    break
                # Keep top 15 largest per target
                entries.sort(key=lambda x: x[1], reverse=True)
                for fp, sz in entries[:15]:
                    sample_before.append({'path': fp, 'size_bytes': sz})
            except Exception:
                continue

        freed_total = 0
        removed_total = 0
        deleted_samples = []  # capture some deleted file names (max 25)
        if not dry_run:
            for p in targets:
                try:
                    if not os.path.isdir(p):
                        continue
                    for entry in os.listdir(p):
                        if removed_total > 5000:  # safety cap
                            break
                        fp = os.path.join(p, entry)
                        try:
                            if os.path.isfile(fp) or os.path.islink(fp):
                                try:
                                    size = os.path.getsize(fp)
                                except Exception:
                                    size = 0
                                try:
                                    os.remove(fp)
                                    freed_total += size
                                    removed_total += 1
                                    if len(deleted_samples) < 25:
                                        deleted_samples.append({'path': fp, 'size_bytes': size})
                                except Exception:
                                    pass
                            elif os.path.isdir(fp):
                                # measure then attempt delete (non‑recursive quick attempt)
                                try:
                                    sz = _dir_size_bytes(fp)
                                except Exception:
                                    sz = 0
                                try:
                                    shutil.rmtree(fp, ignore_errors=True)
                                    if not os.path.exists(fp):
                                        freed_total += sz
                                        removed_total += 1
                                        if len(deleted_samples) < 25:
                                            deleted_samples.append({'path': fp, 'size_bytes': sz, 'type': 'dir'})
                                except Exception:
                                    pass
                        except Exception:
                            continue
                except Exception:
                    continue

            _clear_recycle_bin_windows()

        # Optional: trim working sets of high memory processes (Windows only)
        working_set_results = []
        if trim_working_sets and not dry_run:
            PROCESS_QUERY_INFORMATION = 0x0400
            PROCESS_SET_QUOTA = 0x0100
            EmptyWorkingSet = None
            try:
                EmptyWorkingSet = ctypes.windll.psapi.EmptyWorkingSet  # type: ignore[attr-defined]
            except Exception:
                EmptyWorkingSet = None
            if EmptyWorkingSet:
                CRITICAL_NAMES = {n.lower() for n in [
                    'system', 'smss.exe', 'csrss.exe', 'wininit.exe', 'winlogon.exe', 'services.exe',
                    'lsass.exe', 'svchost.exe', 'explorer.exe'
                ]}
                for proc in psutil.process_iter(['pid', 'name', 'memory_percent']):
                    try:
                        name_l = (proc.info.get('name') or '').lower()
                        if name_l in CRITICAL_NAMES:
                            continue
                        if float(proc.info.get('memory_percent') or 0) < 1.5:  # skip tiny processes
                            continue
                        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_SET_QUOTA, False, proc.pid)  # type: ignore[attr-defined]
                        if handle:
                            try:
                                res = EmptyWorkingSet(handle)
                                working_set_results.append({
                                    'pid': proc.pid,
                                    'name': proc.info.get('name'),
                                    'memory_percent_before': round(float(proc.info.get('memory_percent') or 0), 2),
                                    'trimmed': bool(res)
                                })
                            except Exception as e:
                                working_set_results.append({'pid': proc.pid, 'name': proc.info.get('name'), 'error': str(e)})
                            finally:
                                try:
                                    ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
                                except Exception:
                                    pass
                    except Exception:
                        continue

        mem_after = psutil.virtual_memory()
        disk_after = psutil.disk_usage('/')
        after = {
            'memory_available_gb': round(mem_after.available / (1024**3), 2),
            'memory_used_gb': round(mem_after.used / (1024**3), 2),
            'memory_percent': round(mem_after.percent, 2),
            'disk_free_gb': round(disk_after.free / (1024**3), 2),
            'disk_percent': round((disk_after.used / disk_after.total) * 100, 2)
        }

        if dry_run:
            status_value = 'preview'
            message = 'Preview only – no changes made'
        else:
            status_value = 'accepted' if (removed_total > 0 or freed_total > 0 or working_set_results) else 'no_changes'
            message = (
                f"Cleanup completed (removed {removed_total} items, ~{round(freed_total/1024/1024,1)} MB freed)"
                if status_value == 'accepted' else
                "Cleanup completed but no removable temp files were found"
            )

        return jsonify({
            'status': status_value,
            'message': message,
            'before': before,
            'after': after,
            'delta': {
                'memory_percent_change': round(before['memory_percent'] - after['memory_percent'], 2),
                'memory_available_gb_change': round(after['memory_available_gb'] - before['memory_available_gb'], 3),
                'disk_free_gb_change': round(after['disk_free_gb'] - before['disk_free_gb'], 3)
            },
            'details': {
                'paths_cleaned': sorted(list(targets)),
                'freed_bytes': freed_total,
                'items_removed': removed_total,
                'aggressive_mode': aggressive_flag,
                'browser_cache_included': include_browser_cache,
                'sample_before_top_items': sample_before[:25],
                'sample_deleted_items': deleted_samples,
                'working_set_trims': working_set_results[:50],
                'dry_run': dry_run
            },
            'verification': {
                'memory_percent_before': before['memory_percent'],
                'memory_percent_after': after['memory_percent'],
                'disk_free_gb_before': before['disk_free_gb'],
                'disk_free_gb_after': after['disk_free_gb']
            },
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/actions/disk-cleanup', methods=['POST'])
@auth_required
@role_required('admin')
def action_disk_cleanup():
    try:
        d = psutil.disk_usage('/')
        before = {
            'total_gb': round(d.total / (1024**3), 2),
            'used_gb': round(d.used / (1024**3), 2),
            'free_gb': round(d.free / (1024**3), 2),
            'percent': round((d.used / d.total) * 100, 2)
        }
        data = request.get_json(silent=True) or {}
        dry_run = bool(data.get('dry_run'))

        if not ALLOW_SYSTEM_ACTIONS:
            return jsonify({
                'status': 'forbidden',
                'message': 'Real disk cleanup is disabled. Set ALLOW_SYSTEM_ACTIONS=true and restart the backend.',
                'hint': 'On Windows PowerShell: $env:ALLOW_SYSTEM_ACTIONS=\'true\'; python aiops_chatbot_backend.py',
                'before': before,
                'timestamp': datetime.now().isoformat()
            }), 403

        # Safe user-level disk cleanup
        user_temp = tempfile.gettempdir()
        appdata_temp = os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'Temp')
        downloads = os.path.join(os.path.expanduser('~'), 'Downloads')
        freed_total = 0
        removed_total = 0
        if not dry_run:
            for p in {user_temp, appdata_temp}:
                try:
                    freed, removed = _safe_clean_dir(p)
                    freed_total += freed
                    removed_total += removed
                except Exception:
                    pass
            # Optional: clean Downloads files older than 30 days (non-recursive)
            try:
                cutoff = time.time() - (30 * 24 * 3600)
                if os.path.isdir(downloads):
                    for name in os.listdir(downloads):
                        fp = os.path.join(downloads, name)
                        try:
                            if os.path.isfile(fp) and os.path.getmtime(fp) < cutoff:
                                size = os.path.getsize(fp)
                                os.remove(fp)
                                freed_total += size
                                removed_total += 1
                        except Exception:
                            pass
            except Exception:
                pass
            _clear_recycle_bin_windows()

        d_after = psutil.disk_usage('/')
        after = {
            'free_gb': round(d_after.free / (1024**3), 2),
            'percent': round((d_after.used / d_after.total) * 100, 2)
        }
        if dry_run:
            status_value = 'preview'
            message = 'Preview only – no changes made'
        else:
            status_value = 'accepted' if (removed_total > 0 or freed_total > 0) else 'no_changes'
            message = (
                f'Disk cleanup completed (removed {removed_total} items, ~{round(freed_total/1024/1024,1)} MB freed)'
                if status_value == 'accepted' else
                'Disk cleanup completed but no removable items were found'
            )
        return jsonify({
            'status': status_value,
            'message': message,
            'before': before,
            'after': after,
            'delta': {
                'disk_free_gb_change': round(after['free_gb'] - before['free_gb'], 3),
                'disk_percent_change': round(before['percent'] - after['percent'], 2)
            },
            'details': {
                'paths_cleaned': list({user_temp, appdata_temp, downloads}),
                'freed_bytes': freed_total,
                'items_removed': removed_total,
                'dry_run': dry_run
            },
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/actions/process-monitor', methods=['POST'])
def action_process_monitor():
    try:
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
            info = p.info
            procs.append({
                'pid': info.get('pid'),
                'name': info.get('name'),
                'cpu_percent': float(info.get('cpu_percent') or 0.0),
                'memory_percent': float(info.get('memory_percent') or 0.0),
                'status': info.get('status') or 'running'
            })
        procs.sort(key=lambda x: (x.get('cpu_percent') or 0), reverse=True)
        return jsonify({
            'status': 'accepted',
            'message': 'Process monitor started',
            'top_processes': procs[:10],
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/actions/emergency-stop', methods=['POST'])
@auth_required
@role_required('admin')
def action_emergency_stop():
    try:
        data = request.get_json(silent=True) or {}
        pid = data.get('pid')
        name = data.get('name') or data.get('process_name')
        top_cpu = bool(data.get('top_cpu', False))

        if not ALLOW_SYSTEM_ACTIONS:
            return jsonify({
                'status': 'forbidden',
                'message': 'Real process termination is disabled. Set ALLOW_SYSTEM_ACTIONS=true and restart the backend.',
                'hint': 'On Windows PowerShell: $env:ALLOW_SYSTEM_ACTIONS=\'true\'; python aiops_chatbot_backend.py'
            }), 403

        # Guardrail: never touch critical system processes
        CRITICAL_NAMES = {n.lower() for n in [
            'system', 'smss.exe', 'csrss.exe', 'wininit.exe', 'winlogon.exe', 'services.exe',
            'lsass.exe', 'svchost.exe', 'explorer.exe'
        ]}

        killed = []
        errors = []

        def terminate_proc(p: psutil.Process):
            try:
                info = p.as_dict(attrs=['pid', 'name', 'username', 'status'])
            except Exception:
                info = {'pid': p.pid, 'name': '?'}
            name_l = str(info.get('name') or '').lower()
            if name_l in CRITICAL_NAMES:
                errors.append({'pid': info.get('pid'), 'name': info.get('name'), 'error': 'blocked_critical_process'})
                return
            try:
                p.terminate()
                gone, alive = psutil.wait_procs([p], timeout=2)
                if alive:
                    # escalate carefully
                    for a in alive:
                        try:
                            a.kill()
                        except Exception:
                            pass
                        psutil.wait_procs([a], timeout=1)
                killed.append({'pid': info.get('pid'), 'name': info.get('name')})
            except psutil.AccessDenied:
                errors.append({'pid': info.get('pid'), 'name': info.get('name'), 'error': 'access_denied'})
            except psutil.NoSuchProcess:
                killed.append({'pid': info.get('pid'), 'name': info.get('name'), 'note': 'already_exited'})
            except Exception as e:
                errors.append({'pid': info.get('pid'), 'name': info.get('name'), 'error': str(e)})

        # Strategy selection
        if pid is not None:
            try:
                p = psutil.Process(int(pid))
                terminate_proc(p)
            except Exception as e:
                errors.append({'pid': pid, 'error': str(e)})
        elif name:
            matched = []
            for p in psutil.process_iter(['pid', 'name', 'username']):
                try:
                    if str(p.info.get('name') or '').lower() == str(name).lower():
                        matched.append(p)
                except Exception:
                    continue
            if not matched:
                return jsonify({
                    'status': 'not_found',
                    'message': f'No running process found with name: {name}',
                    'killed': [],
                    'errors': []
                }), 404
            for p in matched:
                terminate_proc(p)
        elif top_cpu:
            # Pick the highest CPU non-critical process
            candidates = []
            for p in psutil.process_iter(['pid', 'name', 'cpu_percent']):
                try:
                    n = (p.info.get('name') or '').lower()
                    if n and n not in CRITICAL_NAMES:
                        candidates.append(p)
                except Exception:
                    continue
            if not candidates:
                return jsonify({'status': 'no_candidates', 'message': 'No eligible processes to stop'}), 404
            # Ensure CPU metrics are fresh
            for p in candidates:
                try:
                    p.cpu_percent(interval=0.0)
                except Exception:
                    pass
            time.sleep(0.1)
            candidates.sort(key=lambda p: (p.cpu_percent(interval=0.0)), reverse=True)
            terminate_proc(candidates[0])
        else:
            return jsonify({
                'status': 'bad_request',
                'message': 'Provide a pid, process_name (name), or set top_cpu=true to stop the top CPU process.'
            }), 400

        return jsonify({
            'status': 'accepted',
            'message': 'Emergency stop executed',
            'killed': killed,
            'errors': errors,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

# ---- AI Actions (no auth; demo acks, echo params) ----
@app.route('/ai/retrain', methods=['POST'])
def ai_retrain():
    try:
        params = request.get_json(silent=True) or {}
        job_id = _new_job('retrain', params)
        _run_in_thread(job_id, _retrain_job)
        return jsonify({
            'status': 'accepted',
            'message': 'Model retraining started',
            'job_id': job_id,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/ai/diagnostics', methods=['POST'])
def ai_diagnostics():
    try:
        params = request.get_json(silent=True) or {}
        job_id = _new_job('diagnostics', params)
        _run_in_thread(job_id, _diagnostics_job)
        return jsonify({
            'status': 'accepted',
            'message': 'AI diagnostics started',
            'job_id': job_id,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/ai/update-params', methods=['POST'])
def ai_update_params():
    try:
        data = request.get_json(silent=True) or {}
        # Apply dynamic runtime flags (demo): adjust chatbot settings
        updated = {}
        if 'max_history' in data:
            try:
                chatbot.max_history = int(data['max_history'])
                updated['max_history'] = chatbot.max_history
            except Exception:
                pass
        if 'system_prompt' in data:
            try:
                chatbot.base_system_prompt = str(data['system_prompt'])[:4000]
                updated['system_prompt'] = 'updated'
            except Exception:
                pass
        return jsonify({
            'status': 'accepted',
            'message': 'Parameters updated',
            'applied': updated or data,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/ai/export-insights', methods=['POST'])
def ai_export_insights():
    try:
        params = request.get_json(silent=True) or {}
        job_id = _new_job('export', params)
        _run_in_thread(job_id, _export_job)
        return jsonify({
            'status': 'accepted',
            'message': 'Insights export started',
            'job_id': job_id,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

# ---- Job status/logs and download endpoints ----
@app.route('/jobs/<job_id>', methods=['GET'])
def job_status(job_id: str):
    try:
        with JOBS_LOCK:
            j = JOBS.get(job_id)
            if not j:
                return jsonify({'error': 'not_found'}), 404
            # do not leak full path in artifact on other OSes; safe to return as-is locally
            return jsonify(j)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/jobs/<job_id>/logs', methods=['GET'])
def job_logs(job_id: str):
    try:
        with JOBS_LOCK:
            j = JOBS.get(job_id)
            if not j:
                return jsonify({'error': 'not_found'}), 404
            return jsonify({'logs': j.get('logs', [])})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/jobs/<job_id>/download', methods=['GET'])
def job_download(job_id: str):
    try:
        with JOBS_LOCK:
            j = JOBS.get(job_id)
            if not j:
                return jsonify({'error': 'not_found'}), 404
            artifact = j.get('artifact')
        if not artifact or not os.path.isfile(artifact):
            return jsonify({'error': 'artifact_not_ready'}), 404
        # send with a friendly filename
        filename = os.path.basename(artifact)
        return send_file(artifact, as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---- Config / Debug endpoints ----
@app.route('/config', methods=['GET'])
def config_info():
    try:
        return jsonify({
            'allow_system_actions': bool(ALLOW_SYSTEM_ACTIONS),
            'ai_enabled': bool(chatbot.ai_enabled),
            'open_registration': str(os.getenv('OPEN_REGISTRATION', 'true')).lower() in ('1','true','yes'),
            'platform': py_platform.platform(),
            'python': sys.version.split()[0]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---- Integrations: Slack & Discord ----
@app.route('/integrations/slack/test', methods=['POST'])
@auth_required
def slack_test():
    """Send a test message to Slack via webhook.
    Body: { webhook_url?: str, title?: str, status?: str, details?: dict }
    If webhook_url is omitted, tries SLACK_ALERTS_WEBHOOK env.
    """
    try:
        data = request.get_json(silent=True) or {}
        webhook_url = data.get('webhook_url') or os.getenv('SLACK_ALERTS_WEBHOOK')
        title = data.get('title') or 'AIOps Bot Test'
        status = data.get('status') or 'All systems operational'
        details = data.get('details') or {}
        if not webhook_url:
            return jsonify({'error': 'Missing Slack webhook_url'}), 400

        # Build a simple Slack message payload (Block Kit)
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": f"📣 {title}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Status:* {status}\n*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}},
        ]
        if details and isinstance(details, dict):
            lines = "\n".join([f"• {k}: {v}" for k, v in details.items()])
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Details:*\n{lines}"}})

        payload = {
            'text': title,
            'blocks': blocks
        }

        # Send to Slack webhook
        resp = requests.post(webhook_url, json=payload, timeout=10)
        ok = resp.status_code in (200, 204)
        return jsonify({'ok': ok, 'status_code': resp.status_code, 'response_text': resp.text[:500]}), (200 if ok else 502)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/integrations/discord/test', methods=['POST'])
@auth_required
def discord_test():
    """Send a test message to Discord via webhook.
    Body: { webhook_url?: str, content?: str, title?: str, fields?: dict }
    If webhook_url is omitted, tries DISCORD_WEBHOOK_URL env.
    """
    try:
        data = request.get_json(silent=True) or {}
        webhook_url = data.get('webhook_url') or os.getenv('DISCORD_WEBHOOK_URL')
        content = data.get('content') or 'AIOps Bot: Test notification'
        title = data.get('title') or 'AIOps Bot Test'
        fields = data.get('fields') or {}
        if not webhook_url:
            return jsonify({'error': 'Missing Discord webhook_url'}), 400

        embed_fields = []
        if isinstance(fields, dict):
            for k, v in list(fields.items())[:10]:
                embed_fields.append({"name": str(k), "value": str(v), "inline": True})

        payload = {
            'content': content,
            'embeds': [
                {
                    'title': title,
                    'description': f'This is a test message sent at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
                    'color': 5814783,
                    'fields': embed_fields
                }
            ]
        }

        resp = requests.post(webhook_url, json=payload, timeout=10)
        ok = 200 <= resp.status_code < 300
        return jsonify({'ok': ok, 'status_code': resp.status_code, 'response_text': resp.text[:500]}), (200 if ok else 502)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Determine port: --port N > PORT env > default 5000
    port = int(os.getenv('PORT', '5000'))
    if '--port' in sys.argv:
        try:
            idx = sys.argv.index('--port')
            port = int(sys.argv[idx + 1])
        except Exception:
            pass

    print("[BOOT] Starting AIOps AI Chatbot...")
    print(f"[HTTP] Chatbot will be available at: http://localhost:{port}")
    print("[INFO] Users can now interact with AI for system diagnostics!")
    print(f"[ACTIONS] System actions enabled: {ALLOW_SYSTEM_ACTIONS}")
    
    use_waitress = str(os.getenv('USE_WAITRESS', 'false')).lower() in ('1','true','yes')
    if use_waitress:
        try:
            from waitress import serve
            print('[HTTP] Starting with waitress (production server)')
            serve(app, host='0.0.0.0', port=port)
        except Exception as e:
            print(f"[HTTP] Waitress unavailable ({e}), falling back to Flask dev server")
            app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
    else:
        app.run(host='0.0.0.0', port=port, debug=False, threaded=True)