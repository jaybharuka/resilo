#!/usr/bin/env python3
"""Complete SQLAlchemy migration for auth_system.py"""

file_path = 'app/auth/auth_system.py'

with open(file_path, 'r') as f:
    lines = f.readlines()

# Find and replace _init_database method
new_lines = []
i = 0
while i < len(lines):
    if 'def _init_database(self):' in lines[i]:
        # Replace entire method
        new_lines.append(lines[i])  # def line
        new_lines.append(lines[i+1])  # docstring
        # Skip old implementation until next method
        i += 2
        while i < len(lines) and not (lines[i].strip().startswith('def ') and not lines[i].startswith('        ')):
            i += 1
        # Add new implementation
        new_lines.append('        with self.engine.connect() as conn:\n')
        new_lines.append('            conn.execute(text(\'CREATE TABLE IF NOT EXISTS companies (id TEXT PRIMARY KEY, name TEXT NOT NULL, domain TEXT UNIQUE NOT NULL, is_active BOOLEAN DEFAULT TRUE, max_devices INTEGER DEFAULT 100, max_users INTEGER DEFAULT 50, created_at TEXT NOT NULL)\'))\n')
        new_lines.append('            conn.execute(text(\'CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, full_name TEXT NOT NULL, role TEXT NOT NULL, department TEXT, company_id TEXT, is_active BOOLEAN DEFAULT TRUE, last_login TEXT, created_at TEXT NOT NULL, must_change_password BOOLEAN DEFAULT FALSE, FOREIGN KEY (company_id) REFERENCES companies (id))\'))\n')
        new_lines.append('            try:\n')
        new_lines.append('                conn.execute(text(\'ALTER TABLE users ADD COLUMN must_change_password BOOLEAN DEFAULT FALSE\'))\n')
        new_lines.append('            except Exception:\n')
        new_lines.append('                pass\n')
        new_lines.append('            conn.execute(text(\'CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, token_hash TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL, is_revoked BOOLEAN DEFAULT FALSE, FOREIGN KEY (user_id) REFERENCES users (id))\'))\n')
        new_lines.append('            conn.execute(text(\'CREATE TABLE IF NOT EXISTS user_devices (user_id TEXT, device_id TEXT, assigned_at TEXT NOT NULL, PRIMARY KEY (user_id, device_id), FOREIGN KEY (user_id) REFERENCES users (id))\'))\n')
        new_lines.append('            conn.execute(text(\'CREATE TABLE IF NOT EXISTS password_reset_tokens (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL, expires_at TEXT NOT NULL, used BOOLEAN DEFAULT FALSE, created_at TEXT NOT NULL, FOREIGN KEY (user_id) REFERENCES users (id))\'))\n')
        new_lines.append('            for col, definition in [(\'totp_secret\', \'TEXT\'), (\'totp_enabled\', \'BOOLEAN DEFAULT FALSE\')]:\n')
        new_lines.append('                try:\n')
        new_lines.append('                    conn.execute(text(f\'ALTER TABLE users ADD COLUMN {col} {definition}\'))\n')
        new_lines.append('                except Exception:\n')
        new_lines.append('                    pass\n')
        new_lines.append('            conn.execute(text(\'CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)\'))\n')
        new_lines.append('            conn.execute(text(\'CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)\'))\n')
        new_lines.append('            conn.execute(text(\'CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)\'))\n')
        new_lines.append('            conn.execute(text(\'CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token_hash)\'))\n')
        new_lines.append('            conn.execute(text(\'CREATE INDEX IF NOT EXISTS idx_reset_tokens ON password_reset_tokens(token_hash)\'))\n')
        new_lines.append('            conn.commit()\n')
        new_lines.append('    \n')
        continue
    new_lines.append(lines[i])
    i += 1

with open(file_path, 'w') as f:
    f.writelines(new_lines)

print("Migration step 1 complete: _init_database replaced")
