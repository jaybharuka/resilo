import pytest

@pytest.mark.asyncio
async def test_playbook_execution():
    from app.remediation.executor import execute_playbook

    result = await execute_playbook("high_cpu", {"cpu": 95})

    assert result["status"] == "success"
