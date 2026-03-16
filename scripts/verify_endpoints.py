import importlib.util
from pathlib import Path


def load_app():
    backend_path = Path(r"D:\AIOps Bot\aiops_chatbot_backend.py")
    spec = importlib.util.spec_from_file_location("aiops_chatbot_backend", str(backend_path))
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod.app


def main():
    app = load_app()
    with app.test_client() as client:
        r1 = client.get('/health')
        r2 = client.get('/devices')
        r3 = client.get('/company-stats')
        print('STATUS /health =', r1.status_code)
        print('JSON   /health =', r1.json)
        print('STATUS /devices =', r2.status_code)
        print('JSON   /devices =', r2.json)
        print('STATUS /company-stats =', r3.status_code)
        print('JSON   /company-stats =', r3.json)


if __name__ == '__main__':
    main()
