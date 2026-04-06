from app.remediation.playbooks import register_playbook


@register_playbook("high_cpu")
async def high_cpu_playbook(context):
    # simulate action
    return {
        "status": "success",
        "action": "scaled_service"
    }

@register_playbook("high_error_rate")
async def high_error_rate_playbook(context):
    return {
        "status": "success",
        "action": "rollback_deployment"
    }

@register_playbook("disk_full")
async def disk_full_playbook(context):
    return {
        "status": "success",
        "action": "cleanup_logs"
    }
