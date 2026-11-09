"""Explicit, versioned Bronze replay into Silver/Gold; never re-fetches Ozon.

Run inside the Compose app container after retaining raw data was authorized:
  docker compose exec api python scripts/recompute.py JOB_ID replay-2026-11-v2
"""
from __future__ import annotations
import argparse
import asyncio
import json
from collector.adapters.factory import make_adapter_factory
from collector.config import Settings
from collector.errors import PolicyViolation
from collector.pipeline.runner import Pipeline
from collector.storage.database import make_session_factory
from collector.storage.facts import ClickHouseFactsSink
from collector.storage.models import CollectionJob, CollectionPolicy, DataSource, JobEvent
from collector.storage.objects import MinioObjectStore
from sqlalchemy import select


async def replay(job_id: str, version: str) -> dict:
    cfg = Settings()
    sf = make_session_factory(cfg.database_url)
    with sf() as db:
        job = db.get(CollectionJob, job_id)
        if job is None or job.status != "completed" or not job.raw_object_key:
            raise PolicyViolation("completed job with retained raw snapshot required")
        source = db.get(DataSource, job.source_id)
        policy = db.scalar(select(CollectionPolicy).where(CollectionPolicy.source_id == job.source_id, CollectionPolicy.endpoint == job.endpoint))
        if not source or not source.license_verified or not policy or source.authorization_scope != policy.authorization_scope:
            raise PolicyViolation("retention/recomputation approval not verified")
        source_id, object_key = job.source_id, job.raw_object_key
    objects = MinioObjectStore(cfg.s3_endpoint, cfg.s3_access_key, cfg.s3_secret_key, cfg.s3_secure)
    facts = ClickHouseFactsSink(cfg.clickhouse_host, cfg.clickhouse_user, cfg.clickhouse_password)
    pipeline = Pipeline(objects, facts, cfg.dataset_version)
    adapter = make_adapter_factory(cfg, sf)(source_id, policy)
    with sf.begin() as db:
        counts = await pipeline.recompute(db, job_id, source_id, object_key, adapter, version)
        db.add(JobEvent(job_id=job_id, event="recomputed", detail={"dataset_version": version, "counts": counts}))
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job_id")
    ap.add_argument("dataset_version")
    a = ap.parse_args()
    print(json.dumps(asyncio.run(replay(a.job_id, a.dataset_version)), ensure_ascii=False))


if __name__ == "__main__":
    main()
