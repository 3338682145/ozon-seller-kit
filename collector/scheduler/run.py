"""Outbox publisher; periodic policy refresh is intentionally OFF without source targets."""
import asyncio
import logging
import os
import redis.asyncio as redis
from collector.config import Settings
from collector.storage.database import make_session_factory, seed_mock
from collector.scheduler.broker import RedisStreamBroker
from collector.scheduler.publisher import Publisher
from collector.scheduler.freshness import FreshnessScheduler

logging.basicConfig(level=logging.INFO)


async def main():
    cfg = Settings()
    sf = make_session_factory(cfg.database_url)
    seed_mock(sf)
    r = redis.from_url(cfg.redis_url, decode_responses=True)
    broker = RedisStreamBroker(r, cfg.stream, cfg.group, cfg.dlq)
    await broker.setup()
    publisher = Publisher(sf, broker, cfg.max_queue_backlog)
    # When Crawlab owns recurring batch schedules, the native freshness
    # scheduler must not independently create overlapping collections.
    freshness_enabled = os.getenv("ENABLE_FRESHNESS_SCHEDULER", "true").lower() == "true"
    freshness = FreshnessScheduler(sf) if freshness_enabled else None
    ticks = 0
    while True:
        try:
            await publisher.flush()
            if freshness is not None and ticks % 60 == 0:
                freshness.tick()
            ticks += 1
        except Exception:
            logging.error("outbox failed; retry later without acknowledging (details suppressed)")
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
