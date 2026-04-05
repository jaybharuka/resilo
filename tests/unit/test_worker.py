from __future__ import annotations

import pytest

from app.core.database import RemediationJob
from app.remediation import worker


class FakeDB:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

    def add(self, obj: object) -> None:
        self.added.append(obj)


@pytest.mark.asyncio
async def test_process_job_marks_success(monkeypatch):
    async def fake_execute_playbook(playbook_type: str, context: dict):
        return {"status": "success", "result": {"action": "scaled_service"}}

    monkeypatch.setattr(worker, "execute_playbook", fake_execute_playbook)

    db = FakeDB()
    job = RemediationJob(
        id=1,
        alert_id="alert-1",
        playbook_type="high_cpu",
        status="pending",
        attempts=0,
        max_retries=3,
        payload={"org_id": "org-1"},
    )

    await worker.process_job(db, job)

    assert job.status == "success"
    assert job.attempts == 1
    assert job.last_error is None
    assert db.commits >= 2


@pytest.mark.asyncio
async def test_process_job_requeues_before_retry_exhausted(monkeypatch):
    async def fake_execute_playbook(playbook_type: str, context: dict):
        return {"status": "failed", "error": "boom"}

    monkeypatch.setattr(worker, "execute_playbook", fake_execute_playbook)

    db = FakeDB()
    job = RemediationJob(
        id=2,
        alert_id="alert-2",
        playbook_type="high_error_rate",
        status="pending",
        attempts=0,
        max_retries=3,
        payload={"org_id": "org-1"},
    )

    await worker.process_job(db, job)

    assert job.status == "pending"
    assert job.attempts == 1
    assert job.last_error is not None


@pytest.mark.asyncio
async def test_process_job_fails_after_retry_exhausted(monkeypatch):
    async def fake_execute_playbook(playbook_type: str, context: dict):
        raise RuntimeError("playbook crashed")

    monkeypatch.setattr(worker, "execute_playbook", fake_execute_playbook)

    db = FakeDB()
    job = RemediationJob(
        id=3,
        alert_id="alert-3",
        playbook_type="disk_full",
        status="pending",
        attempts=2,
        max_retries=3,
        payload={"org_id": "org-1"},
    )

    await worker.process_job(db, job)

    assert job.status == "failed"
    assert job.attempts == 3
    assert "playbook crashed" in (job.last_error or "")
