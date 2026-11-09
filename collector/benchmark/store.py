"""Persistence for buyer benchmark runs, 15-minute intervals and samples.

Design (plan Task 5, spec 10.1):
  * Independent tables only -- no upsert into products/keywords/data_sources.
  * ``(run_id, window_start)`` is unique, so re-flushing a window upserts to a
    single row (idempotent).
  * Samples are strictly quota'd and carry ONLY safe summary fields. Review
    body / author / cookie values are never columns here; a defensive sanitiser
    drops known PII keys even if a caller passes them.
  * A failed write raises StorageUnavailable and the transaction rolls back, so
    a run can never be flipped to ``completed`` by a half-persisted finish.
  * Retention purge removes samples (default 7d) and interval summaries
    (default 180d) older than policy; request-event JSONL retention is the
    operator's job (30d).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, delete, func

from collector.errors import StorageUnavailable
from collector.storage.models import (
    Base,
    BenchmarkRun,
    BenchmarkInterval,
    BenchmarkSample,
    utc_now,
)

# Keys that must NEVER land in a sample value even if a caller passes them.
_FORBIDDEN_VALUE_KEYS = (
    "author", "comment", "text", "body", "cookie", "cookies", "authorization",
    "token", "url", "url_query", "ip",
)

DEFAULT_SAMPLE_QUOTA = 100


def _naive_utc(dt: datetime) -> datetime:
    """SQLite drops tzinfo on round-trip; normalise to naive UTC for storage and
    for equality comparisons so upserts match across DB backends."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _sanitise_value(value: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in (value or {}).items():
        if k.lower() in _FORBIDDEN_VALUE_KEYS:
            continue
        out[k] = v
    return out


class BenchmarkStore:
    """Thin transactional wrapper over the benchmark ORM tables."""

    def __init__(self, session_factory, *, sample_quota: int = DEFAULT_SAMPLE_QUOTA) -> None:
        self._sf = session_factory
        self.sample_quota = sample_quota

    # -- run lifecycle ------------------------------------------------------
    def start_run(self, *, run_id: str, kind: str, source_id: str,
                  mode: str, policy_hash: str) -> BenchmarkRun:
        try:
            with self._sf.begin() as db:
                existing = db.get(BenchmarkRun, run_id)
                if existing is not None:
                    return existing
                row = BenchmarkRun(
                    run_id=run_id, kind=kind, source_id=source_id, mode=mode,
                    started_at=utc_now(), status="running", policy_hash=policy_hash,
                )
                db.add(row)
                db.flush()
                db.refresh(row)
                return row
        except StorageUnavailable:
            raise
        except Exception as e:
            raise StorageUnavailable(f"start_run failed: {e}") from e

    def finish_run(self, *, run_id: str, status: str,
                   stop_reason: Optional[str] = None,
                   stopped_at: Optional[datetime] = None) -> BenchmarkRun:
        try:
            with self._sf.begin() as db:
                row = db.get(BenchmarkRun, run_id)
                if row is None:
                    raise StorageUnavailable(f"run {run_id} not found")
                row.status = status
                row.stop_reason = stop_reason
                row.stopped_at = stopped_at or utc_now()
                db.flush()
                db.refresh(row)
                return row
        except StorageUnavailable:
            raise
        except Exception as e:
            raise StorageUnavailable(f"finish_run failed: {e}") from e

    def get_run(self, run_id: str) -> BenchmarkRun:
        with self._sf() as db:
            row = db.get(BenchmarkRun, run_id)
            if row is None:
                raise StorageUnavailable(f"run {run_id} not found")
            return row

    # -- 15-minute intervals ------------------------------------------------
    def upsert_interval(self, *, run_id: str, window_start: datetime,
                        **fields: Any) -> BenchmarkInterval:
        ws = _naive_utc(window_start)
        try:
            with self._sf.begin() as db:
                row = db.execute(
                    select(BenchmarkInterval).where(
                        BenchmarkInterval.run_id == run_id,
                        BenchmarkInterval.window_start == ws,
                    )
                ).scalar_one_or_none()
                if row is None:
                    row = BenchmarkInterval(run_id=run_id, window_start=ws)
                    db.add(row)
                for k, v in fields.items():
                    if v is not None and hasattr(row, k):
                        setattr(row, k, v)
                db.flush()
                db.refresh(row)
                return row
        except Exception as e:
            raise StorageUnavailable(f"upsert_interval failed: {e}") from e

    def list_intervals(self, run_id: str) -> List[BenchmarkInterval]:
        with self._sf() as db:
            return list(db.execute(
                select(BenchmarkInterval)
                .where(BenchmarkInterval.run_id == run_id)
                .order_by(BenchmarkInterval.window_start)
            ).scalars())

    def total_audit_events(self, run_id: str) -> int:
        with self._sf() as db:
            total = db.execute(
                select(func.coalesce(func.sum(BenchmarkInterval.audit_event_count), 0))
                .where(BenchmarkInterval.run_id == run_id)
            ).scalar()
            return int(total or 0)

    # -- strict samples -----------------------------------------------------
    def save_sample(self, *, run_id: str, kind: str, source_id: str, sku: str,
                    page_path: str, observed_at: datetime,
                    value: Dict[str, Any],
                    raw_sha256: Optional[str] = None) -> Optional[BenchmarkSample]:
        safe = _sanitise_value(value)
        obs = _naive_utc(observed_at)
        try:
            with self._sf.begin() as db:
                used = db.execute(
                    select(func.count(BenchmarkSample.id))
                    .where(BenchmarkSample.run_id == run_id)
                ).scalar() or 0
                if used >= self.sample_quota:
                    return None  # quota reached: drop the sample, do not fail
                row = BenchmarkSample(
                    run_id=run_id, kind=kind, source_id=source_id, sku=str(sku),
                    page_path=page_path, observed_at=obs, value=safe,
                    raw_sha256=raw_sha256,
                )
                db.add(row)
                db.flush()
                db.refresh(row)
                return row
        except Exception as e:
            raise StorageUnavailable(f"save_sample failed: {e}") from e

    def list_samples(self, run_id: str) -> List[BenchmarkSample]:
        with self._sf() as db:
            return list(db.execute(
                select(BenchmarkSample)
                .where(BenchmarkSample.run_id == run_id)
                .order_by(BenchmarkSample.observed_at)
            ).scalars())

    # -- retention ----------------------------------------------------------
    def purge_retention(self, now: datetime, *, sample_days: int,
                        interval_days: int) -> Dict[str, int]:
        now_naive = _naive_utc(now)
        sample_cutoff = now_naive - timedelta(days=sample_days)
        interval_cutoff = now_naive - timedelta(days=interval_days)
        removed = {"samples": 0, "intervals": 0}
        try:
            with self._sf.begin() as db:
                rs = db.execute(
                    delete(BenchmarkSample).where(
                        BenchmarkSample.observed_at < sample_cutoff)
                )
                ri = db.execute(
                    delete(BenchmarkInterval).where(
                        BenchmarkInterval.window_start < interval_cutoff)
                )
                removed["samples"] = rs.rowcount or 0
                removed["intervals"] = ri.rowcount or 0
        except Exception as e:
            raise StorageUnavailable(f"purge_retention failed: {e}") from e
        return removed
