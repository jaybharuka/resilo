"""
Idempotent admin seed + login verification script.

Usage:
    python scripts/seed_admin.py              # seed + verify with admin123
    python scripts/seed_admin.py --check-only # verify only, no DB writes
"""
import sys, os, argparse
from typing import Optional
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
except ImportError:
    pass

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'aiops_auth.db')

DEFAULT_ADMIN_EMAIL = os.getenv('SEED_ADMIN_EMAIL', 'admin@company.local')
DEFAULT_ADMIN_USERNAME = os.getenv('SEED_ADMIN_USERNAME', 'admin')
DEFAULT_ADMIN_PASSWORD = os.getenv('SEED_ADMIN_PASSWORD', 'Admin@1234')

DEFAULT_LOGIN_HOST = os.getenv('LOGIN_TEST_URL', 'http://localhost:5000/auth/login')

def seed_admin(email: Optional[str] = None, username: Optional[str] = None, password: Optional[str] = None):
    email = email or DEFAULT_ADMIN_EMAIL
    username = username or DEFAULT_ADMIN_USERNAME
    password = password or DEFAULT_ADMIN_PASSWORD
    import sqlite3, bcrypt, uuid
    from datetime import datetime

    db = os.path.abspath(DB_PATH)
    print(f"DB: {db}")

    conn = sqlite3.connect(db)
    cur  = conn.cursor()

    # Ensure schema has all required columns
    cur.execute("PRAGMA table_info(users)")
    cols = {r[1] for r in cur.fetchall()}
    if 'password_hash' not in cols:
        print("ERROR: 'password_hash' column missing — wrong database?")
        conn.close()
        sys.exit(1)

    cur.execute("SELECT id, username, email, password_hash, is_active FROM users WHERE email=? OR username=?", (email, username))
    row = cur.fetchone()

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

    if row:
        uid, uname, uemail, stored_hash, is_active = row
        # Verify existing hash
        ok = bcrypt.checkpw(password.encode(), stored_hash.encode() if isinstance(stored_hash, str) else stored_hash)
        print(f"User exists: id={uid} username={uname} email={uemail} active={bool(is_active)}")
        print(f"Password '{password}' matches stored hash: {ok}")
        if not ok:
            print("Hash mismatch — resetting password...")
            cur.execute("UPDATE users SET password_hash=?, must_change_password=0, is_active=1 WHERE id=?", (pw_hash, uid))
            conn.commit()
            print("Password reset done.")
        else:
            # Make sure account is active and not force-changing password
            cur.execute("UPDATE users SET must_change_password=0, is_active=1 WHERE id=?", (uid,))
            conn.commit()
            print("Account confirmed active, must_change_password=0.")
    else:
        print("Admin user not found — creating...")
        # Ensure a company exists
        cur.execute("SELECT id FROM companies LIMIT 1")
        comp = cur.fetchone()
        if not comp:
            cid = str(uuid.uuid4())
            cur.execute("INSERT INTO companies (id, name, domain, created_at) VALUES (?,?,?,?)",
                        (cid, 'Default Company', 'company.local', datetime.now().isoformat()))
        else:
            cid = comp[0]

        uid = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO users
              (id, username, email, password_hash, full_name, role, department, company_id, is_active, created_at, must_change_password)
            VALUES (?,?,?,?,?,?,?,?,1,?,0)
        """, (uid, username, email, pw_hash, 'System Administrator', 'admin', 'IT', cid, datetime.now().isoformat()))
        conn.commit()
        print(f"Admin created: id={uid}")

    conn.close()
    return True


def verify_login(host: Optional[str] = None, email: Optional[str] = None, password: Optional[str] = None):
    import urllib.request, json
    host = host or DEFAULT_LOGIN_HOST
    email = email or DEFAULT_ADMIN_EMAIL
    password = password or DEFAULT_ADMIN_PASSWORD

    normalized_host = host.rstrip('/')
    url = normalized_host if normalized_host.endswith('/auth/login') else f'{normalized_host}/auth/login'
    payload = json.dumps({'email': email, 'password': password}).encode()
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            body = json.loads(r.read())
            if body.get('token') and body.get('user'):
                print(f"LOGIN OK — role={body['user']['role']} token={body['token'][:20]}...")
                return True
            print(f"LOGIN UNEXPECTED RESPONSE: {body}")
            return False
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"LOGIN FAILED HTTP {e.code}: {body}")
        return False
    except Exception as e:
        print(f"LOGIN ERROR (server unreachable?): {e}")
        return False


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--host', default=DEFAULT_LOGIN_HOST)
    parser.add_argument('--email', default=DEFAULT_ADMIN_EMAIL)
    parser.add_argument('--username', default=DEFAULT_ADMIN_USERNAME)
    parser.add_argument('--password', default=DEFAULT_ADMIN_PASSWORD)
    args = parser.parse_args()

    if not args.check_only:
        seed_admin(email=args.email, username=args.username, password=args.password)
        print()
    verify_login(host=args.host, email=args.email, password=args.password)
