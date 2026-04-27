import json
import os
import urllib.request

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

LOGIN_URL = os.getenv('LOGIN_TEST_URL', 'http://localhost:5000/auth/login')
LOGIN_EMAIL = os.getenv('LOGIN_TEST_EMAIL', 'admin@company.local')
LOGIN_PASSWORD = os.getenv('LOGIN_TEST_PASSWORD') or os.getenv('ADMIN_DEFAULT_PASSWORD', '')

req = urllib.request.Request(
    LOGIN_URL,
    data=json.dumps({'email': LOGIN_EMAIL, 'password': LOGIN_PASSWORD}).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)

try:
    res = urllib.request.urlopen(req)
    print("Success:", res.read()[:200])
except Exception as e:
    print("Error:", e)
    if hasattr(e, 'read'):
        print(e.read()[:200])
