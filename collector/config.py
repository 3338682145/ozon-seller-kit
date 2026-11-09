"""Typed configuration. Live Ozon sources are OFF unless explicitly approved."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    stream: str = os.getenv("COLLECTION_STREAM", "collection:tasks")
    group: str = os.getenv("COLLECTION_GROUP", "collection-workers")
    dlq: str = os.getenv("COLLECTION_DLQ", "collection:dlq")
    s3_endpoint: str = os.getenv("MINIO_ENDPOINT", "minio:9000")
    s3_access_key: str = os.getenv("MINIO_ACCESS_KEY", "")
    s3_secret_key: str = os.getenv("MINIO_SECRET_KEY", "")
    s3_secure: bool = os.getenv("MINIO_SECURE", "false").lower() == "true"
    clickhouse_host: str = os.getenv("CLICKHOUSE_HOST", "clickhouse")
    clickhouse_user: str = os.getenv("CLICKHOUSE_USER", "default")
    clickhouse_password: str = os.getenv("CLICKHOUSE_PASSWORD", "")
    api_key: str = os.getenv("API_KEY", "")
    viewer_key: str = os.getenv("VIEWER_KEY", "")
    admin_key: str = os.getenv("ADMIN_KEY", "")
    allow_insecure_dev: bool = os.getenv("ALLOW_INSECURE_DEV", "false").lower() == "true"
    vault_addr: str = os.getenv("VAULT_ADDR", "")
    vault_token: str = os.getenv("VAULT_TOKEN", "")
    vault_mount: str = os.getenv("VAULT_MOUNT", "secret")
    otel_endpoint: str = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    dataset_version: str = os.getenv("DATASET_VERSION", "mock-v1")
    max_queue_backlog: int = int(os.getenv("MAX_QUEUE_BACKLOG", "10000"))
    sample_path: str = os.getenv("SAMPLE_PATH", "samples/mock_collection.json")


def must_have_auth(settings: Settings) -> None:
    if not settings.allow_insecure_dev and (not settings.api_key or not settings.admin_key):
        raise RuntimeError("API_KEY and ADMIN_KEY required; ALLOW_INSECURE_DEV is test-only")
    configured = [k for k in (settings.api_key, settings.admin_key, settings.viewer_key) if k]
    if len(set(configured)) != len(configured):
        raise RuntimeError("API_KEY, VIEWER_KEY and ADMIN_KEY must be distinct")
