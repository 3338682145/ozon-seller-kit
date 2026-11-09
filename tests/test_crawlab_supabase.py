"""Mock-only rollout tests; never connect to live Ozon or Supabase."""
from __future__ import annotations

from pathlib import Path
import json
import re
import sys

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from crawlab_submit import submit, wait_for_batch, _idempotency_key, _safe_url
from supabase.verify_connection import validate_supabase_url
from collector.api import create_app
from collector.config import Settings
from collector.storage.database import make_session_factory, seed_mock
from collector.storage.models import CollectionJob
from collector.scheduler.jobs import JobService


def _tasks():
    return [{"source_id": "mock", "endpoint": "sample", "kind": "keyword", "payload": {"keyword": "антистресс"}}]


def _url(user="collector_runtime.project", ssl="require"):
    return f"postgresql+psycopg://{user}:password@pooler.example.org:5432/postgres?sslmode={ssl}"


def test_external_supabase_url_requires_tls_private_schema_and_low_privilege_role():
    validate_supabase_url(_url())
    for url in (
        _url(ssl="disable"),
        _url(user="postgres.project"),
        "sqlite+pysqlite:///:memory:",
        "postgresql+psycopg://collector_runtime@localhost/postgres?sslmode=require",
    ):
        with pytest.raises(ValueError):
            validate_supabase_url(url)
    validate_supabase_url(_url(user="postgres.project"), allow_admin=True)
    with pytest.raises(ValueError):
        validate_supabase_url(_url(), schema_config="public")


def test_compose_only_crawlab_has_mongo_and_no_duplicate_postgres():
    config = yaml.safe_load((ROOT / "docker-compose.crawlab-supabase.yml").read_text())
    services = config["services"]
    assert "postgres" not in services
    assert ".env.*" in (ROOT / ".dockerignore").read_text()
    assert ".env.crawlab-supabase" in (ROOT / ".gitignore").read_text()
    assert {"api", "worker", "publisher", "crawlab", "crawlab-mongo", "minio", "clickhouse", "redis"} <= set(services)
    assert services["crawlab-mongo"]["networks"] == ["crawlab_private"]
    assert "ports" not in services["crawlab-mongo"]
    assert "ports" not in services["minio"]
    assert "ports" not in services["clickhouse"]
    assert "ports" not in services["redis"]
    assert "collector_data" not in services["crawlab"]["networks"]
    assert "crawlab_private" not in services["api"]["networks"]
    assert services["publisher"]["environment"]["ENABLE_FRESHNESS_SCHEDULER"] == "false"
    assert services["api"]["ports"] == ["127.0.0.1:8000:8000"]
    assert services["crawlab"]["ports"] == ["127.0.0.1:8080:8080"]
    assert services["db-migrate"]["profiles"] == ["bootstrap"]
    assert "SUPABASE_MIGRATION_DATABASE_URL" not in services["crawlab"]["environment"]
    assert "SUPABASE_MIGRATION_DATABASE_URL" not in services["api"]["environment"]
    assert "SUPABASE_MIGRATION_DATABASE_URL" not in services["worker"]["environment"]
    assert "SUPABASE_MIGRATION_DATABASE_URL" not in services["publisher"]["environment"]


def test_sql_bootstrap_is_private_and_does_not_modify_old_schemas():
    schema = (ROOT / "sql/supabase/001_private_schema.sql").read_text().lower()
    grants = (ROOT / "sql/supabase/020_runtime_grants.sql").read_text().lower()
    assert "create schema if not exists collector_core" in schema
    assert "revoke all on schema collector_core" in schema
    assert "from anon, authenticated" in schema
    assert "grant usage on schema collector_core to collector_runtime" in grants
    assert "grant select, insert, update, delete" in grants
    assert "grant create" not in grants
    assert not re.search(r"\bgrant\b[^;]*\bto\s+(?:anon|authenticated|public)\b", grants)
    assert not re.search(r"\b(?:drop|truncate)\s+(?:table|schema)\b", schema + grants)


