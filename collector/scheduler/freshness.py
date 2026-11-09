"""Interval scheduling strictly bounded by verified collection_policies.

Only explicit CollectionTarget rows create recurring jobs. Crawlab batch IDs are
metadata, not a competing Redis scheduler. A target is idempotent per due epoch.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from collector.scheduler.jobs import JobService
from collector.storage.models import CollectionTarget, CollectionPolicy, utc_now
from collector.errors import PolicyViolation


class FreshnessScheduler:
    def __init__(self, session_factory):
        self.sf = session_factory
        self.jobs = JobService(session_factory)

    def tick(self, limit: int = 100) -> int:
        with self.sf() as db:
            targets = db.scalars(select(CollectionTarget).where(CollectionTarget.enabled.is_(True), CollectionTarget.next_due_at <= utc_now()).order_by(CollectionTarget.next_due_at).limit(limit)).all()
            # Decode ORM objects into values outside the transaction.
            due = [(x.id, x.source_id, x.endpoint, x.kind, x.payload, x.next_due_at) for x in targets]
        count = 0
        for target_id, source_id, endpoint, kind, payload, due_at in due:
            policy = None
            with self.sf() as db:
                policy = db.scalar(select(CollectionPolicy).where(CollectionPolicy.source_id == source_id, CollectionPolicy.endpoint == endpoint))
                period = policy.refresh_interval if policy and policy.enabled and policy.limit_verified else None
            if period is None or period <= 0:
                continue
            # Stable idempotency key lets a scheduler crash before due-update retry safely.
            try:
                job = self.jobs.create(source_id=source_id, endpoint=endpoint, kind=kind, payload=payload,
                                       idempotency_key=f"target:{target_id}:{due_at.isoformat()}")
            except PolicyViolation:
                continue
            with self.sf.begin() as db:
                current = db.get(CollectionTarget, target_id)
                if current and current.enabled and current.next_due_at == due_at:
                    # Catch up at most one interval per tick; no backlog flood.
                    current.next_due_at = max(utc_now(), (due_at.replace(tzinfo=timezone.utc) if due_at.tzinfo is None else due_at) + timedelta(seconds=period))
                    current.last_job_id = job.id
                    count += 1
        return count
