"""Error taxonomy determines whether a source must be blocked."""
from __future__ import annotations


class CollectionError(Exception):
    code = "collection_error"
    retryable = False
    block_source = False


class PermissionLost(CollectionError):
    code = "authorization_lost"
    block_source = True


class AccessChallenge(PermissionLost):
    code = "access_challenge"


class RateLimited(CollectionError):
    code = "rate_limited"
    # Ozon 429 is not permission to rotate identity or increase concurrency.
    retryable = False
    block_source = True


class TransientSourceError(CollectionError):
    code = "source_temporarily_unavailable"
    retryable = True


class DataQualityError(CollectionError):
    code = "data_quality_error"


class StorageUnavailable(CollectionError):
    code = "storage_unavailable"
    retryable = True


class SourceNotImplemented(CollectionError):
    code = "source_not_implemented"


class PolicyViolation(CollectionError):
    code = "policy_denied"


def classify_http(status: int, text: str = "", content_type: str = "") -> None:
    if status in (301, 302, 303, 307, 308, 401, 403):
        raise PermissionLost(f"source stopped: HTTP {status}")
    if status == 429:
        raise RateLimited("source stopped: HTTP 429")
    if "text/html" in content_type.lower() or "challenge" in text[:512].lower() or "antibot" in text[:512].lower():
        raise AccessChallenge("source stopped: HTML/challenge response")
    if status >= 500 or status in (408, 425):
        raise TransientSourceError(f"HTTP {status}")
    if status >= 400:
        raise CollectionError(f"HTTP {status}")
