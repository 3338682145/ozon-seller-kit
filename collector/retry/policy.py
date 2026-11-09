"""Deterministic bounded retry policy; never retries auth or challenges."""
from __future__ import annotations
from datetime import timedelta
from collector.errors import CollectionError
from collector.storage.models import utc_now


def should_retry(error: Exception, attempts: int, retry_budget: int) -> bool:
    return isinstance(error, CollectionError) and error.retryable and not error.block_source and attempts <= retry_budget


def retry_at(attempts: int):
    return utc_now() + timedelta(seconds=min(300, 2 ** min(attempts, 8)))
