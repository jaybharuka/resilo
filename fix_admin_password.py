#!/usr/bin/env python3
"""
Direct SQLite password reset utility.
This bypasses the Flask backend and directly updates the password hash.
"""
import sqlite3
import bcrypt
import sys

def reset_admin_password(db_path='aiops_auth.db', password='admin123'):
    """Reset admin password directly in SQLite"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Hash the password
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
        
        # Update admin user password
        cursor.execute(
            'UPDATE users SET password_hash = ? WHERE username = ?',
            (pw_hash, 'admin')
        )
        
        rows_updated = cursor.rowcount
        conn.commit()
        conn.close()
        
        if rows_updated > 0:
            print(f'✓ Admin password updated successfully')
            print(f'  Username: admin')
            print(f'  Email: admin@company.local')
            print(f'  Password: {password}')
            return True
        else:
            print('✗ Admin user not found in database')
            return False
            
    except Exception as e:
        print(f'✗ Error: {e}')
        return False

if __name__ == '__main__':
    password = sys.argv[1] if len(sys.argv) > 1 else 'admin123'
    success = reset_admin_password(password=password)
    sys.exit(0 if success else 1)
