import pytest
from sqlalchemy import select
from collector.scheduler.freshness import FreshnessScheduler
from collector.storage.models import CollectionTarget, CollectionJob, OutboxEvent, utc_now


def test_refresh_scheduler_enqueues_once_then_updates_due(rig):
    with rig["sf"].begin() as db:
        t = CollectionTarget(source_id="mock", endpoint="sample", kind="keyword", payload={"keyword": "test"}, enabled=True, next_due_at=utc_now())
        db.add(t)
    n = FreshnessScheduler(rig["sf"]).tick()
    assert n == 1
    assert FreshnessScheduler(rig["sf"]).tick() == 0
    with rig["sf"]() as db:
        assert len(db.scalars(select(CollectionJob)).all()) == 1
