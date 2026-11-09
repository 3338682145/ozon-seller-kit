"""Bounded async Worker. Never ACK on database outage; XAUTOCLAIM recovers it."""
from __future__ import annotations
import asyncio
import time
from datetime import timedelta
from uuid import uuid4
from contextlib import asynccontextmanager
from sqlalchemy import select, update, and_, or_
from sqlalchemy.exc import SQLAlchemyError
from collector.adapters.base import CollectionTask
from collector.errors import CollectionError, DataQualityError, PermissionLost, SourceNotImplemented, StorageUnavailable
from collector.monitoring.incidents import report_incident
from collector.retry.policy import should_retry, retry_at
from collector.storage.models import (CollectionJob, CollectionPolicy, DataSource, JobEvent, OutboxEvent, WorkerHeartbeat, utc_now)


@asynccontextmanager
async def no_permit():
    yield


class Worker:
    def __init__(self, session_factory, broker, adapter_factory, pipeline, permit_factory=None):
        self.sf, self.broker, self.adapter_factory, self.pipeline = session_factory, broker, adapter_factory, pipeline
        self.permit_factory = permit_factory or (lambda source, policy: no_permit())
        self._heartbeat_at = 0.0

    def heartbeat(self, consumer: str, state: str, job_id: str | None = None, force: bool = False):
        if not force and time.monotonic() - self._heartbeat_at < 15:
            return
        with self.sf.begin() as db:
            heartbeat = db.get(WorkerHeartbeat, consumer)
            if heartbeat is None:
                heartbeat = WorkerHeartbeat(worker_id=consumer)
                db.add(heartbeat)
            heartbeat.last_seen_at = utc_now()
            heartbeat.state, heartbeat.last_job_id = state, job_id
        self._heartbeat_at = time.monotonic()

    async def run_once(self, consumer: str = "worker-1", *, reclaim: bool = False, idle_ms: int = 60000) -> bool:
        msg = await self.broker.recover(consumer, idle_ms=idle_ms) if reclaim else await self.broker.receive(consumer)
        if msg is None:
            self.heartbeat(consumer, "idle")
            return False
        self.heartbeat(consumer, "running", msg.job_id, force=True)
        try:
            should_ack = await self._process(msg.job_id, consumer)
        except SQLAlchemyError:
            # Do not ACK: the DB is the source of truth, stop consuming until recovery.
            raise
        else:
            if should_ack:
                await self.broker.ack(msg)
        finally:
            self.heartbeat(consumer, "idle", force=True)
        return should_ack

    async def _process(self, job_id: str, consumer: str) -> bool:
        """Atomically own a leased job or leave its Redis PEL entry un-ACKed.

        A stale worker may finish late: lease-token comparison before silver/fact
        writes prevents its result from overwriting a recovery worker's result.
        """
        token = f"{consumer}:{uuid4()}"
        with self.sf.begin() as db:
            job = db.get(CollectionJob, job_id)
            if job is None or job.status in {"completed", "canceled", "dead_letter", "blocked"}:
                return True
            source = db.get(DataSource, job.source_id)
            policy = db.scalar(select(CollectionPolicy).where(CollectionPolicy.source_id == job.source_id, CollectionPolicy.endpoint == job.endpoint))
            if not source or not policy or not source.enabled or source.blocked or not source.license_verified or not policy.enabled or not policy.limit_verified or source.authorization_scope != policy.authorization_scope:
                job.status, job.last_error_code = "blocked", "policy_denied"
                return True
            if job.status == "retry_wait" and job.next_retry_at is not None:
                due = job.next_retry_at
                if due.tzinfo is None:
                    due = due.replace(tzinfo=utc_now().tzinfo)
                if due > utc_now():
                    return True  # retry outbox owns future enqueue
            now = utc_now()
            lease = now + timedelta(seconds=max(policy.timeout_seconds + 30, 60))
            # The UPDATE guard is evaluated atomically in PostgreSQL, even when
            # multiple at-least-once deliveries race for the same job.
            stmt = (update(CollectionJob)
                .where(CollectionJob.id == job_id)
                .where(or_(CollectionJob.status.in_(["pending", "retry_wait"]),
                    and_(CollectionJob.status == "running",
                         or_(CollectionJob.lease_expires_at.is_(None), CollectionJob.lease_expires_at <= now))))
                .values(status="running", lease_owner=token, lease_expires_at=lease,
                        attempts=CollectionJob.attempts + 1).execution_options(synchronize_session=False))
            if db.execute(stmt).rowcount != 1:
                # Another worker's lease is alive. In particular, DO NOT ACK the
                # only pending Redis delivery of a worker which may have crashed.
                return False
            db.add(JobEvent(job_id=job.id, event="claimed", detail={"attempt": job.attempts + 1}))
            task = CollectionTask(job.id, job.source_id, job.endpoint, job.kind, job.payload)
            source_id = source.source_id
            max_timeout = policy.timeout_seconds
        try:
            adapter = self.adapter_factory(source_id, policy)
            await adapter.prepare(task)
            async with self.permit_factory(source_id, policy):
                response = await asyncio.wait_for(adapter.fetch(task), timeout=max_timeout)
            # Bronze happens *before* parsing, so malformed source snapshots can
            # be inspected after a parse/validation incident.
            key, digest = self.pipeline.save_raw(job_id, response)
            with self.sf.begin() as db:
                job = db.get(CollectionJob, job_id)
                if job.status != "running" or job.lease_owner != token:
                    return True
                job.raw_object_key, job.raw_sha256 = key, digest
            records = await adapter.validate(await adapter.parse(response))
            with self.sf.begin() as db:
                job = db.get(CollectionJob, job_id)
                if job.status != "running" or job.lease_owner != token:
                    return True  # lease was superseded; discard late result
                counts = self.pipeline.ingest(db, job_id, source_id, records)
                job.status, job.lease_owner, job.lease_expires_at, job.completed_at = "completed", None, None, utc_now()
                job.checkpoint = {"stored_records": counts["products"], "raw_sha256": digest, "dataset_version": self.pipeline.dataset_version}
                db.add(JobEvent(job_id=job_id, event="completed", detail=counts))
        except asyncio.TimeoutError:
            await self._failed(job_id, StorageUnavailable("bounded fetch deadline"), policy.retry_budget, token)
        except CollectionError as exc:
            await self._failed(job_id, exc, policy.retry_budget, token)
        # Unexpected errors are not blindly retried, and error text is not logged.
        except (TypeError, KeyError, ValueError, ImportError) as exc:
            await self._failed(job_id, DataQualityError(type(exc).__name__), policy.retry_budget, token)
        return True

    async def _failed(self, job_id: str, error: CollectionError, budget: int, token: str):
        send_dlq = False
        with self.sf.begin() as db:
            job = db.get(CollectionJob, job_id)
            if job.status != "running" or job.lease_owner != token:
                return  # recovery worker or cancellation won the lease
            job.last_error_code, job.last_error, job.lease_owner, job.lease_expires_at = error.code, type(error).__name__, None, None
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
                report_incident(db, job.source_id, error.code, severity="P1" if error.code == "storage_unavailable" else "P3")
            db.add(JobEvent(job_id=job.id, event=job.status, detail={"code": error.code, "attempt": job.attempts}))
        if send_dlq:
            await self.broker.dead_letter(job_id, error.code)
