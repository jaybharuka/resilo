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
    raise RuntimeError("DATABASE_URL not set. Copy .env.example to .env and configure your database connection string.")

conn = psycopg2.connect(conn_str)
cur = conn.cursor()

cur.execute("SELECT hashed_password FROM users WHERE email='admin@company.local'")
row = cur.fetchone()
if not row:
    print("No user found for admin@company.local")
else:
    print("Retrieved hash for admin@company.local (not printing for security). Length:", len(row[0]))

cur.close()
conn.close()
