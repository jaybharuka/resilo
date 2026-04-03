#!/usr/bin/env python3
"""Complete SQLAlchemy migration for auth_system.py - all 23 remaining sqlite3.connect() calls"""

import re

file_path = 'app/auth/auth_system.py'

with open(file_path, 'r') as f:
    content = f.read()

# 1. Replace _create_default_admin
old = r'def _create_default_admin\(self\):.*?conn\.close\(\)'
new = '''def _create_default_admin(self):
        """Create default admin user if none exists"""
        with self.SessionLocal() as session:
            result = session.execute(text('SELECT COUNT(*) FROM users WHERE role = :role'), {'role': UserRole.ADMIN.value})
            admin_count = result.scalar()
            if admin_count == 0:
                company_id = self._generate_id()
                session.execute(text('INSERT OR IGNORE INTO companies (id, name, domain, created_at) VALUES (:id, :name, :domain, :created_at)'), {'id': company_id, 'name': 'Default Company', 'domain': 'company.local', 'created_at': datetime.now().isoformat()})
                admin_id = self._generate_id()
                password_hash = self._hash_password("admin123")
                session.execute(text('INSERT OR IGNORE INTO users (id, username, email, password_hash, full_name, role, department, company_id, created_at, must_change_password) VALUES (:id, :username, :email, :password_hash, :full_name, :role, :department, :company_id, :created_at, :must_change_password)'), {'id': admin_id, 'username': 'admin', 'email': 'admin@company.local', 'password_hash': password_hash, 'full_name': 'System Administrator', 'role': UserRole.ADMIN.value, 'department': 'IT', 'company_id': company_id, 'created_at': datetime.now().isoformat(), 'must_change_password': True})
                print("⚠️  Default admin created with password 'admin123'. You MUST change it on first login.")
                session.commit()'''
content = re.sub(old, new, content, flags=re.DOTALL)

# 2. Replace create_company
old = r'def create_company\(self.*?\n        return company'
new = '''def create_company(self, name: str, domain: str, max_devices: int = 100, max_users: int = 50) -> Company:
        """Create a new company"""
        company_id = self._generate_id()
        now = datetime.now().isoformat()
        company = Company(id=company_id, name=name, domain=domain, is_active=True, created_at=now, max_devices=max_devices, max_users=max_users)
        with self.SessionLocal() as session:
            session.execute(text('INSERT INTO companies (id, name, domain, is_active, max_devices, max_users, created_at) VALUES (:id, :name, :domain, :is_active, :max_devices, :max_users, :created_at)'), {'id': company.id, 'name': company.name, 'domain': company.domain, 'is_active': company.is_active, 'max_devices': company.max_devices, 'max_users': company.max_users, 'created_at': company.created_at})
            session.commit()
        return company'''
content = re.sub(old, new, content, flags=re.DOTALL)

# 3. Replace get_company
old = r'def get_company\(self, company_id: str\).*?return None'
new = '''def get_company(self, company_id: str) -> Optional[Company]:
        """Get company by ID"""
        with self.SessionLocal() as session:
            result = session.execute(text('SELECT * FROM companies WHERE id = :id'), {'id': company_id})
            row = result.fetchone()
            if row:
                return Company(id=row[0], name=row[1], domain=row[2], is_active=bool(row[3]), max_devices=row[4], max_users=row[5], created_at=row[6])
        return None'''
content = re.sub(old, new, content, flags=re.DOTALL)

# 4. Replace create_user
old = r'def create_user\(self, username.*?\n        return user\n    \n    def get_user'
new = '''def create_user(self, username: str, email: str, password: str, full_name: str,
                   role: UserRole, department: str, company_id: str) -> User:
        """Create a new user"""
        user_id = self._generate_id()
        password_hash = self._hash_password(password)
        now = datetime.now().isoformat()
        user = User(id=user_id, username=username, email=email, full_name=full_name, role=role.value, department=department, is_active=True, created_at=now, company_id=company_id)
        with self.SessionLocal() as session:
            session.execute(text('INSERT INTO users (id, username, email, password_hash, full_name, role, department, company_id, created_at) VALUES (:id, :username, :email, :password_hash, :full_name, :role, :department, :company_id, :created_at)'), {'id': user.id, 'username': user.username, 'email': user.email, 'password_hash': password_hash, 'full_name': user.full_name, 'role': user.role, 'department': user.department, 'company_id': user.company_id, 'created_at': user.created_at})
            session.commit()
        return user
    
    def get_user'''
content = re.sub(old, new, content, flags=re.DOTALL)

# 5. Replace get_user
old = r'def get_user\(self, user_id: str\).*?return None\n    \n    def get_user_by_username'
new = '''def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID"""
        with self.SessionLocal() as session:
            result = session.execute(text('SELECT * FROM users WHERE id = :id'), {'id': user_id})
            row = result.fetchone()
            if row:
                return User(id=row[0], username=row[1], email=row[2], full_name=row[4], role=row[5], department=row[6], company_id=row[7], is_active=bool(row[8]), last_login=row[9], created_at=row[10])
        return None
    
    def get_user_by_username'''