def test_crawlab_batch_submission_has_replay_safe_keys_but_no_payload_in_logs():
    calls = []

    def fake(method, url, body, key, idem=None):
        calls.append((method, url, body, key, idem))
        return {"id": "job-1"}

    tasks = _tasks()
    assert submit(tasks, "crawler-run-01", "http://api:8000", "operator-key", request_fn=fake) == ["job-1"]
    assert submit(tasks, "crawler-run-01", "http://api:8000", "operator-key", request_fn=fake) == ["job-1"]
    assert calls[0][4] == calls[1][4]
    assert calls[0][2]["batch_id"] == "crawler-run-01"
    assert calls[0][1].endswith("/api/v1/jobs")
    tasks2 = _tasks()
    tasks2[0]["payload"]["keyword"] = "игрушки"
    submit(tasks2, "crawler-run-01", "http://api:8000", "operator-key", request_fn=fake)
    assert calls[2][4] != calls[0][4]


def test_crawlab_rejects_secrets_invalid_hosts_and_unbounded_batches():
    for bad in (
        [{"source_id": "mock", "endpoint": "sample", "kind": "sku", "payload": {"headers": {"Cookie": "sensitive"}}}],
        [{"source_id": "mock", "endpoint": "sample", "kind": "sku", "payload": {"refresh_token": "x"}}],
        [{"source_id": "mock", "endpoint": "sample", "kind": "sku", "payload": {}, "priority": 99}],
        _tasks() * 501,
        [],
    ):
        with pytest.raises(ValueError):
            submit(bad, "crawler-1", "http://api:8000", "key")
    for badurl in ("http://not-api:8000", "http://api:8001", "file:///tmp/secret", "https://user:secret@host", "http://localhost:8000", "https://example.org/steal?x=1"):
        with pytest.raises(ValueError):
            _safe_url(badurl)
    with pytest.raises(ValueError):
        submit(_tasks(), "../../bad", "http://api:8000", "key")


def test_status_wait_has_budget_and_does_not_hide_failure():
    sequence = iter([{"status": "running"}, {"status": "completed", "completed": 2, "failed": 0}])
    calls = []

    def fake(method, url, body, key, idem=None):
        calls.append((method, url))
        return next(sequence)

    report = wait_for_batch("b1", "http://api:8000", "x", max_wait=12, poll_seconds=1,
                            request_fn=fake, clock=lambda: 0, sleep=lambda _: None)
    assert report["status"] == "completed"
    assert all(x[0] == "GET" and "/api/v1/batches/b1" in x[1] for x in calls)
    times = iter([100, 101])
    with pytest.raises(TimeoutError):
        wait_for_batch("b1", "http://api:8000", "x", max_wait=1,
                       request_fn=lambda *args: {"status": "running"}, clock=lambda: next(times), sleep=lambda _: None)


def test_api_batch_aggregates_real_pg_job_status_and_enforces_auth(tmp_path):
    sf = make_session_factory(f"sqlite+pysqlite:///{tmp_path/'db.sqlite'}", test_schema=True)
    seed_mock(sf)
    settings = Settings(api_key="operator", viewer_key="viewer", admin_key="admin", allow_insecure_dev=False)
    app = create_app(settings=settings, session_factory=sf)
    jobs = JobService(sf)
    batch = "crawlab-2026-11-09"
    j1 = jobs.create(source_id="mock", endpoint="sample", kind="keyword", payload={"q": "a"}, batch_id=batch)
    j2 = jobs.create(source_id="mock", endpoint="sample", kind="keyword", payload={"q": "b"}, batch_id=batch)
    with TestClient(app) as client:
        assert client.get(f"/api/v1/batches/{batch}").status_code == 401
        headers = {"X-API-Key": "viewer"}
        body = client.get(f"/api/v1/batches/{batch}", headers=headers).json()
        assert body["status"] == "running" and body["pending"] == 2 and body["total"] == 2
        assert client.get("/api/v1/batches/no-such-batch", headers=headers).status_code == 404
        with sf.begin() as db:
            db.get(CollectionJob, j1.id).status = "completed"
            db.get(CollectionJob, j2.id).status = "dead_letter"
        body = client.get(f"/api/v1/batches/{batch}", headers=headers).json()
        assert body["status"] == "partial" and body["failed"] == 1 and body["completed"] == 1
        with sf.begin() as db:
            db.get(CollectionJob, j2.id).status = "completed"
        assert client.get(f"/api/v1/batches/{batch}", headers=headers).json()["status"] == "completed"


