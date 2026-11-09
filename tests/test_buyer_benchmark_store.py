"""T5: persist benchmark runs, 15-minute intervals and strict samples.

Constraints locked here:
  * BenchmarkRun / BenchmarkInterval / BenchmarkSample on INDEPENDENT tables;
  * (run_id, window_start) is unique -> a repeated interval write upserts to one row;
  * NULL stock values are preserved (never coerced to 0);
  * cross-date snapshots stay distinct;
  * interval audit_event_count sums reconcile with terminal events;
  * retention purge removes old samples/intervals;
  * a failed persistence must NOT flip the run to completed;
  * samples carry only safe fields -- no review body / author / cookie.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from collector.errors import StorageUnavailable
from collector.storage.database import make_session_factory
from collector.benchmark.store import BenchmarkStore


def _store(tmp_path) -> BenchmarkStore:
    sf = make_session_factory(f"sqlite+pysqlite:///{tmp_path}/t5.db", test_schema=True)
    return BenchmarkStore(sf)


def _run(store, run_id="run-1", mode="offline"):
    return store.start_run(
        run_id=run_id, kind="inventory", source_id="buyer-inventory",
        mode=mode, policy_hash="sha256:abc",
    )


def test_start_and_finish_run_records_status(tmp_path):
    store = _store(tmp_path)
    _run(store)
    store.finish_run(run_id="run-1", status="completed", stop_reason="duration_elapsed")
    run = store.get_run("run-1")
    assert run.status == "completed"
    assert run.mode == "offline"
    assert run.stopped_at is not None


def test_two_windows_and_repeated_write_is_one_row(tmp_path):
    store = _store(tmp_path)
    _run(store)
    w1 = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
    w2 = datetime(2026, 11, 9, 12, 15, tzinfo=timezone.utc)

    store.upsert_interval(run_id="run-1", window_start=w1, requests=10, ok=8,
                          audit_event_count=10, schema_version="buyer-v2-1",
                          policy_version="v1")
    # repeat same window -> must upsert (one row), not a second row
    store.upsert_interval(run_id="run-1", window_start=w1, requests=12, ok=9,
                          audit_event_count=12, schema_version="buyer-v2-1",
                          policy_version="v1")
    store.upsert_interval(run_id="run-1", window_start=w2, requests=5, ok=4,
                          audit_event_count=5, schema_version="buyer-v2-1",
                          policy_version="v1")

    rows = store.list_intervals("run-1")
    assert len(rows) == 2
    by_ws = {r.window_start.replace(tzinfo=timezone.utc): r for r in rows}
    assert by_ws[w1].requests == 12  # last write wins
    assert by_ws[w2].requests == 5


def test_null_stock_value_preserved_not_zero(tmp_path):
    store = _store(tmp_path)
    _run(store)
    observed = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
    # widget present but maxItems absent -> both stock fields NULL, never 0
    store.save_sample(
        run_id="run-1", kind="inventory", source_id="buyer-inventory",
        sku="12345", page_path="/c/toys/", observed_at=observed,
        value={"stock_proxy_max_items": None, "stock_text_remaining": None,
               "is_capped": False},
    )
    rows = store.list_samples("run-1")
    assert len(rows) == 1
    assert rows[0].value["stock_proxy_max_items"] is None
    assert rows[0].value["stock_text_remaining"] is None


def test_capped_stock_keeps_both_fields(tmp_path):
    store = _store(tmp_path)
    _run(store)
    observed = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
    store.save_sample(
        run_id="run-1", kind="inventory", source_id="buyer-inventory",
        sku="hot-1", page_path="/c/toys/", observed_at=observed,
        value={"stock_proxy_max_items": 2000, "stock_text_remaining": 3359,
               "is_capped": True},
    )
    row = store.list_samples("run-1")[0]
    assert row.value["stock_proxy_max_items"] == 2000
    assert row.value["stock_text_remaining"] == 3359
    assert row.value["is_capped"] is True


def test_cross_date_snapshots_kept_distinct(tmp_path):
    store = _store(tmp_path)
    _run(store)
    d1 = datetime(2026, 11, 9, 23, 50, tzinfo=timezone.utc)
    d2 = datetime(2026, 11, 10, 0, 10, tzinfo=timezone.utc)
    for d in (d1, d2):
        store.save_sample(
            run_id="run-1", kind="inventory", source_id="buyer-inventory",
            sku="12345", page_path="/c/toys/", observed_at=d,
            value={"stock_proxy_max_items": 5},
        )
    rows = store.list_samples("run-1")
    assert len(rows) == 2


def test_interval_totals_reconcile_with_terminal_events(tmp_path):
    store = _store(tmp_path)
    _run(store)
    w1 = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
    w2 = datetime(2026, 11, 9, 12, 15, tzinfo=timezone.utc)
    store.upsert_interval(run_id="run-1", window_start=w1, requests=10,
                          audit_event_count=10)
    store.upsert_interval(run_id="run-1", window_start=w2, requests=8,
                          audit_event_count=8)
    # 18 terminal events produced across the run == sum of interval counts
    assert store.total_audit_events("run-1") == 18


def test_sample_quota_blocks_extra_rows(tmp_path):
    store = BenchmarkStore(
        make_session_factory(f"sqlite+pysqlite:///{tmp_path}/q.db", test_schema=True),
        sample_quota=2,
    )
    _run(store)
    obs = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
    for i in range(4):
        store.save_sample(run_id="run-1", kind="inventory", source_id="s",
                          sku=str(i), page_path="/p", observed_at=obs,
                          value={"stock_proxy_max_items": i})
    assert len(store.list_samples("run-1")) == 2


def test_samples_never_carry_comment_body_or_author(tmp_path):
    store = _store(tmp_path)
    _run(store)
    obs = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
    store.save_sample(
        run_id="run-1", kind="reviews", source_id="buyer-reviews",
        sku="12345", page_path="/product/12345/reviews/", observed_at=obs,
        value={"review_id": "rev-1", "score": 5},
    )
    row = store.list_samples("run-1")[0]
    blob = str(row.value)
    assert "author" not in blob.lower()
    assert "comment" not in blob.lower()
    assert "text" not in blob.lower()


def test_retention_purge_removes_old_samples(tmp_path):
    store = _store(tmp_path)
    _run(store)
    now = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
    fresh = now
    old = now - timedelta(days=10)  # beyond 7-day sample retention
    for d in (fresh, old):
        store.save_sample(run_id="run-1", kind="inventory", source_id="s",
                          sku="1", page_path="/p", observed_at=d,
                          value={"stock_proxy_max_items": 1})
    removed = store.purge_retention(now, sample_days=7, interval_days=180)
    rows = store.list_samples("run-1")
    assert len(rows) == 1
    assert rows[0].observed_at.replace(tzinfo=timezone.utc) == fresh
    assert removed["samples"] >= 1


def test_failed_persistence_never_marks_completed(tmp_path):
    # Healthy DB: start the run -> status is "running".
    url = f"sqlite+pysqlite:///{tmp_path}/fail.db"
    sf = make_session_factory(url, test_schema=True)
    store = BenchmarkStore(sf)
    store.start_run(run_id="run-1", kind="inventory", source_id="s",
                    mode="offline", policy_hash="h")
    assert store.get_run("run-1").status == "running"

    # Make every commit blow up. finish_run must raise AND the transaction must
    # roll back -- the row must NOT be flipped to completed.
    from sqlalchemy import event
    engine = sf.kw["bind"]

    def _boom(conn):
        raise StorageUnavailable("disk full")

    event.listen(engine, "commit", _boom)
    try:
        with pytest.raises(StorageUnavailable):
            store.finish_run(run_id="run-1", status="completed")
    finally:
        event.remove(engine, "commit", _boom)

    # Re-read from the same healthy DB: status must still be running.
    assert store.get_run("run-1").status == "running"
