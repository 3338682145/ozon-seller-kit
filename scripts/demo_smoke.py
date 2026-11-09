"""Self-contained mock E2E: job -> broker -> raw -> Silver -> Gold -> API/Agent.

No network, Ozon, Docker or API keys needed; test-only in-memory backends.
"""
from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from collector.adapters.mock import MockAdapter
from collector.api import create_app
from collector.config import Settings
from collector.pipeline.runner import Pipeline
from collector.scheduler.broker import MemoryBroker
from collector.scheduler.jobs import JobService
from collector.scheduler.publisher import Publisher
from collector.storage.database import make_session_factory, seed_mock
from collector.storage.facts import MemoryFactsSink
from collector.storage.objects import MemoryObjectStore
from collector.workers.runtime import Worker


async def smoke() -> dict:
    with TemporaryDirectory() as d:
        sf = make_session_factory(f"sqlite:///{d}/smoke.db", test_schema=True)
        seed_mock(sf)
        broker, objects, facts = MemoryBroker(), MemoryObjectStore(), MemoryFactsSink()
        fixture = str(ROOT / "samples/mock_collection.json")
        worker = Worker(sf, broker, lambda source, policy: MockAdapter(fixture), Pipeline(objects, facts, "demo-v1"))
        app = create_app(settings=Settings(database_url="sqlite:///ignored", api_key="demo-reader", admin_key="demo-admin"), session_factory=sf)
        with TestClient(app) as client:
            headers = {"x-api-key": "demo-reader"}
            j = client.post("/api/v1/jobs", headers=headers, json={"source_id": "mock", "endpoint": "sample", "kind": "keyword", "payload": {"keyword": "антистресс"}})
            j.raise_for_status()
            job_id = j.json()["id"]
            await Publisher(sf, broker).flush()
            assert await worker.run_once("demo-worker")
            job = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
            products = client.get("/api/v1/products", headers=headers).json()
            kw = client.get("/api/v1/keywords", headers=headers).json()
            first = kw["items"][0]["id"]
            links = client.get(f"/api/v1/keywords/{first}/products", headers=headers).json()
            agent = client.get("/api/v1/agents/collector/status", headers=headers).json()
            db_health = client.get("/api/v1/agents/database/health", headers=headers).json()
            assert job["status"] == "completed" and links["items"]
            return {"job_status": job["status"], "products": products["total"],
                    "keywords": kw["total"], "keyword_sku_links": len(links["items"]),
                    "raw_objects": len(objects.objects), "gold_facts": len(facts.tables["fact_keyword_daily"]),
                    "agent_jobs": agent["total_jobs"], "database_health": db_health["postgres_control_plane"]}


if __name__ == "__main__":
    print(json.dumps(asyncio.run(smoke()), ensure_ascii=False, indent=2))
