import sqlite3

def patch_api_server():
    with open('api_server.py', 'r', encoding='utf-8') as f:
        content = f.read()

    new_endpoint = '''
@app.route('/users', methods=['GET'])
@auth_token_required
def get_users(current_user):
    # Only admin can list users, but let's be flexible a bit if needed
    if current_user.get('role') != 'admin':
        return jsonify({"error": "unauthorized"}), 403
    try:
        conn = _sqlite3.connect(auth_system.db_path)
        conn.row_factory = _sqlite3.Row
        users_rows = conn.execute("SELECT id, username, email, full_name, role, is_active, created_at, last_login_at FROM users").fetchall()
        users = [dict(r) for r in users_rows]
        return jsonify(users)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/devices', methods=['GET'])'''

    if "@app.route('/users'" not in content:
        content = content.replace("@app.route('/devices', methods=['GET'])", new_endpoint)
        with open('api_server.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print("Patched api_server.py")
    else:
        print("Already patched")

patch_api_server()
