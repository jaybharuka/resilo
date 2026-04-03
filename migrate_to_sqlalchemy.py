#!/usr/bin/env python3
"""
Complete SQLAlchemy migration for auth_system.py
Replaces all sqlite3.connect() calls with SQLAlchemy SessionLocal
"""
import re

def migrate_auth_system():
    file_path = 'app/auth/auth_system.py'
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Step 1: Replace imports
    content = re.sub(
        r'import jwt\nimport bcrypt\nimport sqlite3\nfrom datetime import datetime, timedelta',
        'import jwt\nimport bcrypt\nfrom sqlalchemy import create_engine, text\nfrom sqlalchemy.orm import sessionmaker\nfrom datetime import datetime, timedelta',
        content
    )
    
    # Step 2: Update __init__ method
    old_init = r'class AuthenticationSystem:\n    def __init__\(self, db_path: str = "auth\.db", secret_key: str = None\):\n        self\.db_path = db_path\n        self\.secret_key = secret_key or os\.environ\.get\("JWT_SECRET_KEY"\)\n        if not self\.secret_key:\n            raise RuntimeError\("JWT_SECRET_KEY environment variable must be set"\)\n        self\._init_database\(\)\n        self\._create_default_admin\(\)'
    
    new_init = '''class AuthenticationSystem:
    def __init__(self, db_path: str = "auth.db", secret_key: str = None):
        self.db_path = db_path
        self.secret_key = secret_key or os.environ.get("JWT_SECRET_KEY")
        if not self.secret_key:
            raise RuntimeError("JWT_SECRET_KEY environment variable must be set")
        db_url = f"sqlite:///{db_path}"
        self.engine = create_engine(db_url, connect_args={"check_same_thread": False}, pool_size=10, max_overflow=20)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self._init_database()
        self._create_default_admin()'''
    
    content = re.sub(old_init, new_init, content)
    
    # Step 3: Replace _init_database
    old_init_db = r'def _init_database\(self\):.*?conn\.close\(\)'
    new_init_db = '''def _init_database(self):
        """Initialize authentication database"""
        with self.engine.connect() as conn:
            conn.execute(text('CREATE TABLE IF NOT EXISTS companies (id TEXT PRIMARY KEY, name TEXT NOT NULL, domain TEXT UNIQUE NOT NULL, is_active BOOLEAN DEFAULT TRUE, max_devices INTEGER DEFAULT 100, max_users INTEGER DEFAULT 50, created_at TEXT NOT NULL)'))
            conn.execute(text('CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, full_name TEXT NOT NULL, role TEXT NOT NULL, department TEXT, company_id TEXT, is_active BOOLEAN DEFAULT TRUE, last_login TEXT, created_at TEXT NOT NULL, must_change_password BOOLEAN DEFAULT FALSE, FOREIGN KEY (company_id) REFERENCES companies (id))'))
            try:
                conn.execute(text('ALTER TABLE users ADD COLUMN must_change_password BOOLEAN DEFAULT FALSE'))
            except Exception:
                pass
            conn.execute(text('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, token_hash TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL, is_revoked BOOLEAN DEFAULT FALSE, FOREIGN KEY (user_id) REFERENCES users (id))'))
            conn.execute(text('CREATE TABLE IF NOT EXISTS user_devices (user_id TEXT, device_id TEXT, assigned_at TEXT NOT NULL, PRIMARY KEY (user_id, device_id), FOREIGN KEY (user_id) REFERENCES users (id))'))
            conn.execute(text('CREATE TABLE IF NOT EXISTS password_reset_tokens (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL, expires_at TEXT NOT NULL, used BOOLEAN DEFAULT FALSE, created_at TEXT NOT NULL, FOREIGN KEY (user_id) REFERENCES users (id))'))
            for col, definition in [('totp_secret', 'TEXT'), ('totp_enabled', 'BOOLEAN DEFAULT FALSE')]:
                try:
                    conn.execute(text(f'ALTER TABLE users ADD COLUMN {col} {definition}'))
                except Exception:
                    pass
            conn.execute(text('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)'))
            conn.execute(text('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)'))
            conn.execute(text('CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)'))
            conn.execute(text('CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token_hash)'))
            conn.execute(text('CREATE INDEX IF NOT EXISTS idx_reset_tokens ON password_reset_tokens(token_hash)'))
            conn.commit()'''
    
    content = re.sub(old_init_db, new_init_db, content, flags=re.DOTALL)
    
    # Write back
    with open(file_path, 'w') as f:
        f.write(content)
    
    print("Migration complete!")

if __name__ == '__main__':
    migrate_auth_system()
