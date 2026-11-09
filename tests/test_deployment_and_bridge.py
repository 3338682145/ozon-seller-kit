"""Static Compose and controlled Crawlab bridge tests; no actual Docker claim."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path
import httpx
import pytest
import yaml
from scripts.crawlab_batch import submit_batch

ROOT = Path(__file__).resolve().parents[1]


def test_compose_mock_stack_is_isolated_and_live_sources_not_enabled():
    compose = yaml.safe_load((ROOT/"docker-compose.yml").read_text())
    services = compose["services"]
    for name in ("postgres", "redis", "clickhouse", "minio", "minio-init", "api", "worker", "scheduler", "mcp-server", "prometheus", "loki", "grafana", "alertmanager", "otel-collector"):
        assert name in services
    assert services["crawlab"]["profiles"] == ["crawlab"]
    assert services["api"]["ports"] == ["127.0.0.1:8000:8000"]
    assert services["minio-init"]["entrypoint"] == ["/bin/sh", "-ec"]
    assert "until mc alias set" in services["minio-init"]["command"]
    assert "VAULT_TOKEN" not in services["api"]["environment"]


def test_crawlab_batch_only_enqueues_jobs_with_stable_keys():
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(201, json={"id": f"j{len(calls)}", "status": "pending"})
    jobs = submit_batch([{"source_id": "mock", "endpoint": "sample", "kind": "sku", "payload": {"sku": "101001"}}], "batch-1", "http://api:8000", "key", httpx.MockTransport(handler))
    assert jobs == ["j1"]
    assert calls[0].url.path == "/api/v1/jobs"
    assert calls[0].headers["Idempotency-Key"]
    assert calls[0].headers["X-API-Key"] == "key"
    with pytest.raises(ValueError):
        submit_batch([], "x", "http://bad-host:8000", "key", httpx.MockTransport(handler))


def test_migration_sqlite_bootstrap(tmp_path):
    env = __import__("os").environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{tmp_path}/migration.db"
    p = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=20)
    assert p.returncode == 0, p.stdout + p.stderr
    import sqlite3
    with sqlite3.connect(tmp_path/"migration.db") as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "f92b0c1d873e"
        assert "lease_expires_at" in [x[1] for x in db.execute("PRAGMA table_info(collection_jobs)")]
