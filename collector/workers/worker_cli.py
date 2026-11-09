"""Docker entrypoint: bounded async workers, stop consuming when DB is down."""
from __future__ import annotations
import asyncio
import logging
import os
import socket
import redis.asyncio as redis
from collector.config import Settings
from collector.storage.database import make_session_factory, seed_mock
from collector.storage.objects import MinioObjectStore
from collector.storage.facts import ClickHouseFactsSink
from collector.pipeline.runner import Pipeline
from collector.adapters.factory import make_adapter_factory
from collector.rate_limit.distributed import DistributedPermit
from collector.scheduler.broker import RedisStreamBroker
from collector.workers.runtime import Worker

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger("collection-worker")


async def main():
    cfg = Settings()
    sf = make_session_factory(cfg.database_url)
    seed_mock(sf)
    r = redis.from_url(cfg.redis_url, decode_responses=True)
    broker = RedisStreamBroker(r, cfg.stream, cfg.group, cfg.dlq)
    await broker.setup()
    objects = MinioObjectStore(cfg.s3_endpoint, cfg.s3_access_key, cfg.s3_secret_key, cfg.s3_secure)
    facts = ClickHouseFactsSink(cfg.clickhouse_host, cfg.clickhouse_user, cfg.clickhouse_password)
    pipeline = Pipeline(objects, facts, cfg.dataset_version)
    def permit(source, policy):
        return DistributedPermit(r, source, float(policy.rate_limit), policy.burst_limit, policy.max_concurrency, policy.timeout_seconds)
    worker = Worker(sf, broker, make_adapter_factory(cfg, sf), pipeline, permit)
    consumer = os.getenv("WORKER_NAME", socket.gethostname())
    while True:
        try:
            processed = await worker.run_once(consumer, reclaim=True, idle_ms=60000)
            if not processed:
                processed = await worker.run_once(consumer)
            if not processed:
                await asyncio.sleep(0.5)
        except Exception:
            # Never print secrets or raw exceptions containing URLs/auth headers.
            log.error("worker paused: control-plane unavailable (exception details suppressed)")
            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
