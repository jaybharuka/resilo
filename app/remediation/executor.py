import app.remediation.sample_playbooks
from app.remediation.playbooks import PLAYBOOKS

async def execute_playbook(playbook_type: str, context: dict):
    playbook = PLAYBOOKS.get(playbook_type)

    if not playbook:
        raise ValueError(f"Unknown playbook: {playbook_type}")

    return await playbook(context)

