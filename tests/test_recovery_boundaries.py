"""Fault-injection tests for lease recovery, storage consistency and access gates."""
from __future__ import annotations
import asyncio
from datetime import timedelta
import pytest
from sqlalchemy import select, func
from collector.adapters.mock import MockAdapter
from collector.errors import PolicyViolation, StorageUnavailable
from collector.pipeline.runner import Pipeline
from collector.scheduler.publisher import Publisher
from collector.storage.facts import MemoryFactsSink
from collector.storage.models import CollectionJob, DataSource, JobEvent, WorkerHeartbeat, utc_now
from collector.storage.objects import MemoryObjectStore
from collector.workers.runtime import Worker


class WaitingAdapter(MockAdapter):
    def __init__(self, file_path, entered: asyncio.Event, release: asyncio.Event, calls: list):
        super().__init__(file_path)
        self.entered, self.release, self.calls = entered, release, calls

    async def fetch(self, task):
        self.calls.append(task.job_id)
        self.entered.set()
        await self.release.wait()
        return await super().fetch(task)


@pytest.mark.asyncio
async def test_duplicate_delivery_does_not_steal_live_lease_or_drop_pending(rig):
    job = rig["jobs"].create(source_id="mock", endpoint="sample", kind="sku", payload={})
    await rig["publisher"].flush()
    await rig["broker"].publish(job.id)
    started, release, calls = asyncio.Event(), asyncio.Event(), []
    adapter = lambda src, policy: WaitingAdapter(rig["sample"], started, release, calls)
    first = Worker(rig["sf"], rig["broker"], adapter, rig["pipeline"])
    second = Worker(rig["sf"], rig["broker"], adapter, rig["pipeline"])
    task = asyncio.create_task(first.run_once("worker-A"))
    await asyncio.wait_for(started.wait(), 3)
    # The duplicate message stays in Redis PEL; it must NOT be ACKed.
    assert not await second.run_once("worker-B")
    assert len(rig["broker"].pending) == 2
    release.set()
    assert await task
    assert await second.run_once("worker-B", reclaim=True)
    assert calls == [job.id]
    with rig["sf"]() as db:
        row = db.get(CollectionJob, job.id)
        assert (row.status, row.attempts, row.lease_owner) == ("completed", 1, None)
        assert db.scalar(select(func.count()).select_from(JobEvent).where(JobEvent.event == "claimed")) == 1


@pytest.mark.asyncio
async def test_running_lease_expiry_recovers_worker_crash(rig):
    job = rig["jobs"].create(source_id="mock", endpoint="sample", kind="keyword", payload={})
    await rig["publisher"].flush()
    assert await rig["broker"].receive("dead-worker")
    with rig["sf"].begin() as db:
        current = db.get(CollectionJob, job.id)
        current.status = "running"
        current.lease_owner = "dead-worker:abandoned"
        current.attempts = 1
        current.lease_expires_at = utc_now() + timedelta(seconds=100)
    assert not await rig["worker"].run_once("rescue", reclaim=True)
    assert len(rig["broker"].pending) == 1
    with rig["sf"].begin() as db:
        db.get(CollectionJob, job.id).lease_expires_at = utc_now() - timedelta(seconds=1)
    assert await rig["worker"].run_once("rescue", reclaim=True)
    with rig["sf"]() as db:
        assert db.get(CollectionJob, job.id).status == "completed"
        assert db.get(CollectionJob, job.id).attempts == 2
        assert db.get(WorkerHeartbeat, "rescue").state == "idle"


class FailingStore(MemoryObjectStore):
    def put(self, bucket, key, data):
        raise StorageUnavailable("forced object outage")


class FailingFacts(MemoryFactsSink):
    def write(self, records, gold):
        raise StorageUnavailable("forced ClickHouse outage")


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_in", ["bronze", "facts"])
async def test_external_storage_failure_never_commits_completed_job(rig, fail_in):
    from collector.storage.models import Product
    j = rig["jobs"].create(source_id="mock", endpoint="sample", kind="keyword", payload={})
    await rig["publisher"].flush()
    p = Pipeline(FailingStore() if fail_in == "bronze" else rig["objects"],
                 FailingFacts() if fail_in == "facts" else rig["facts"], "mock-v1")
    w = Worker(rig["sf"], rig["broker"], lambda src, policy: MockAdapter(rig["sample"]), p)
    assert await w.run_once()
    with rig["sf"]() as db:
        assert db.get(CollectionJob, j.id).status == "retry_wait"
        assert db.scalar(select(func.count()).select_from(Product)) == 0
    # Re-process after storage recovery. Retries have finite policy budget.
    with rig["sf"].begin() as db:
        from collector.storage.models import OutboxEvent
        db.get(CollectionJob, j.id).next_retry_at = utc_now()
        for e in db.scalars(select(OutboxEvent).where(OutboxEvent.published_at.is_(None))):
            e.available_at = utc_now()
    await rig["publisher"].flush()
    assert await rig["worker"].run_once()
    with rig["sf"]() as db:
        assert db.get(CollectionJob, j.id).status == "completed"


def test_reject_nested_credential_material(rig):
    with pytest.raises(PolicyViolation):
        rig["jobs"].create(source_id="mock", endpoint="sample", kind="sku",
                           payload={"filters": [{"session": {"access_token": "secret"}}]})


@pytest.mark.asyncio
async def test_operator_pause_recovery_requires_verified_policy_and_requeues(rig):
    j = rig["jobs"].create(source_id="mock", endpoint="sample", kind="sku", payload={})
    assert rig["jobs"].pause_source("mock", reason="operator_paused")
    assert rig["jobs"].resume_source("mock")
    with rig["sf"]() as db:
        assert db.get(DataSource, "mock").enabled
        assert db.get(CollectionJob, j.id).status == "pending"
    # Outbox may contain both the initial enqueue and the resume entry.
    await rig["publisher"].flush()
    while await rig["worker"].run_once():
        pass
    with rig["sf"]() as db:
        assert db.get(CollectionJob, j.id).status == "completed"
    # Automatic recovery from an authentication block is forbidden.
    with rig["sf"].begin() as db:
        src = db.get(DataSource, "mock")
        src.enabled, src.blocked, src.blocked_reason = False, True, "authorization_lost"
    assert not rig["jobs"].resume_source("mock")
