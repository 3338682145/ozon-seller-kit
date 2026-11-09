import asyncio
import json
import pytest
from sqlalchemy import select, func
from collector.storage.models import Product, Keyword, KeywordProduct, JobEvent, CollectionJob


@pytest.mark.asyncio
async def test_mock_e2e_storage_keywords_agents_and_raw(rig):
    job = rig["jobs"].create(source_id="mock", endpoint="sample", kind="keyword", payload={"keyword": "антистресс"})
    assert await rig["publisher"].flush() == 1
    assert await rig["worker"].run_once("worker-a") is True
    with rig["sf"]() as db:
        item = db.get(CollectionJob, job.id)
        assert item.status == "completed" and item.attempts == 1
        assert item.raw_object_key.endswith(f"{job.id}.json")
        assert db.scalar(select(func.count()).select_from(Product)) == 3
        assert db.scalar(select(func.count()).select_from(Keyword)) == 2
        assert db.scalar(select(func.count()).select_from(KeywordProduct)) == 3
        assert db.scalar(select(func.count()).select_from(JobEvent).where(JobEvent.event == "completed")) == 1
    assert len(rig["objects"].objects) == 1
    assert len(rig["facts"].tables["fact_serp_observation"]) == 3
    assert len(rig["facts"].tables["fact_keyword_daily"]) == 2
    assert json.loads(next(iter(rig["objects"].objects.values())))["records"][0]["sku"] == "101001"


@pytest.mark.asyncio
async def test_worker_reclaim_pending_after_crash(rig):
    job = rig["jobs"].create(source_id="mock", endpoint="sample", kind="sku", payload={"sku": "101001"})
    await rig["publisher"].flush()
    first = await rig["broker"].receive("crashed-worker")
    assert first is not None and len(rig["broker"].pending) == 1
    assert await rig["worker"].run_once("replacement-worker", reclaim=True, idle_ms=0)
    assert len(rig["broker"].pending) == 0
    with rig["sf"]() as db:
        assert db.get(CollectionJob, job.id).status == "completed"


@pytest.mark.asyncio
async def test_idempotent_job_and_duplicate_delivery(rig):
    args = {"source_id": "mock", "endpoint": "sample", "kind": "sku", "payload": {"sku": "101001"}}
    one = rig["jobs"].create(**args, idempotency_key="import-once")
    two = rig["jobs"].create(**args, idempotency_key="import-once")
    assert one.id == two.id
    assert await rig["publisher"].flush() == 1
    await rig["worker"].run_once()
    await rig["broker"].publish(one.id)
    await rig["worker"].run_once()
    with rig["sf"]() as db:
        assert db.scalar(select(func.count()).select_from(JobEvent).where(JobEvent.event == "completed")) == 1
        assert db.scalar(select(func.count()).select_from(KeywordProduct)) == 3
    assert len(rig["facts"].tables["fact_serp_observation"]) == 3
