"""Connections and schema seeding. create_all is only for local unit tests."""
from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from collector.storage.models import Base, DataSource, CollectionPolicy


def make_session_factory(url: str, *, test_schema: bool = False):
    extra = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {"pool_pre_ping": True}
    engine = create_engine(url, future=True, **extra)
    if test_schema:
        Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def seed_mock(session_factory) -> None:
    with session_factory.begin() as db:
        if db.get(DataSource, "mock") is None:
            db.add(DataSource(source_id="mock", engine="mock", authorization_scope="mock:read", license_verified=True, enabled=True))
        if db.scalar(select(CollectionPolicy).where(CollectionPolicy.source_id == "mock")) is None:
            db.add(CollectionPolicy(source_id="mock", endpoint="sample", authorization_scope="mock:read", max_concurrency=2, rate_limit=10, burst_limit=2, refresh_interval=3600, timeout_seconds=5, retry_budget=2, enabled=True, limit_verified=True))
        for source in ("seller_p6", "seller_p7", "seller_p8", "seller_cjm", "buyer_search", "buyer_detail", "buyer_reviews", "buyer_offers"):
            if db.get(DataSource, source) is None:
                db.add(DataSource(source_id=source, engine="httpx" if source.startswith("seller") else "snapshot", authorization_scope="unverified", license_verified=False, enabled=False))
