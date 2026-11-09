"""Bounded async Worker. Never ACK on database outage; XAUTOCLAIM recovers it."""
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from collector.adapters.base import CollectionTask
from collector.errors import CollectionError, DataQualityError, PermissionLost, SourceNotImplemented, StorageUnavailable
from collector.monitoring.incidents import report_incident
from collector.retry.policy import should_retry, retry_at
from collector.storage.models import (CollectionJob, CollectionPolicy, DataSource, JobEvent, OutboxEvent, utc_now)


@asynccontextmanager
async def no_permit():
    yield


class Worker:
    def __init__(self, session_factory, broker, adapter_factory, pipeline, permit_factory=None):
        self.sf, self.broker, self.adapter_factory, self.pipeline = session_factory, broker, adapter_factory, pipeline
        self.permit_factory = permit_factory or (lambda source, policy: no_permit())

    async def run_once(self, consumer: str = "worker-1", *, reclaim: bool = False, idle_ms: int = 60000) -> bool:
        msg = await self.broker.recover(consumer, idle_ms=idle_ms) if reclaim else await self.broker.receive(consumer)
        if msg is None:
            return False
        try:
            await self._process(msg.job_id, consumer)
        except SQLAlchemyError:
            # Do not ACK: the DB is the source of truth, stop consuming until recovery.
            raise
        else:
            await self.broker.ack(msg)
        return True

    async def _process(self, job_id: str, consumer: str) -> None:
        with self.sf.begin() as db:
            job = db.get(CollectionJob, job_id)
            if job is None or job.status in {"completed", "canceled", "dead_letter", "blocked"}:
                return
            source = db.get(DataSource, job.source_id)
            policy = db.scalar(select(CollectionPolicy).where(CollectionPolicy.source_id == job.source_id, CollectionPolicy.endpoint == job.endpoint))
            if not source or not policy or not source.enabled or source.blocked or not source.license_verified or not policy.enabled or not policy.limit_verified or source.authorization_scope != policy.authorization_scope:
                job.status, job.last_error_code = "blocked", "policy_denied"
                return
            if job.status == "retry_wait" and job.next_retry_at is not None:
                due = job.next_retry_at
                if due.tzinfo is None:
                    due = due.replace(tzinfo=utc_now().tzinfo)
                if due > utc_now():
                    return  # publisher will enqueue only when due
            job.status, job.lease_owner = "running", consumer
            job.attempts += 1
            db.add(JobEvent(job_id=job.id, event="claimed", detail={"attempt": job.attempts}))
            task = CollectionTask(job.id, job.source_id, job.endpoint, job.kind, job.payload)
            source_id = source.source_id
            max_timeout = policy.timeout_seconds
        try:
            adapter = self.adapter_factory(source_id, policy)
            await adapter.prepare(task)
            async with self.permit_factory(source_id, policy):
                response = await asyncio.wait_for(adapter.fetch(task), timeout=max_timeout)
            records = await adapter.validate(await adapter.parse(response))
            key, digest = self.pipeline.save_raw(job_id, response)
            with self.sf.begin() as db:
                job = db.get(CollectionJob, job_id)
                if job.status in {"canceled", "blocked"}:
                    return
                counts = self.pipeline.ingest(db, job_id, source_id, records)
                job.raw_object_key, job.raw_sha256 = key, digest
                job.status, job.lease_owner, job.completed_at = "completed", None, utc_now()
                job.checkpoint = {"stored_records": counts["products"], "raw_sha256": digest}
                db.add(JobEvent(job_id=job_id, event="completed", detail=counts))
        except asyncio.TimeoutError:
            await self._failed(job_id, StorageUnavailable("bounded fetch deadline"), policy.retry_budget)
        except CollectionError as exc:
            await self._failed(job_id, exc, policy.retry_budget)
        # Unexpected errors are not blindly retried, and error text is not logged.
        except (TypeError, KeyError, ValueError, ImportError) as exc:
            await self._failed(job_id, DataQualityError(type(exc).__name__), policy.retry_budget)

    async def _failed(self, job_id: str, error: CollectionError, budget: int):
        send_dlq = False
        with self.sf.begin() as db:
            job = db.get(CollectionJob, job_id)
            if job.status in {"canceled", "blocked", "completed"}:
                return
            job.last_error_code, job.last_error, job.lease_owner = error.code, type(error).__name__, None
            if error.block_source:
                source = db.get(DataSource, job.source_id)
                source.enabled, source.blocked, source.blocked_reason = False, True, error.code
                db.query(CollectionJob).filter(CollectionJob.source_id == job.source_id, CollectionJob.status.in_(["pending", "retry_wait", "running"])).update({"status": "blocked", "last_error_code": error.code}, synchronize_session=False)
                job.status = "blocked"
                report_incident(db, job.source_id, error.code, severity="P2")
            elif should_retry(error, job.attempts, budget):
                job.status, job.next_retry_at = "retry_wait", retry_at(job.attempts)
                db.add(OutboxEvent(job_id=job.id, priority=job.priority, available_at=job.next_retry_at))
            else:
                job.status = "dead_letter"
                send_dlq = True
                report_incident(db, job.source_id, error.code, severity="P3")
            db.add(JobEvent(job_id=job.id, event=job.status, detail={"code": error.code, "attempt": job.attempts}))
        if send_dlq:
            await self.broker.dead_letter(job_id, error.code)
