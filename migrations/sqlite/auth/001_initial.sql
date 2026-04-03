-- Auth system tables (auth.db / aiops_auth.db)
CREATE TABLE IF NOT EXISTS companies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    domain TEXT UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    max_devices INTEGER DEFAULT 100,
    max_users INTEGER DEFAULT 50,
    created_at TEXT NOT NULL
);

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
    totp_secret TEXT,
    totp_enabled BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (company_id) REFERENCES companies (id)
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    is_revoked BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS user_devices (
    user_id TEXT,
    device_id TEXT,
    assigned_at TEXT NOT NULL,
    PRIMARY KEY (user_id, device_id),
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token_hash TEXT UNIQUE NOT NULL,
    expires_at TEXT NOT NULL,
    used BOOLEAN DEFAULT FALSE,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_reset_tokens ON password_reset_tokens(token_hash);