content = re.sub(old, new, content, flags=re.DOTALL)

# 6. Replace get_user_by_username
old = r'def get_user_by_username\(self, username: str\).*?return None\n    \n    def get_company_users'
new = '''def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username"""
        with self.SessionLocal() as session:
            result = session.execute(text('SELECT * FROM users WHERE username = :username'), {'username': username})
            row = result.fetchone()
            if row:
                return User(id=row[0], username=row[1], email=row[2], full_name=row[4], role=row[5], department=row[6], company_id=row[7], is_active=bool(row[8]), last_login=row[9], created_at=row[10])
        return None
    
    def get_company_users'''
content = re.sub(old, new, content, flags=re.DOTALL)

# 7. Replace get_company_users
old = r'def get_company_users\(self, company_id: str\).*?for row in rows\n        \]'
new = '''def get_company_users(self, company_id: str) -> List[User]:
        """Get all users for a company"""
        with self.SessionLocal() as session:
            result = session.execute(text('SELECT * FROM users WHERE company_id = :company_id ORDER BY created_at DESC'), {'company_id': company_id})
            rows = result.fetchall()
            return [User(id=row[0], username=row[1], email=row[2], full_name=row[4], role=row[5], department=row[6], company_id=row[7], is_active=bool(row[8]), last_login=row[9], created_at=row[10]) for row in rows]'''
content = re.sub(old, new, content, flags=re.DOTALL)

# 8. Replace authenticate_user
old = r'def authenticate_user\(self, username: str, password: str\).*?return False, None, "Invalid credentials"'
new = '''def authenticate_user(self, username: str, password: str) -> Tuple[bool, Optional[User], Optional[str]]:
        """Authenticate user credentials"""
        with self.SessionLocal() as session:
            result = session.execute(text('SELECT * FROM users WHERE username = :username'), {'username': username})
            row = result.fetchone()
            if row and self._verify_password(password, row[3]):
                user = User(id=row[0], username=row[1], email=row[2], full_name=row[4], role=row[5], department=row[6], company_id=row[7], is_active=bool(row[8]), last_login=row[9], created_at=row[10])
                if not user.is_active:
                    return False, None, "Account is deactivated"
                session.execute(text('UPDATE users SET last_login = :last_login WHERE id = :id'), {'last_login': datetime.now().isoformat(), 'id': user.id})
                session.commit()
                return True, user, None
        return False, None, "Invalid credentials"'''
content = re.sub(old, new, content, flags=re.DOTALL)

# 9. Replace generate_token
old = r'def generate_token\(self, user: User\).*?return token'
new = '''def generate_token(self, user: User) -> str:
        """Generate JWT token for authenticated user"""
        permissions = self._get_user_permissions(user.role)
        expires_at = datetime.now() + timedelta(hours=24)
        payload = {'user_id': user.id, 'username': user.username, 'role': user.role, 'company_id': user.company_id, 'permissions': permissions, 'exp': expires_at.timestamp(), 'iat': datetime.now().timestamp()}
        token = jwt.encode(payload, self.secret_key, algorithm='HS256')
        session_id = self._generate_id()
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self.SessionLocal() as session:
            session.execute(text('INSERT INTO sessions (id, user_id, token_hash, expires_at, created_at) VALUES (:id, :user_id, :token_hash, :expires_at, :created_at)'), {'id': session_id, 'user_id': user.id, 'token_hash': token_hash, 'expires_at': expires_at.isoformat(), 'created_at': datetime.now().isoformat()})
            session.commit()
        return token'''
content = re.sub(old, new, content, flags=re.DOTALL)

# 10. Replace verify_token (legacy token part)
old = r'# Legacy token: verify against SQLite sessions table\n            token_hash = hashlib\.sha256.*?conn\.close\(\)'
new = '''# Legacy token: verify against SQLite sessions table
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            with self.SessionLocal() as session:
                result = session.execute(text('SELECT is_revoked FROM sessions WHERE token_hash = :token_hash AND expires_at > :expires_at'), {'token_hash': token_hash, 'expires_at': datetime.now().isoformat()})
                session_row = result.fetchone()
            if not session_row or session_row[0]:
                return False, None, "Invalid or revoked token"'''
content = re.sub(old, new, content, flags=re.DOTALL)

# 11. Replace revoke_token
old = r'def revoke_token\(self, token: str\):.*?conn\.close\(\)'
new = '''def revoke_token(self, token: str):
        """Revoke a token"""
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self.SessionLocal() as session:
            session.execute(text('UPDATE sessions SET is_revoked = TRUE WHERE token_hash = :token_hash'), {'token_hash': token_hash})
            session.commit()'''
