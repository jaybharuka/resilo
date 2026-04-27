import os

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

cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users'")
print("users:", [row[0] for row in cur.fetchall()])

cur.close()
conn.close()
