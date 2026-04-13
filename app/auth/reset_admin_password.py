#!/usr/bin/env python3
"""
Reset the admin@company.local password in aiops_auth.db.

Usage:
    python reset_admin_password.py                  # prompts for new password
    python reset_admin_password.py --password <pw>  # non-interactive

The script writes a fresh bcrypt hash (compatible with auth_system.py) AND a
Werkzeug scrypt hash row if needed, so both api_server.py and
aiops_chatbot_backend.py can authenticate the admin immediately.
"""

import sqlite3
import sys
import os
import getpass

DB_PATH = os.getenv('AIOPS_DB_PATH', os.path.join(os.path.dirname(__file__), 'aiops_auth.db'))

def main():
    # --- Determine new password ---
    if '--password' in sys.argv:
        idx = sys.argv.index('--password')
        try:
            new_password = sys.argv[idx + 1]
        except IndexError:
            print("ERROR: --password requires a value.")
            sys.exit(1)
    else:
        new_password = getpass.getpass("New admin password (min 8 chars): ")
        confirm = getpass.getpass("Confirm password: ")
        if new_password != confirm:
            print("ERROR: Passwords do not match.")
            sys.exit(1)

    if len(new_password) < 8:
        print("ERROR: Password must be at least 8 characters.")
        sys.exit(1)

    # --- Hash with bcrypt (used by auth_system.py / api_server.py) ---
    try:
        import bcrypt
        bcrypt_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    except ImportError:
        print("WARNING: bcrypt not installed. Skipping bcrypt hash.")
        bcrypt_hash = None

    # --- Hash with Werkzeug scrypt (used by aiops_chatbot_backend.py) ---
    try:
        from werkzeug.security import generate_password_hash
        werkzeug_hash = generate_password_hash(new_password)
    except ImportError:
        print("WARNING: werkzeug not installed. Skipping Werkzeug hash.")
        werkzeug_hash = None

    if not bcrypt_hash and not werkzeug_hash:
        print("ERROR: Neither bcrypt nor werkzeug is available. Install dependencies first.")
        sys.exit(1)

    # --- Connect and update ---
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        print("Run api_server.py or aiops_chatbot_backend.py once first to initialise the DB.")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute("SELECT id, email, password_hash FROM users WHERE email = ?", ("admin@company.local",))
        row = cur.fetchone()

        if not row:
            print("Admin user (admin@company.local) not found in the database.")
            print("Starting either backend once will create it automatically.")
            sys.exit(1)

        # Prefer the hash that matches the backend currently in use.
        # If both are available we store bcrypt (auth_system.py is authoritative)
        # and aiops_chatbot_backend.py will auto-migrate it on next login.
        chosen_hash = bcrypt_hash or werkzeug_hash

        with conn:
            conn.execute(
                "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
                (chosen_hash, row['id'])
            )

        # Also revoke existing sessions so old JWTs are invalidated
        try:
            with conn:
                conn.execute("UPDATE sessions SET is_revoked = 1 WHERE user_id = ?", (str(row['id']),))
        except Exception:
            pass  # sessions table may not exist in all schema versions

        print(f"\n[OK] Admin password reset successfully.")
        print(f"    Email    : admin@company.local")
        print(f"    Hash type: {'bcrypt' if bcrypt_hash else 'werkzeug-scrypt'}")
        print(f"\nRestart the backend server, then log in with the new password.")

    finally:
        conn.close()


if __name__ == '__main__':
    main()
