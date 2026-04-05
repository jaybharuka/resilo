from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import AuditLog, RemediationJob, SessionLocal
from app.remediation.executor import execute_playbook

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def process_job(db: AsyncSession, job: RemediationJob) -> None:
    job.status = "running"
    job.attempts += 1
    job.updated_at = _now_utc()
    await db.commit()

    try:
        result = await execute_playbook(job.playbook_type, job.payload or {})
        if isinstance(result, dict) and result.get("status") == "failed":
            raise RuntimeError(result.get("error") or "Playbook execution failed")

        job.status = "success"
        job.last_error = None
        db.add(
            AuditLog(
                org_id=(job.payload or {}).get("org_id"),
                action="playbook.job.success",
                resource_type="remediation_job",
                resource_id=str(job.id),
                detail={"playbook_type": job.playbook_type},
            )
        )
    except Exception as exc:
        should_retry = job.attempts < job.max_retries
        job.status = "pending" if should_retry else "failed"
        job.last_error = str(exc)
        if should_retry:
            logger.warning(
                "Job %s failed on attempt %s/%s and will retry: %s",
                job.id,
                job.attempts,
                job.max_retries,
                exc,
            )
        else:
            logger.error(
                "Job %s exhausted retries (%s/%s): %s",
                job.id,
                job.attempts,
                job.max_retries,
                exc,
            )
        db.add(
            AuditLog(
                org_id=(job.payload or {}).get("org_id"),
                action="playbook.job.retry" if should_retry else "playbook.job.failed",
                resource_type="remediation_job",
                resource_id=str(job.id),
                detail={
                    "playbook_type": job.playbook_type,
                    "error": str(exc),
                    "attempts": job.attempts,
                    "max_retries": job.max_retries,
                    "will_retry": should_retry,
                },
            )
        )

    job.updated_at = _now_utc()
    await db.commit()


async def worker_loop(
    db_factory: async_sessionmaker[AsyncSession] = SessionLocal,
    poll_interval: float = 1.0,
    batch_size: int = 5,
) -> None:
    while True:
        async with db_factory() as db:
            jobs_result = await db.execute(
                select(RemediationJob)
                .where(RemediationJob.status == "pending")
                .order_by(RemediationJob.created_at.asc())
                .limit(batch_size)
            )
            jobs = jobs_result.scalars().all()

            for job in jobs:
                await process_job(db, job)

        await asyncio.sleep(poll_interval)


async def run_once(db_factory: async_sessionmaker[AsyncSession] = SessionLocal, batch_size: int = 5) -> None:
    async with db_factory() as db:
        jobs_result = await db.execute(
            select(RemediationJob)
            .where(RemediationJob.status == "pending")
            .order_by(RemediationJob.created_at.asc())
            .limit(batch_size)
        )
        for job in jobs_result.scalars().all():
            await process_job(db, job)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Run remediation queue worker")
    parser.add_argument("--once", action="store_true", help="Process one batch and exit")
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    args = parser.parse_args()

    if args.once:
        asyncio.run(run_once(batch_size=args.batch_size))
        return

    asyncio.run(worker_loop(batch_size=args.batch_size, poll_interval=args.poll_interval))


if __name__ == "__main__":
    main()
