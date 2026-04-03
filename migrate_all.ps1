$file = 'app/auth/auth_system.py'
$content = Get-Content $file -Raw

# 1. Replace imports
$content = $content -replace 'import jwt\nimport bcrypt\nimport sqlite3\nfrom datetime import datetime, timedelta', 'import jwt
import bcrypt
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta'

# 2. Replace __init__ method
$old_init = @'
    def __init__(self, db_path: str = "auth.db", secret_key: str = None):
        self.db_path = db_path
        self.secret_key = secret_key or os.environ.get("JWT_SECRET_KEY") or secrets.token_urlsafe(32)
        self._init_database()
        self._create_default_admin()
'@

$new_init = @'
    def __init__(self, db_path: str = "auth.db", secret_key: str = None):
        self.db_path = db_path
        self.secret_key = secret_key or os.environ.get("JWT_SECRET_KEY")
        if not self.secret_key:
            raise RuntimeError("JWT_SECRET_KEY environment variable must be set")
        db_url = f"sqlite:///{db_path}"
        self.engine = create_engine(db_url, connect_args={"check_same_thread": False}, pool_size=10, max_overflow=20)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self._init_database()
        self._create_default_admin()
'@

$content = $content -replace [regex]::Escape($old_init), $new_init

# 3. Replace _init_database - use engine.connect() with text()
$old_init_db = @'
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
'@

$new_init_db = @'
    def _init_database(self):
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
            conn.commit()
'@

$content = $content -replace [regex]::Escape($old_init_db), $new_init_db

Set-Content $file $content
Write-Host "Migration complete: imports, __init__, and _init_database replaced"
