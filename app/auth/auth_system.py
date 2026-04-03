"""
Role-Based Authentication System
JWT-based authentication with role management for multi-tenant AIOps platform
"""

import jwt
import bcrypt
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import secrets
import hashlib
import hmac
import struct
import time
import base64
import os
from functools import wraps
from flask import request, jsonify, current_app

# ---------------------------------------------------------------------------
# Pure-Python TOTP (RFC 6238) — uses only stdlib, no pyotp needed
# ---------------------------------------------------------------------------

def _totp_generate(secret_b32: str, at_time: int = None) -> str:
    key = base64.b32decode(secret_b32.upper().replace(' ', ''))
    t = ((at_time or int(time.time())) // 30).to_bytes(8, 'big')
    h = hmac.new(key, t, 'sha1').digest()
    offset = h[-1] & 0x0f
    code = struct.unpack('>I', h[offset:offset + 4])[0] & 0x7FFFFFFF
    return f'{code % 1_000_000:06d}'

def _totp_verify(secret_b32: str, code: str, window: int = 1) -> bool:
    now = int(time.time())
    for delta in range(-window, window + 1):
        expected = _totp_generate(secret_b32, now + delta * 30)
        if hmac.compare_digest(expected, code.strip()):
            return True
    return False

def _totp_uri(secret_b32: str, account: str, issuer: str = 'AIOps Bot') -> str:
    from urllib.parse import quote
    return (f'otpauth://totp/{quote(issuer)}:{quote(account)}'
            f'?secret={secret_b32}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30')

class UserRole(Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    EMPLOYEE = "employee"
    GUEST = "guest"

class Permission(Enum):
    VIEW_ALL_DEVICES = "view_all_devices"
    MANAGE_DEVICES = "manage_devices"
    VIEW_ANALYTICS = "view_analytics"
    MANAGE_USERS = "manage_users"
    SYSTEM_SETTINGS = "system_settings"
    VIEW_OWN_DEVICE = "view_own_device"
    CREATE_TICKETS = "create_tickets"
    MANAGE_TICKETS = "manage_tickets"

@dataclass
class User:
    id: str
    username: str
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: str
    last_login: Optional[str] = None
    password_hash: Optional[str] = None
    org_id: Optional[str] = None

@dataclass
class Company:
    id: str
    name: str
    domain: str
    is_active: bool
    created_at: str
    max_devices: int = 100
    max_users: int = 50

@dataclass
class AuthToken:
    user_id: str
    username: str
    role: str
    company_id: str
    permissions: List[str]
    expires_at: str

# Role-Permission mapping
ROLE_PERMISSIONS = {
    UserRole.ADMIN: [
        Permission.VIEW_ALL_DEVICES,
        Permission.MANAGE_DEVICES,
        Permission.VIEW_ANALYTICS,
        Permission.MANAGE_USERS,
        Permission.SYSTEM_SETTINGS,
        Permission.VIEW_OWN_DEVICE,
        Permission.CREATE_TICKETS,
        Permission.MANAGE_TICKETS
    ],
    UserRole.MANAGER: [
        Permission.VIEW_ALL_DEVICES,
        Permission.VIEW_ANALYTICS,
        Permission.VIEW_OWN_DEVICE,
        Permission.CREATE_TICKETS,
        Permission.MANAGE_TICKETS
    ],
    UserRole.EMPLOYEE: [
        Permission.VIEW_OWN_DEVICE,
        Permission.CREATE_TICKETS
    ],
    UserRole.GUEST: [
        Permission.VIEW_OWN_DEVICE
    ]
}

class AuthenticationSystem:
    def __init__(self, db_path: str = "auth.db", secret_key: str = None):
        self.db_path = db_path
        self.secret_key = secret_key or os.environ.get("JWT_SECRET_KEY")
        if not self.secret_key:
            raise RuntimeError("JWT_SECRET_KEY environment variable is required but not set")
        self._init_database()
        self._create_default_admin()
    
    def _init_database(self):
        """Initialize authentication database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Companies table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS companies (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                domain TEXT UNIQUE NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                max_devices INTEGER DEFAULT 100,
                max_users INTEGER DEFAULT 50,
                created_at TEXT NOT NULL
            )
        ''')
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL,
                department TEXT,
                company_id TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                last_login TEXT,
                created_at TEXT NOT NULL,
                must_change_password BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (company_id) REFERENCES companies (id)
            )
        ''')
        # Add column to existing databases that predate this migration
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN must_change_password BOOLEAN DEFAULT FALSE")
        except Exception:
            pass  # Column already exists
        
        # Sessions table for token management
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_revoked BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Device assignments table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_devices (
                user_id TEXT,
                device_id TEXT,
                assigned_at TEXT NOT NULL,
                PRIMARY KEY (user_id, device_id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Password reset tokens table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                token_hash TEXT UNIQUE NOT NULL,
                expires_at TEXT NOT NULL,
                used BOOLEAN DEFAULT FALSE,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')

        # TOTP 2FA columns (migrate existing DBs)
        for col, definition in [
            ('totp_secret', 'TEXT'),
            ('totp_enabled', 'BOOLEAN DEFAULT FALSE'),
        ]:
            try:
                cursor.execute(f'ALTER TABLE users ADD COLUMN {col} {definition}')
            except Exception:
                pass  # Column already exists

        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token_hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_reset_tokens ON password_reset_tokens(token_hash)')

        conn.commit()
        conn.close()
    
    def _create_default_admin(self):
        """Create default admin user if none exists"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE role = ?', (UserRole.ADMIN.value,))
        admin_count = cursor.fetchone()[0]
        
        if admin_count == 0:
            # Create default company
            company_id = self._generate_id()
            cursor.execute('''
                INSERT OR IGNORE INTO companies (id, name, domain, created_at)
                VALUES (?, ?, ?, ?)
            ''', (company_id, "Default Company", "company.local", datetime.now().isoformat()))
            
            # Create default admin — password must be changed on first login
            admin_id = self._generate_id()
            default_password = secrets.token_urlsafe(16)
            password_hash = self._hash_password(default_password)

            cursor.execute('''
                INSERT OR IGNORE INTO users
                (id, username, email, password_hash, full_name, role, department, company_id, created_at, must_change_password)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                admin_id, "admin", "admin@company.local", password_hash,
                "System Administrator", UserRole.ADMIN.value, "IT",
                company_id, datetime.now().isoformat(), True
            ))
            print(f"Default admin created. You MUST set a password on first login.")
            
            conn.commit()
        
        conn.close()
    
    def _generate_id(self) -> str:
        """Generate unique ID"""
        return secrets.token_urlsafe(16)
    
    def _hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against hash"""
        if not password_hash or not password_hash.startswith(('$2b$', '$2a$', '$2y$')):
            return False
        try:
            return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
        except Exception:
            return False
    
    def _get_user_permissions(self, role: str) -> List[str]:
        """Get permissions for a user role.
        Maps modern auth_api roles (devops, viewer) to legacy Flask roles."""
        _role_map = {
            'devops':  'manager',
            'viewer':  'employee',
            'manager': 'manager',
            'employee': 'employee',
            'guest':   'guest',
        }
        mapped = _role_map.get(role, role)
        try:
            user_role = UserRole(mapped)
            return [perm.value for perm in ROLE_PERMISSIONS.get(user_role, [])]
        except ValueError:
            # Unknown role — grant minimal read access
            return [Permission.VIEW_OWN_DEVICE.value, Permission.VIEW_ANALYTICS.value]
    
    # Company Management
    def create_company(self, name: str, domain: str, max_devices: int = 100, max_users: int = 50) -> Company:
        """Create a new company"""
        company_id = self._generate_id()
        now = datetime.now().isoformat()
        
        company = Company(
            id=company_id,
            name=name,
            domain=domain,
            is_active=True,
            created_at=now,
            max_devices=max_devices,
            max_users=max_users
        )
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO companies (id, name, domain, is_active, max_devices, max_users, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            company.id, company.name, company.domain, company.is_active,
            company.max_devices, company.max_users, company.created_at
        ))
        
        conn.commit()
        conn.close()
        
        return company
    
    def get_company(self, company_id: str) -> Optional[Company]:
        """Get company by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM companies WHERE id = ?', (company_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return Company(
                id=row[0], name=row[1], domain=row[2], is_active=bool(row[3]),
                max_devices=row[4], max_users=row[5], created_at=row[6]
            )
        return None
    
    # User Management
    def create_user(self, username: str, email: str, password: str, full_name: str,
                   role: UserRole, department: str, company_id: str) -> User:
        """Create a new user"""
        user_id = self._generate_id()
        password_hash = self._hash_password(password)
        now = datetime.now().isoformat()
        
        user = User(
            id=user_id,
            username=username,
            email=email,
            full_name=full_name,
            role=role.value,
            department=department,
            is_active=True,
            created_at=now,
            company_id=company_id
        )
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO users 
            (id, username, email, password_hash, full_name, role, department, company_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user.id, user.username, user.email, password_hash, user.full_name,
            user.role, user.department, user.company_id, user.created_at
        ))
        
        conn.commit()
        conn.close()
        
        return user
    
    def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return User(
                id=row[0], username=row[1], email=row[2], full_name=row[4],
                role=row[5], department=row[6], company_id=row[7],
                is_active=bool(row[8]), last_login=row[9], created_at=row[10]
            )
        return None
    
    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return User(
                id=row[0], username=row[1], email=row[2], full_name=row[4],
                role=row[5], department=row[6], company_id=row[7],
                is_active=bool(row[8]), last_login=row[9], created_at=row[10]
            )
        return None
    
    def get_company_users(self, company_id: str) -> List[User]:
        """Get all users for a company"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE company_id = ? ORDER BY created_at DESC', (company_id,))
        rows = cursor.fetchall()
        conn.close()
        
        return [
            User(
                id=row[0], username=row[1], email=row[2], full_name=row[4],
                role=row[5], department=row[6], company_id=row[7],
                is_active=bool(row[8]), last_login=row[9], created_at=row[10]
            )
            for row in rows
        ]
    
    # Authentication
    def authenticate_user(self, username: str, password: str) -> Tuple[bool, Optional[User], Optional[str]]:
        """Authenticate user credentials"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, username, email, password_hash, full_name, role, department, 
                   company_id, is_active, last_login, created_at
            FROM users WHERE username = ?
        ''', (username,))
        
        row = cursor.fetchone()
        
        if row and self._verify_password(password, row[3]):
            user = User(
                id=row[0], username=row[1], email=row[2], full_name=row[4],
                role=row[5], department=row[6], company_id=row[7],
                is_active=bool(row[8]), last_login=row[9], created_at=row[10]
            )
            
            if not user.is_active:
                conn.close()
                return False, None, "Account is deactivated"
            
            # Update last login
            cursor.execute('''
                UPDATE users SET last_login = ? WHERE id = ?
            ''', (datetime.now().isoformat(), user.id))
            
            conn.commit()
            conn.close()
            
            return True, user, None
        
        conn.close()
        return False, None, "Invalid credentials"
    
    def generate_token(self, user: User) -> str:
        """Generate JWT token for authenticated user"""
        permissions = self._get_user_permissions(user.role)
        expires_at = datetime.now() + timedelta(hours=24)
        
        payload = {
            'user_id': user.id,
            'username': user.username,
            'role': user.role,
            'company_id': user.company_id,
            'permissions': permissions,
            'exp': expires_at.timestamp(),
            'iat': datetime.now().timestamp()
        }
        
        token = jwt.encode(payload, self.secret_key, algorithm='HS256')
        
        # Store session
        session_id = self._generate_id()
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO sessions (id, user_id, token_hash, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (session_id, user.id, token_hash, expires_at.isoformat(), datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        return token
    
    def verify_token(self, token: str) -> Tuple[bool, Optional[AuthToken], Optional[str]]:
        """Verify JWT token — accepts both legacy Flask tokens (session in SQLite)
        and modern FastAPI auth_api tokens (validated by signature + expiry only)."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])

            # Modern FastAPI token: has 'sub' claim instead of 'user_id'
            is_modern = 'sub' in payload and 'user_id' not in payload

            if is_modern:
                # Accept any signature-valid, non-expired token from auth_api
                auth_token = AuthToken(
                    user_id=payload.get('sub', ''),
                    username=payload.get('username', payload.get('email', '')),
                    role=payload.get('role', 'viewer'),
                    company_id=payload.get('org_id', ''),
                    permissions=self._get_user_permissions(payload.get('role', 'viewer')),
                    expires_at=datetime.fromtimestamp(payload['exp']).isoformat()
                )
                return True, auth_token, None

            # Legacy token: verify against SQLite sessions table
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT is_revoked FROM sessions
                WHERE token_hash = ? AND expires_at > ?
            ''', (token_hash, datetime.now().isoformat()))
            session = cursor.fetchone()
            conn.close()

            if not session or session[0]:  # Session not found or revoked
                return False, None, "Invalid or revoked token"

            auth_token = AuthToken(
                user_id=payload['user_id'],
                username=payload['username'],
                role=payload['role'],
                company_id=payload['company_id'],
                permissions=payload['permissions'],
                expires_at=datetime.fromtimestamp(payload['exp']).isoformat()
            )
            return True, auth_token, None

        except jwt.ExpiredSignatureError:
            return False, None, "Token has expired"
        except jwt.InvalidTokenError:
            return False, None, "Invalid token"
    
    def revoke_token(self, token: str):
        """Revoke a token"""
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE sessions SET is_revoked = TRUE 
            WHERE token_hash = ?
        ''', (token_hash,))
        
        conn.commit()
        conn.close()
    
    def revoke_user_sessions(self, user_id: str):
        """Revoke all sessions for a user"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE sessions SET is_revoked = TRUE 
            WHERE user_id = ?
        ''', (user_id,))
        
        conn.commit()
        conn.close()
    
    # Device Assignment
    def assign_device_to_user(self, user_id: str, device_id: str):
        """Assign a device to a user"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO user_devices (user_id, device_id, assigned_at)
            VALUES (?, ?, ?)
        ''', (user_id, device_id, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    
    def get_user_devices(self, user_id: str) -> List[str]:
        """Get device IDs assigned to a user"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT device_id FROM user_devices WHERE user_id = ?', (user_id,))
        rows = cursor.fetchall()
        conn.close()
        
        return [row[0] for row in rows]
    
    def remove_device_from_user(self, user_id: str, device_id: str):
        """Remove device assignment from user"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM user_devices WHERE user_id = ? AND device_id = ?', (user_id, device_id))
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # Password Reset
    # ------------------------------------------------------------------

    def create_reset_token(self, email: str) -> Optional[str]:
        """
        Generate a password-reset token for the given email.
        Returns the raw token (to embed in a link), or None if email not found.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE email = ? AND is_active = 1', (email.strip().lower(),))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None

        user_id = row[0]
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        expires_at = (datetime.now() + timedelta(hours=1)).isoformat()

        # Invalidate any existing unused tokens for this user
        cursor.execute(
            'UPDATE password_reset_tokens SET used = 1 WHERE user_id = ? AND used = 0',
            (user_id,)
        )
        cursor.execute(
            'INSERT INTO password_reset_tokens (id, user_id, token_hash, expires_at, created_at) VALUES (?,?,?,?,?)',
            (self._generate_id(), user_id, token_hash, expires_at, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
        return raw_token

    def consume_reset_token(self, raw_token: str, new_password: str) -> Tuple[bool, Optional[str]]:
        """
        Validate the raw token and update the user's password.
        Returns (success, error_message).
        """
        if len(new_password) < 8:
            return False, 'Password must be at least 8 characters'

        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, user_id, expires_at, used FROM password_reset_tokens WHERE token_hash = ?',
            (token_hash,)
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False, 'Invalid or expired reset link'

        token_id, user_id, expires_at, used = row
        if used:
            conn.close()
            return False, 'Reset link has already been used'
        if datetime.fromisoformat(expires_at) < datetime.now():
            conn.close()
            return False, 'Reset link has expired'

        new_hash = self._hash_password(new_password)
        cursor.execute(
            'UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?',
            (new_hash, user_id)
        )
        cursor.execute('UPDATE password_reset_tokens SET used = 1 WHERE id = ?', (token_id,))
        # Revoke all active sessions so old tokens are invalidated
        cursor.execute('UPDATE sessions SET is_revoked = 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return True, None

    # ------------------------------------------------------------------
    # TOTP 2FA
    # ------------------------------------------------------------------

    def setup_totp(self, user_id: str) -> dict:
        """
        Generate a new TOTP secret for a user (does not enable 2FA yet).
        Returns {'secret': ..., 'uri': ...} so the frontend can show a QR code.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT email FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise ValueError('User not found')

        email = row[0]
        secret = base64.b32encode(os.urandom(20)).decode('utf-8').rstrip('=')
        # Store the pending secret (not yet enabled)
        cursor.execute('UPDATE users SET totp_secret = ?, totp_enabled = 0 WHERE id = ?', (secret, user_id))
        conn.commit()
        conn.close()

        return {
            'secret': secret,
            'uri': _totp_uri(secret, email),
        }

    def verify_totp_code(self, user_id: str, code: str) -> bool:
        """Verify a 6-digit TOTP code against the user's stored secret."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT totp_secret FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        if not row or not row[0]:
            return False
        return _totp_verify(row[0], code)

    def enable_totp(self, user_id: str) -> bool:
        """Mark 2FA as enabled for the user (call after first successful verify)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT totp_secret FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        if not row or not row[0]:
            conn.close()
            return False
        cursor.execute('UPDATE users SET totp_enabled = 1 WHERE id = ?', (user_id,))
        conn.commit()
        conn.close()
        return True

    def disable_totp(self, user_id: str):
        """Disable and remove 2FA for the user."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET totp_secret = NULL, totp_enabled = 0 WHERE id = ?', (user_id,))
        conn.commit()
        conn.close()

    def get_totp_status(self, user_id: str) -> dict:
        """Return {'enabled': bool, 'configured': bool} for the user."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT totp_secret, totp_enabled FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return {'enabled': False, 'configured': False}
        return {
            'enabled': bool(row[1]),
            'configured': bool(row[0]),
        }

# Flask decorators for authentication and authorization
def token_required(f):
    """Decorator to require valid token"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        if token.startswith('Bearer '):
            token = token[7:]
        
        auth_system = current_app.auth_system
        valid, auth_token, error = auth_system.verify_token(token)
        
        if not valid:
            return jsonify({'error': error}), 401
        
        request.current_user = auth_token
        return f(*args, **kwargs)
    
    return decorated

def permission_required(permission: Permission):
    """Decorator to require specific permission"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not hasattr(request, 'current_user'):
                return jsonify({'error': 'Authentication required'}), 401
            
            if permission.value not in request.current_user.permissions:
                return jsonify({'error': 'Insufficient permissions'}), 403
            
            return f(*args, **kwargs)
        return decorated
    return decorator

def role_required(required_role: UserRole):
    """Decorator to require specific role"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not hasattr(request, 'current_user'):
                return jsonify({'error': 'Authentication required'}), 401
            
            if request.current_user.role != required_role.value:
                return jsonify({'error': f'Role {required_role.value} required'}), 403
            
            return f(*args, **kwargs)
        return decorated
    return decorator

# Example usage
if __name__ == "__main__":
    # Initialize authentication system
    auth = AuthenticationSystem()
    
    # Create a test company
    try:
        company = auth.create_company("Test Company", "test.com")
        print(f"Created company: {company.name}")
    except:
        pass  # Company might already exist
    
    # Test authentication (skip if running in production)
    if os.environ.get("SKIP_AUTH_TEST"):
        success, user, error = False, None, "Skipped"
    else:
        success, user, error = auth.authenticate_user("admin", "admin123")
    if success:
        print(f"Authenticated user: {user.username}")
        
        # Generate token
        token = auth.generate_token(user)
        print(f"Generated token: {token[:50]}...")
        
        # Verify token
        valid, auth_token, error = auth.verify_token(token)
        if valid:
            print(f"Token valid for user: {auth_token.username}")
            print(f"Permissions: {auth_token.permissions}")
        else:
            print(f"Token verification failed: {error}")
    else:
        print(f"Authentication failed: {error}")