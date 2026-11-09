"""End-to-end smoke against an already bootstrapped Docker Compose stack.

HTTP API -> PostgreSQL outbox -> Redis Streams -> mock worker -> MinIO ->
Silver PostgreSQL -> Gold ClickHouse -> API + Agent. No real Ozon calls.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4
import httpx

ROOT = Path(__file__).resolve().parents[1]

def env_value(name):
    if os.getenv(name):
        return os.environ[name]
    f = ROOT / ".env"
    if not f.exists():
        raise RuntimeError(".env missing; first run bash scripts/bootstrap.sh")
    for line in f.read_text().splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1]
    raise RuntimeError(f"required setting {name} not present")


def main():
    root = os.getenv("SMOKE_API_URL", "http://127.0.0.1:8000")
    with httpx.Client(base_url=root, headers={"x-api-key": env_value("API_KEY")}, timeout=5, trust_env=False) as c:
        r = c.get("/healthz")
        r.raise_for_status()
        idem = f"smoke-{uuid4()}"
        job = c.post("/api/v1/jobs", headers={"Idempotency-Key": idem}, json={
            "source_id":"mock", "endpoint":"sample", "kind":"keyword", "payload":{"keyword":"антистресс"}})
        job.raise_for_status()
        jid = job.json()["id"]
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            current = c.get(f"/api/v1/jobs/{jid}")
            current.raise_for_status()
            state = current.json()["status"]
            if state == "completed":
                break
            if state in {"blocked", "dead_letter", "canceled"}:
                raise RuntimeError(f"mock job ended unsuccessfully: {state}")
            time.sleep(1)
        else:
            raise TimeoutError("mock job did not complete within smoke test window")
        item = c.get("/api/v1/products/101001")
        item.raise_for_status()
        keywords = c.get("/api/v1/products/101001/keywords")
        keywords.raise_for_status()
        if not keywords.json()["items"]:
            raise AssertionError("Keyword-SKU relationship missing")
        agent = c.get("/api/v1/agents/collector/status")
        agent.raise_for_status()
        health = c.get("/api/v1/agents/database/health")
        health.raise_for_status()
        if health.json()["postgres_control_plane"] != "ok":
            raise AssertionError("not a PostgreSQL production-like smoke environment")
        # Verify facts reached an actual ClickHouse, not just a mocked sink.
        check = subprocess.run(["docker", "compose", "exec", "-T", "clickhouse", "sh", "-c",
                                'clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" -q "SELECT count() FROM fact_keyword_daily"'],
                               cwd=ROOT, capture_output=True, text=True, timeout=25)
        if check.returncode != 0 or int(check.stdout.strip() or 0) < 2:
            raise AssertionError("ClickHouse gold fact verification failed")
        print(json.dumps({"result": "PASS", "job_id": jid, "source": "mock",
                          "gold_keyword_rows": int(check.stdout.strip()),
                          "raw_object_key": current.json().get("raw_object_key"),
                          "agent_total_jobs": agent.json()["total_jobs"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
