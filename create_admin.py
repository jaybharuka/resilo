#!/usr/bin/env python3
import sqlite3
import bcrypt
import uuid
from datetime import datetime

db_path = 'aiops_auth.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Create companies table
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

# Create users table
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
        totp_secret TEXT,
        totp_enabled BOOLEAN DEFAULT FALSE,
        FOREIGN KEY (company_id) REFERENCES companies (id)
    )
''')

# Get or create default company
cursor.execute('SELECT id FROM companies LIMIT 1')
company = cursor.fetchone()
if not company:
    company_id = str(uuid.uuid4())
    cursor.execute(
        'INSERT INTO companies (id, name, domain, is_active, created_at) VALUES (?, ?, ?, ?, ?)',
        (company_id, 'Default Company', 'company.local', True, datetime.now().isoformat())
    )
    print('✓ Default company created')
else:
    company_id = company[0]

# Check if admin exists
cursor.execute('SELECT id FROM users WHERE email = ?', ('admin@company.local',))
admin = cursor.fetchone()

password = 'Admin@1234'
pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

if admin:
    cursor.execute(
        'UPDATE users SET password_hash = ?, is_active = 1, must_change_password = 0 WHERE email = ?',
        (pw_hash, 'admin@company.local')
    )
    print('✓ Admin password updated')
else:
    user_id = str(uuid.uuid4())
    cursor.execute(
        'INSERT INTO users (id, username, email, password_hash, full_name, role, department, company_id, is_active, created_at, must_change_password) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (user_id, 'admin', 'admin@company.local', pw_hash, 'System Administrator', 'admin', 'IT', company_id, True, datetime.now().isoformat(), False)
    )
    print('✓ Admin user created')

conn.commit()

# Verify
cursor.execute('SELECT username, email, role FROM users WHERE email = ?', ('admin@company.local',))
row = cursor.fetchone()
if row:
    print(f'✓ Verified: username={row[0]}, email={row[1]}, role={row[2]}')
    print(f'✓ Login with: admin@company.local / Admin@1234')

conn.close()
