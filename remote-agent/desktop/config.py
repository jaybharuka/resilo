from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".resilo"
CONFIG_FILE = CONFIG_DIR / "desktop_agent.json"

_DEFAULTS: dict[str, Any] = {
    "backend_url": "http://localhost:8000",
    "org_id": "",
    "agent_key": "",
    "label": "",
    "device_id": "",
    "consented": False,
    "autostart": False,
    "interval": 5,
}


def load() -> dict[str, Any]:
    if CONFIG_FILE.exists():
        try:
            with CONFIG_FILE.open() as fh:
                data = json.load(fh)
            return {**_DEFAULTS, **data}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(_DEFAULTS)


def save(cfg: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with CONFIG_FILE.open("w") as fh:
        json.dump(cfg, fh, indent=2)