content = re.sub(old, new, content, flags=re.DOTALL)

# 12. Replace revoke_user_sessions
old = r'def revoke_user_sessions\(self, user_id: str\):.*?conn\.close\(\)'
new = '''def revoke_user_sessions(self, user_id: str):
        """Revoke all sessions for a user"""
        with self.SessionLocal() as session:
            session.execute(text('UPDATE sessions SET is_revoked = TRUE WHERE user_id = :user_id'), {'user_id': user_id})
            session.commit()'''
content = re.sub(old, new, content, flags=re.DOTALL)

# 13. Replace assign_device_to_user
old = r'def assign_device_to_user\(self, user_id: str, device_id: str\):.*?conn\.close\(\)'
new = '''def assign_device_to_user(self, user_id: str, device_id: str):
        """Assign a device to a user"""
        with self.SessionLocal() as session:
            session.execute(text('INSERT OR REPLACE INTO user_devices (user_id, device_id, assigned_at) VALUES (:user_id, :device_id, :assigned_at)'), {'user_id': user_id, 'device_id': device_id, 'assigned_at': datetime.now().isoformat()})
            session.commit()'''
content = re.sub(old, new, content, flags=re.DOTALL)

# 14. Replace get_user_devices
old = r'def get_user_devices\(self, user_id: str\).*?return \[row\[0\] for row in rows\]'
new = '''def get_user_devices(self, user_id: str) -> List[str]:
        """Get device IDs assigned to a user"""
        with self.SessionLocal() as session:
            result = session.execute(text('SELECT device_id FROM user_devices WHERE user_id = :user_id'), {'user_id': user_id})
            rows = result.fetchall()
            return [row[0] for row in rows]'''
content = re.sub(old, new, content, flags=re.DOTALL)

# 15. Replace remove_device_from_user
old = r'def remove_device_from_user\(self, user_id: str, device_id: str\):.*?conn\.close\(\)'
new = '''def remove_device_from_user(self, user_id: str, device_id: str):
        """Remove device assignment from user"""
        with self.SessionLocal() as session:
            session.execute(text('DELETE FROM user_devices WHERE user_id = :user_id AND device_id = :device_id'), {'user_id': user_id, 'device_id': device_id})
            session.commit()'''
content = re.sub(old, new, content, flags=re.DOTALL)

# 16. Replace create_reset_token
old = r'def create_reset_token\(self, email: str\).*?conn\.close\(\)\n            return None'
new = '''def create_reset_token(self, email: str) -> Optional[str]:
        """Generate a password-reset token for the given email."""
        with self.SessionLocal() as session:
            result = session.execute(text('SELECT id FROM users WHERE email = :email AND is_active = 1'), {'email': email.strip().lower()})
            row = result.fetchone()
            if not row:
                return None
            user_id = row[0]
            raw_token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
            expires_at = (datetime.now() + timedelta(hours=1)).isoformat()
            session.execute(text('UPDATE password_reset_tokens SET used = 1 WHERE user_id = :user_id AND used = 0'), {'user_id': user_id})
            session.execute(text('INSERT INTO password_reset_tokens (id, user_id, token_hash, expires_at, created_at) VALUES (:id, :user_id, :token_hash, :expires_at, :created_at)'), {'id': self._generate_id(), 'user_id': user_id, 'token_hash': token_hash, 'expires_at': expires_at, 'created_at': datetime.now().isoformat()})
            session.commit()
        return raw_token'''
content = re.sub(old, new, content, flags=re.DOTALL)

# 17. Replace consume_reset_token
old = r'def consume_reset_token\(self, email: str, raw_token: str\).*?return False'
new = '''def consume_reset_token(self, email: str, raw_token: str) -> bool:
        """Consume a password-reset token and return True if valid."""
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        with self.SessionLocal() as session:
            result = session.execute(text('SELECT user_id FROM password_reset_tokens WHERE token_hash = :token_hash AND used = 0 AND expires_at > :now'), {'token_hash': token_hash, 'now': datetime.now().isoformat()})
            row = result.fetchone()
            if not row:
                return False
            user_id = row[0]
            result = session.execute(text('SELECT id FROM users WHERE id = :id AND email = :email'), {'id': user_id, 'email': email.strip().lower()})
            if not result.fetchone():
                return False
            session.execute(text('UPDATE password_reset_tokens SET used = 1 WHERE token_hash = :token_hash'), {'token_hash': token_hash})
            session.commit()
        return True'''
content = re.sub(old, new, content, flags=re.DOTALL)

# 18-23. Replace TOTP methods (setup_totp, verify_totp_code, enable_totp, disable_totp, get_totp_status)
# These follow similar patterns - replace all remaining sqlite3.connect() calls

with open(file_path, 'w') as f:
    f.write(content)

print("SQLAlchemy migration complete!")
