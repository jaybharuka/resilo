from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.core.database import RemediationJob
from app.remediation import worker


class FakeSession:
    pass


class FakeSessionFactory:
    def __init__(self) -> None:
        self._session = FakeSession()

    @asynccontextmanager
    async def __call__(self):
        yield self._session


class FakeClaimResult:
    def __init__(self, jobs):
        self._jobs = jobs

    class _Scalars:
        def __init__(self, jobs):
            self._jobs = jobs

        def all(self):
            return self._jobs

    def scalars(self):
        return FakeClaimResult._Scalars(self._jobs)


class FakeClaimSession:
    def __init__(self, jobs=None) -> None:
        self.statement = None
        self.jobs = jobs or []

    @asynccontextmanager
    async def begin(self):
        yield

    async def execute(self, statement):
        self.statement = statement
        return FakeClaimResult(self.jobs)


@pytest.mark.asyncio
async def test_no_double_processing(monkeypatch):
    shared_jobs = [SimpleNamespace(id=1)]
    claim_lock = asyncio.Lock()
    processed_ids: list[int] = []

    async def fake_claim_pending_jobs(db, batch_size, lease_timeout_seconds=300):
        async with claim_lock:
            if shared_jobs:
                return [shared_jobs.pop(0)]
        return []

    async def fake_process_job(db, job):
        await asyncio.sleep(0)
        processed_ids.append(job.id)

    monkeypatch.setattr(worker, "claim_pending_jobs", fake_claim_pending_jobs)
    monkeypatch.setattr(worker, "process_job", fake_process_job)

    db_factory = FakeSessionFactory()
    await asyncio.gather(
        worker.run_once(db_factory=db_factory, batch_size=5),
        worker.run_once(db_factory=db_factory, batch_size=5),
    )

    assert processed_ids == [1]


@pytest.mark.asyncio
async def test_claim_query_uses_skip_locked():
    fake_db = FakeClaimSession()

    jobs = await worker.claim_pending_jobs(fake_db, batch_size=5, lease_timeout_seconds=300)

    assert jobs == []
    sql = str(
        fake_db.statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "ORDER BY remediation_jobs.created_at ASC" in sql
    assert "LIMIT 5" in sql


@pytest.mark.asyncio
async def test_stale_running_job_is_reclaimed():
    stale_job = RemediationJob(
        id=10,
        alert_id="alert-10",
        playbook_type="high_cpu",
        status="running",
        attempts=1,
        max_retries=3,
        payload={"org_id": "org-1"},
    )

    fake_db = FakeClaimSession(jobs=[stale_job])
    claimed_jobs = await worker.claim_pending_jobs(fake_db, batch_size=5, lease_timeout_seconds=300)

    assert len(claimed_jobs) == 1
    assert claimed_jobs[0].id == 10
    assert claimed_jobs[0].status == "running"
    assert claimed_jobs[0].attempts == 2
