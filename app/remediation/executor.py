import asyncio

import app.remediation.sample_playbooks
from app.remediation.playbooks import PLAYBOOKS

MAX_RETRIES = 3


async def execute_playbook(playbook_type: str, context: dict):
    playbook = PLAYBOOKS.get(playbook_type)

    if not playbook:
        raise ValueError(f"Unknown playbook: {playbook_type}")

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = await playbook(context)

            return {
                "status": "success",
                "result": result,
                "attempt": attempt,
                "rollback": result.get("rollback") if isinstance(result, dict) else None,
            }

        except Exception as e:
            last_error = e
            await asyncio.sleep(1)

    return {
        "status": "failed",
        "error": str(last_error),
        "attempt": MAX_RETRIES,
        "rollback": None,
    }
