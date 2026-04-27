import os

import bcrypt
import psycopg2

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

conn_str = os.getenv('DATABASE_URL')
if not conn_str:
    raise RuntimeError('DATABASE_URL not set. Copy .env.example to .env and configure your database connection string.')

_raw_password = os.getenv('RESET_PASSWORD_NEW')
if not _raw_password:
    raise RuntimeError(
        'RESET_PASSWORD_NEW is not set. Set it in your .env file or environment before running this script.\n'
        'Example: RESET_PASSWORD_NEW=<new-password> python update_db.py'
    )
new_password = _raw_password.encode()
email = os.getenv('RESET_PASSWORD_EMAIL', 'admin@company.local')

hashed = bcrypt.hashpw(new_password, bcrypt.gensalt()).decode('utf-8')

conn = psycopg2.connect(conn_str)
cur = conn.cursor()

cur.execute("UPDATE users SET hashed_password=%s, must_change_password=FALSE WHERE email=%s", (hashed, email))
conn.commit()
print('Rows updated:', cur.rowcount)

cur.execute("UPDATE sessions SET is_revoked = TRUE WHERE user_id IN (SELECT id FROM users WHERE email=%s)", (email,))
conn.commit()

cur.close()
conn.close()
