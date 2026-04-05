from app.remediation.playbooks import register_playbook

@register_playbook("high_cpu")
async def high_cpu_playbook(context):
    # simulate action
    return {
        "status": "success",
        "action": "scaled_service"
    }
