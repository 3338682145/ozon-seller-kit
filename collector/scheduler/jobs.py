"""PG is the source of truth; Crawlab owns batches, not Redis child tasks."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from collector.errors import PolicyViolation
from collector.storage.models import (CollectionJob, CollectionPolicy, DataSource, JobEvent, OutboxEvent, utc_now)

VALID_KINDS = {"keyword", "sku", "category", "shop", "import"}
FINAL = {"completed", "canceled", "blocked", "dead_letter"}


def canonical_payload(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def fingerprint(source_id: str, endpoint: str, kind: str, payload: dict, idempotency_key: str | None) -> str:
    # Explicit idempotency key can be reused across requests; daily default avoids duplicate storms.
    material = idempotency_key or f"{datetime.now(timezone.utc).date().isoformat()}:{canonical_payload(payload)}"
    return hashlib.sha256(f"{source_id}:{endpoint}:{kind}:{material}".encode()).hexdigest()


class JobService:
    def __init__(self, session_factory):
        self.sf = session_factory

    def create(self, *, source_id: str, endpoint: str, kind: str, payload: dict, batch_id: str | None = None, priority: int | None = None, idempotency_key: str | None = None) -> CollectionJob:
        if kind not in VALID_KINDS:
            raise PolicyViolation("invalid job kind")
        if not isinstance(payload, dict) or any(k.lower() in {"cookie", "token", "authorization", "password", "secret", "api_key"} for k in payload):
            raise PolicyViolation("credential material is prohibited in job payload")
        if priority is not None and not -10 <= priority <= 10:
            raise PolicyViolation("priority must be -10..10")
        fp = fingerprint(source_id, endpoint, kind, payload, idempotency_key)
        with self.sf.begin() as db:
            existing = db.scalar(select(CollectionJob).where(CollectionJob.fingerprint == fp))
            if existing:
                return existing
            source = db.get(DataSource, source_id)
            policy = db.scalar(select(CollectionPolicy).where(CollectionPolicy.source_id == source_id, CollectionPolicy.endpoint == endpoint))
            if not source or not source.enabled or source.blocked or not policy or not policy.enabled:
                raise PolicyViolation("source/policy disabled or blocked")
            if not source.license_verified or not policy.limit_verified:
                raise PolicyViolation("license/rate limit not verified")
            if source.authorization_scope != policy.authorization_scope:
                raise PolicyViolation("authorization scope differs from verified policy")
            job = CollectionJob(source_id=source_id, endpoint=endpoint, kind=kind, payload=payload,
                                fingerprint=fp, batch_id=batch_id, priority=priority if priority is not None else policy.priority)
            db.add(job)
            db.flush()
            db.add(OutboxEvent(job_id=job.id, priority=job.priority))
            db.add(JobEvent(job_id=job.id, event="created", detail={"batch_id": batch_id}))
            return job

    def cancel(self, job_id: str) -> CollectionJob | None:
        with self.sf.begin() as db:
            job = db.get(CollectionJob, job_id)
            if job and job.status not in FINAL:
                job.status = "canceled"
                db.add(JobEvent(job_id=job.id, event="canceled"))
            return job

    def pause_source(self, source_id: str, *, reason: str = "operator_paused") -> bool:
        with self.sf.begin() as db:
            source = db.get(DataSource, source_id)
            if not source:
                return False
            source.enabled = False
            source.blocked = True
            source.blocked_reason = reason[:256]
            db.query(CollectionJob).filter(CollectionJob.source_id == source_id, CollectionJob.status.in_(["pending", "retry_wait", "running"])).update({"status": "blocked", "last_error_code": "source_blocked"}, synchronize_session=False)
            return True
