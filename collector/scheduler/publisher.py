"""Transactional outbox drain + due retries. At least once; worker is idempotent."""
from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import select, or_
from collector.storage.models import CollectionJob, OutboxEvent, utc_now


class Publisher:
    def __init__(self, session_factory, broker, max_backlog: int = 10000):
        self.sf, self.broker, self.max_backlog = session_factory, broker, max_backlog

    async def flush(self, limit: int = 100) -> int:
        if await self.broker.backlog() >= self.max_backlog:
            return 0
        count = 0
        # A crash after XADD but before published_at causes a duplicate, safe via Job state.
        with self.sf() as db:
            outbox = db.scalars(select(OutboxEvent).where(OutboxEvent.published_at.is_(None), OutboxEvent.available_at <= utc_now()).order_by(OutboxEvent.priority.desc(), OutboxEvent.created_at).limit(limit)).all()
            for event in outbox:
                job = db.get(CollectionJob, event.job_id)
                if job is None or job.status in {"canceled", "blocked", "completed", "dead_letter"}:
                    event.published_at = utc_now()
                    db.commit()
                    continue
                await self.broker.publish(event.job_id, event.priority)
                event.published_at = utc_now()
                db.commit()
                count += 1
        return count
