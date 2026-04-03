import os

import psycopg2

try:  # Allow optional .env loading for local development
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

conn_str = os.getenv('DATABASE_URL')
if not conn_str:
    raise RuntimeError("DATABASE_URL not set. Copy .env.example to .env and configure your database connection string.")

conn = psycopg2.connect(conn_str)
cur = conn.cursor()

cur.execute("SELECT id, email, username, role, is_active FROM users")
rows = cur.fetchall()
print("Users in DB:")
for r in rows:
    print(r)

cur.close()
conn.close()
