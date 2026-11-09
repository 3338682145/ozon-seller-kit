"""PostgreSQL control plane schema. Use Alembic for production migrations."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, Numeric,
    String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase


def uuid_str() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"
    ozon_id = Column(String(64), primary_key=True)
    title = Column(Text)
    price_rub = Column(Numeric(18, 4))
    currency = Column(String(8), nullable=False, default="RUB")
    category_id = Column(String(64))
    seller_id = Column(String(64))
    observed_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    source = Column(String(64), nullable=False)
    data_type = Column(String(24), nullable=False, default="observation")
    dataset_version = Column(String(128), nullable=False)
    algorithm_version = Column(String(64), nullable=False)


class ProductVariant(Base):
    __tablename__ = "product_variants"
    id = Column(String(36), primary_key=True, default=uuid_str)
    product_id = Column(String(64), ForeignKey("products.ozon_id"), nullable=False)
    variant_ozon_id = Column(String(64), nullable=False)
    properties = Column(JSON, default=dict)
    source = Column(String(64), nullable=False)
    __table_args__ = (UniqueConstraint("product_id", "variant_ozon_id", name="uq_variant"),)


class ProductIdMapping(Base):
    __tablename__ = "product_id_mappings"
    id = Column(String(36), primary_key=True, default=uuid_str)
    external_source = Column(String(64), nullable=False)
    external_id = Column(String(128), nullable=False)
    ozon_id = Column(String(64), ForeignKey("products.ozon_id"), nullable=False)
    confidence = Column(Numeric(6, 4), nullable=False, default=1)
    evidence = Column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("external_source", "external_id", name="uq_external_id"),)


class Keyword(Base):
    __tablename__ = "keywords"
    id = Column(String(36), primary_key=True, default=uuid_str)
    text = Column(Text, nullable=False)
    normalized = Column(String(512), nullable=False, unique=True)
    language = Column(String(8), nullable=False, default="ru")
    observed_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    dataset_version = Column(String(128), nullable=False)


class Category(Base):
    __tablename__ = "categories"
    id = Column(String(64), primary_key=True)
    parent_id = Column(String(64), ForeignKey("categories.id"))
    title = Column(Text, nullable=False)


class Seller(Base):
    __tablename__ = "sellers"
    id = Column(String(64), primary_key=True)
    name = Column(Text)
    country = Column(String(64))


class DataSource(Base):
    __tablename__ = "data_sources"
    source_id = Column(String(64), primary_key=True)
    engine = Column(String(32), nullable=False, default="httpx")
    authorization_scope = Column(String(128), nullable=False, default="mock")
    license_verified = Column(Boolean, nullable=False, default=False)
    enabled = Column(Boolean, nullable=False, default=False)
    blocked = Column(Boolean, nullable=False, default=False)
    blocked_reason = Column(String(256))
    credential_ref = Column(String(256))  # Secret reference only, never cookie bytes.
    last_healthy_at = Column(DateTime(timezone=True))


class CollectionPolicy(Base):
    __tablename__ = "collection_policies"
    id = Column(String(36), primary_key=True, default=uuid_str)
    source_id = Column(String(64), ForeignKey("data_sources.source_id"), nullable=False)
    endpoint = Column(String(256), nullable=False)
    authorization_scope = Column(String(128), nullable=False)
    max_concurrency = Column(Integer, nullable=False, default=1)
    rate_limit = Column(Numeric(12, 4), nullable=False, default=1)
    burst_limit = Column(Integer, nullable=False, default=1)
    refresh_interval = Column(Integer, nullable=False, default=86400)
    timeout_seconds = Column(Integer, nullable=False, default=30)
    retry_budget = Column(Integer, nullable=False, default=2)
    priority = Column(Integer, nullable=False, default=0)
    enabled = Column(Boolean, nullable=False, default=False)
    limit_verified = Column(Boolean, nullable=False, default=False)
    __table_args__ = (UniqueConstraint("source_id", "endpoint", name="uq_collection_policy"),)


class CollectionJob(Base):
    __tablename__ = "collection_jobs"
    id = Column(String(36), primary_key=True, default=uuid_str)
    source_id = Column(String(64), ForeignKey("data_sources.source_id"), nullable=False)
    endpoint = Column(String(256), nullable=False)
    kind = Column(String(24), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    batch_id = Column(String(128))
    fingerprint = Column(String(128), nullable=False, unique=True)
    status = Column(String(32), nullable=False, default="pending")
    priority = Column(Integer, nullable=False, default=0)
    attempts = Column(Integer, nullable=False, default=0)
    checkpoint = Column(JSON, default=dict)
    raw_object_key = Column(String(512))
    raw_sha256 = Column(String(64))
    last_error_code = Column(String(64))
    last_error = Column(String(512))  # sanitized only
    next_retry_at = Column(DateTime(timezone=True))
    lease_owner = Column(String(128))
    lease_expires_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    completed_at = Column(DateTime(timezone=True))
    __table_args__ = (Index("ix_jobs_source_status_due", "source_id", "status", "next_retry_at"),)


class JobEvent(Base):
    __tablename__ = "job_events"
    id = Column(String(36), primary_key=True, default=uuid_str)
    job_id = Column(String(36), ForeignKey("collection_jobs.id"), nullable=False)
    event = Column(String(64), nullable=False)
    detail = Column(JSON, default=dict)
    occurred_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    id = Column(String(36), primary_key=True, default=uuid_str)
    job_id = Column(String(36), ForeignKey("collection_jobs.id"), nullable=False)
    kind = Column(String(24), nullable=False, default="enqueue")
    priority = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    published_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    __table_args__ = (Index("ix_outbox_unpublished", "published_at", "available_at"),)


class KeywordProduct(Base):
    __tablename__ = "keyword_product_relations"
    id = Column(String(36), primary_key=True, default=uuid_str)
    keyword_id = Column(String(36), ForeignKey("keywords.id"), nullable=False)
    ozon_id = Column(String(64), ForeignKey("products.ozon_id"), nullable=False)
    observed_date = Column(String(10), nullable=False)
    position = Column(Integer)
    is_advert = Column(Boolean)
    source = Column(String(64), nullable=False)
    dataset_version = Column(String(128), nullable=False)
    algorithm_version = Column(String(64), nullable=False)
    __table_args__ = (UniqueConstraint("keyword_id", "ozon_id", "observed_date", "source", name="uq_kw_sku_day_source"), Index("ix_kwsku_product", "ozon_id"),)


class DataQualityIssue(Base):
    __tablename__ = "data_quality_issues"
    id = Column(String(36), primary_key=True, default=uuid_str)
    job_id = Column(String(36), ForeignKey("collection_jobs.id"))
    source = Column(String(64), nullable=False)
    issue_type = Column(String(64), nullable=False)
    reference_id = Column(String(128))
    details = Column(JSON, default=dict)
    observed_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class Incident(Base):
    __tablename__ = "incidents"
    id = Column(String(36), primary_key=True, default=uuid_str)
    dedup_key = Column(String(128), nullable=False, unique=True)
    severity = Column(String(2), nullable=False)
    status = Column(String(24), nullable=False, default="open")
    source_id = Column(String(64))
    error_code = Column(String(64))
    summary = Column(Text)
    occurrence_count = Column(Integer, nullable=False, default=1)
    root_cause = Column(Text)
    actions = Column(JSON, default=list)
    recovered_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_seen_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class AgentDecision(Base):
    __tablename__ = "agent_decisions"
    id = Column(String(36), primary_key=True, default=uuid_str)
    agent = Column(String(64), nullable=False)
    ticket_id = Column(String(36))
    session_id = Column(String(36))
    decision = Column(String(128), nullable=False)
    rationale = Column(Text, nullable=False)
    inputs = Column(JSON, default=dict)
    assignment = Column(JSON, default=dict)
    report = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class AgentApproval(Base):
    __tablename__ = "agent_approvals"
    id = Column(String(36), primary_key=True, default=uuid_str)
    decision_id = Column(String(36), ForeignKey("agent_decisions.id"), nullable=False)
    operation = Column(String(64), nullable=False)
    status = Column(String(24), nullable=False, default="pending")
    approver = Column(String(128))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    approved_at = Column(DateTime(timezone=True))


class CredentialStatus(Base):
    __tablename__ = "credential_status"
    credential_ref = Column(String(256), primary_key=True)
    status = Column(String(24), nullable=False, default="active")
    expires_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class CollectionTarget(Base):
    """Explicitly configured freshness-driven recurring targets; no blind scanning."""
    __tablename__ = "collection_targets"
    id = Column(String(36), primary_key=True, default=uuid_str)
    source_id = Column(String(64), ForeignKey("data_sources.source_id"), nullable=False)
    endpoint = Column(String(256), nullable=False)
    kind = Column(String(24), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    enabled = Column(Boolean, nullable=False, default=False)
    next_due_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_job_id = Column(String(36))
    __table_args__ = (Index("ix_target_due", "enabled", "next_due_at"),)


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    worker_id = Column(String(128), primary_key=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    state = Column(String(24), nullable=False, default="idle")
    last_job_id = Column(String(36))


# ---------------------------------------------------------------------------
# Buyer 12-hour benchmark: INDEPENDENT tables. These are NOT product/keyword
# master tables and must not upsert into products/keywords. They exist only to
# audit a single-process stability run; review body / author / cookie values
# never live here.
# ---------------------------------------------------------------------------
class BenchmarkRun(Base):
    """One benchmark execution (offline or live)."""
    __tablename__ = "benchmark_runs"
    run_id = Column(String(64), primary_key=True)
    kind = Column(String(24), nullable=False)          # inventory | reviews
    source_id = Column(String(64), nullable=False)
    mode = Column(String(16), nullable=False)         # offline | live
    started_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    stopped_at = Column(DateTime(timezone=True))
    status = Column(String(24), nullable=False, default="running")
    stop_reason = Column(String(256))
    policy_hash = Column(String(128), nullable=False)


class BenchmarkInterval(Base):
    """One 15-minute aggregated window per run. Unique on (run_id, window_start)
    so a repeated flush upserts to a single row (idempotent)."""
    __tablename__ = "benchmark_intervals"
    id = Column(String(36), primary_key=True, default=uuid_str)
    run_id = Column(String(64), ForeignKey("benchmark_runs.run_id"), nullable=False)
    window_start = Column(DateTime(timezone=True), nullable=False)
    requests = Column(Integer, nullable=False, default=0)
    records = Column(Integer, nullable=False, default=0)
    ok = Column(Integer, nullable=False, default=0)
    empty_valid = Column(Integer, nullable=False, default=0)
    empty_suspect = Column(Integer, nullable=False, default=0)
    blocked = Column(Integer, nullable=False, default=0)
    error = Column(Integer, nullable=False, default=0)
    latency_p50_ms = Column(Numeric(12, 3))
    latency_p95_ms = Column(Numeric(12, 3))
    latency_p99_ms = Column(Numeric(12, 3))
    bytes_received = Column(Integer, nullable=False, default=0)
    valid_count = Column(Integer, nullable=False, default=0)
    invalid_count = Column(Integer, nullable=False, default=0)
    unknown_count = Column(Integer, nullable=False, default=0)
    missing_field_rates = Column(JSON, default=dict)
    schema_version = Column(String(32))
    policy_version = Column(String(32))
    audit_event_count = Column(Integer, nullable=False, default=0)
    __table_args__ = (
        UniqueConstraint("run_id", "window_start", name="uq_benchmark_interval_window"),
    )


class BenchmarkSample(Base):
    """Strictly-quota'd, de-identified observations. ``value`` holds ONLY safe
    summary fields (stock_proxy_max_items / stock_text_remaining / is_capped /
    score / review_id). Review body, author, cookie and URLs are NEVER stored
    here; raw responses (when explicitly approved) live in object storage with
    an expiry and only their sha256 digest is referenced."""
    __tablename__ = "benchmark_samples"
    id = Column(String(36), primary_key=True, default=uuid_str)
    run_id = Column(String(64), ForeignKey("benchmark_runs.run_id"), nullable=False)
    kind = Column(String(24), nullable=False)
    source_id = Column(String(64), nullable=False)
    sku = Column(String(64), nullable=False)
    page_path = Column(String(512), nullable=False)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    value = Column(JSON, nullable=False)
    raw_sha256 = Column(String(64))  # only when explicitly approved
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
