import pytest
from sqlalchemy import select, func
from collector.errors import PermissionLost, AccessChallenge, RateLimited, PolicyViolation, StorageUnavailable, classify_http
from collector.storage.models import CollectionJob, DataSource, Incident, OutboxEvent, CollectionPolicy
from collector.sessions.credentials import mark_dead
from collector.adapters.legacy_seller import UnimplementedAdapter
from collector.adapters.base import CollectionTask


@pytest.mark.parametrize("status", [301,302,307,401,403])
def test_redirect_or_forbidden_never_retried(status):
    with pytest.raises(PermissionLost):
        classify_http(status)


def test_challenge_and_429_stop():
    with pytest.raises(AccessChallenge):
        classify_http(200, "<html>antibot challenge</html>", "text/html")
    with pytest.raises(RateLimited):
        classify_http(429)


@pytest.mark.asyncio
async def test_source_auth_error_blocks_all_jobs(rig):
    a = rig["jobs"].create(source_id="mock", endpoint="sample", kind="keyword", payload={"simulate_error": "403"}, idempotency_key="a")
    b = rig["jobs"].create(source_id="mock", endpoint="sample", kind="sku", payload={}, idempotency_key="b")
    await rig["publisher"].flush()
    assert await rig["worker"].run_once()
    with rig["sf"]() as db:
        assert db.get(DataSource, "mock").blocked is True
        assert db.get(CollectionJob, a.id).status == "blocked"
        assert db.get(CollectionJob, b.id).status == "blocked"
        assert db.scalar(select(func.count()).select_from(Incident)) == 1


@pytest.mark.asyncio
async def test_bounded_retries_dead_letter(rig):
    with rig["sf"].begin() as db:
        p = db.scalars(select(CollectionPolicy).where(CollectionPolicy.source_id == "mock")).one()
        p.retry_budget = 1
    j = rig["jobs"].create(source_id="mock", endpoint="sample", kind="keyword", payload={"simulate_error": "transient"})
    await rig["publisher"].flush()
    await rig["worker"].run_once()
    with rig["sf"].begin() as db:
        job = db.get(CollectionJob, j.id)
        assert job.status == "retry_wait" and job.attempts == 1
        # Simulate clock reaching the approved finite retry deadline.
        from collector.storage.models import utc_now
        job.next_retry_at = utc_now()
        for e in db.scalars(select(OutboxEvent).where(OutboxEvent.published_at.is_(None))):
            e.available_at = utc_now()
    await rig["publisher"].flush()
    await rig["worker"].run_once()
    with rig["sf"]() as db:
        assert db.get(CollectionJob, j.id).status == "dead_letter"
        assert db.get(CollectionJob, j.id).attempts == 2
        assert len(rig["broker"].dlq) == 1


@pytest.mark.asyncio
async def test_unimplemented_p7_is_explicit():
    with pytest.raises(Exception, match="P7 online"):
        await UnimplementedAdapter().prepare(CollectionTask("job", "seller_p7", "p7", "keyword", {}))


def test_live_source_not_authorized(rig):
    with pytest.raises(PolicyViolation):
        rig["jobs"].create(source_id="seller_p6", endpoint="what_to_sell", kind="sku", payload={})


def test_mark_dead_stops_sources(rig):
    with rig["sf"].begin() as db:
        s = db.get(DataSource, "mock")
        s.credential_ref = "dev/ref"
        mark_dead(db, "dev/ref")
    with rig["sf"]() as db:
        assert db.get(DataSource, "mock").blocked is True


def test_expired_or_missing_secret_reference_blocks_job_creation(rig):
    from datetime import timedelta
    from collector.storage.models import CredentialStatus, utc_now
    with rig["sf"].begin() as db:
        db.get(DataSource,"mock").credential_ref = "vault/dead"
    with pytest.raises(PolicyViolation):
        rig["jobs"].create(source_id="mock",endpoint="sample",kind="sku",payload={})
    with rig["sf"].begin() as db:
        db.add(CredentialStatus(credential_ref="vault/dead",status="active",expires_at=utc_now()-timedelta(minutes=1)))
    with pytest.raises(PolicyViolation):
        rig["jobs"].create(source_id="mock",endpoint="sample",kind="sku",payload={})


def test_agent_proposals_reject_nested_credentials(rig):
    from collector.agents.policy import propose
    with rig["sf"].begin() as db:
        with pytest.raises(PolicyViolation):
            propose(db,"collector_ops","schedule_collection_job",
                    {"payload":{"request":{"Cookie":"sensitive"}}},"test")
