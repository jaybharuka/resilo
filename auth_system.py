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
from functools import wraps
from flask import request, jsonify, current_app

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
    department: str
    is_active: bool
    created_at: str
    last_login: Optional[str] = None
    password_hash: Optional[str] = None
    company_id: Optional[str] = None

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
        self.secret_key = secret_key or secrets.token_urlsafe(32)
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
                FOREIGN KEY (company_id) REFERENCES companies (id)
            )
        ''')
        
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
        
        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token_hash)')
        
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
            
            # Create default admin
            admin_id = self._generate_id()
            password_hash = self._hash_password("admin123")
            
            cursor.execute('''
                INSERT OR IGNORE INTO users 
                (id, username, email, password_hash, full_name, role, department, company_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                admin_id, "admin", "admin@company.local", password_hash,
                "System Administrator", UserRole.ADMIN.value, "IT",
                company_id, datetime.now().isoformat()
            ))
            
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
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    
    def _get_user_permissions(self, role: str) -> List[str]:
        """Get permissions for a user role"""
        user_role = UserRole(role)
        return [perm.value for perm in ROLE_PERMISSIONS.get(user_role, [])]
    
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
        """Verify JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
            
            # Check if session is revoked
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
    
    # Test authentication
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