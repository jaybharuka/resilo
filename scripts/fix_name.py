import sqlite3
conn = sqlite3.connect('aiops_auth.db')
conn.execute("UPDATE users SET name='System Admin' WHERE email='admin@company.local'")
conn.commit()
conn.close()