def test_sample_tasks_are_mock_only():
    tasks = json.loads((ROOT / "samples/crawlab_batch_mock.json").read_text())
    assert len(tasks) == 2
    assert {x["source_id"] for x in tasks} == {"mock"}
    assert {x["endpoint"] for x in tasks} == {"sample"}


def test_mock_crawlab_api_outbox_worker_raw_store_and_supabase_model(tmp_path):
    """Executable mock full control path; not a claim of remote container validation."""
    import asyncio
    from datetime import datetime, timezone
    from collector.storage.models import Product
    from collector.storage.objects import MemoryObjectStore, serialize
    from collector.scheduler.broker import MemoryBroker
    from collector.scheduler.publisher import Publisher
    from collector.adapters.mock import MockAdapter
    from collector.workers.runtime import Worker

    sf = make_session_factory(f"sqlite+pysqlite:///{tmp_path/'full.db'}", test_schema=True)
    seed_mock(sf)
    app = create_app(settings=Settings(api_key="operator", viewer_key="viewer", admin_key="admin", allow_insecure_dev=False), session_factory=sf)
    objects = MemoryObjectStore()
    emitted_facts = {}

    class OfflineVerifiedPipeline:
        dataset_version = "mock-v1"

        def save_raw(self, job_id, response):
            key = f"mock-v1/{job_id}.json"
            return key, objects.put("raw-snapshots", key, serialize(response))

        def ingest(self, db, job_id, source, rows):
            # Stubbed Silver/Gold: test only the boundary and causal delivery.
            assert source == "mock" and rows and "sku" in rows[0]
            db.add(Product(ozon_id=str(rows[0]["sku"]), title="verified mock", source=source,
                           observed_at=datetime.now(timezone.utc), dataset_version="mock-v1", algorithm_version="test-v1"))
            emitted_facts[str(rows[0]["sku"])] = {"source": source, "kind": "synthetic"}
            return {"products": 1}

    with TestClient(app) as client:
        def fake_http(method, url, body, key, idem=None):
            assert method == "POST" and url.endswith("/api/v1/jobs")
            response = client.post("/api/v1/jobs", json=body,
                                   headers={"X-API-Key": key, "Idempotency-Key": idem})
            assert response.status_code == 201, response.text
            return response.json()

        jobs = submit(_tasks(), "sample-batch", "http://api:8000", "operator", request_fn=fake_http)
        replay = submit(_tasks(), "sample-batch", "http://api:8000", "operator", request_fn=fake_http)
        assert jobs == replay
        broker = MemoryBroker()
        publisher = Publisher(sf, broker)
        pipeline = OfflineVerifiedPipeline()
        adapter = lambda source, policy: MockAdapter(str(ROOT / "samples/mock_collection.json"))
        worker = Worker(sf, broker, adapter, pipeline)

        async def run():
            assert await publisher.flush() == 1
            assert await worker.run_once("sample-worker")

        asyncio.run(run())
        status = client.get("/api/v1/batches/sample-batch", headers={"X-API-Key": "viewer"}).json()
        assert status["status"] == "completed"
        assert status["total"] == 1
        assert len(objects.objects) == 1
        assert "101001" in emitted_facts
        with sf() as db:
            assert db.get(Product, "101001") is not None
