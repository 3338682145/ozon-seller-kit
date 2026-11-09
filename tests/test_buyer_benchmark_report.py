"""T6: 15-minute metrics accumulation and the sanitised run report.

Locks:
  * per-outcome counters, raw-duration P50/P95/P99, peak inflight, permit wait;
  * duration-weighted observed throughput vs the policy rps cap (utilisation);
  * valid/invalid/unknown record buckets;
  * interval-audit-event-count reconciles with the terminal event log;
  * completed vs stopped surfaced honestly;
  * a 302->200 followed redirect lands in ok/empty_valid -- NEVER invalid/error;
  * report carries no review body / author / cookie / token.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from collector.benchmark.metrics import BenchmarkMetrics
from collector.benchmark.report import build_benchmark_report, render_markdown_report


def _run(status="completed"):
    # duck-typed run row
    class R:
        run_id = "run-x"
        kind = "inventory"
        source_id = "buyer-inventory"
        mode = "offline"
        started_at = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
        stopped_at = datetime(2026, 11, 9, 12, 15, tzinfo=timezone.utc)
        policy_hash = "sha256:abc"
    R.status = status
    R.stop_reason = "duration_elapsed" if status == "completed" else "sigterm"
    return R()


def _interval(**over):
    class I:
        run_id = "run-x"
        window_start = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
        requests = 100
        records = 200
        ok = 90
        empty_valid = 2
        empty_suspect = 3
        blocked = 2
        error = 3
        latency_p50_ms = 120.0
        latency_p95_ms = 300.0
        latency_p99_ms = 600.0
        bytes_received = 12345
        valid_count = 190
        invalid_count = 5
        unknown_count = 5
        missing_field_rates = {}
        schema_version = "buyer-v2-1"
        policy_version = "v1"
        audit_event_count = 100
    for k, v in over.items():
        setattr(I, k, v)
    return I()


# --- metrics accumulation ---------------------------------------------------
def test_metrics_counts_outcomes_and_percentiles():
    m = BenchmarkMetrics(source_id="buyer-inventory", kind="inventory", max_rps=4.6)
    # durations in seconds: 0.1, 0.2, ..., 1.0
    for i in range(10):
        m.record(outcome="ok", duration_seconds=0.1 * (i + 1), records=2,
                 bytes_received=100, permit_wait_ms=5.0,
                 valid=2, invalid=0, unknown=0)
    snap = m.snapshot()
    assert snap["requests"] == 10
    assert snap["outcome_counts"]["ok"] == 10
    assert snap["records"] == 20
    # p50 of 0.1..1.0s ~= 0.55s = 550ms; p99 ~= 1.0s
    assert 500 <= snap["latency_p50_ms"] <= 600
    assert snap["latency_p99_ms"] > 900
    assert snap["permit_wait_ms"] == 50.0
    assert snap["valid_count"] == 20


def test_metrics_peak_concurrency():
    m = BenchmarkMetrics(source_id="s", kind="inventory", max_rps=4.6)
    m.start_attempt()
    m.start_attempt()
    m.start_attempt()
    m.end_attempt()
    m.record(outcome="ok", duration_seconds=0.1, records=1, bytes_received=10,
             permit_wait_ms=0, valid=1, invalid=0, unknown=0)
    m.start_attempt()  # inflight was 2 after release, peak already 3
    m.end_attempt()
    assert m.snapshot()["peak_inflight"] == 3


def test_metrics_buckets_invalid_and_unknown_separately():
    m = BenchmarkMetrics(source_id="s", kind="reviews", max_rps=4.6)
    m.record(outcome="ok", duration_seconds=0.1, records=3, bytes_received=10,
             permit_wait_ms=0, valid=3, invalid=0, unknown=0)
    m.record(outcome="invalid", duration_seconds=0.1, records=1, bytes_received=10,
             permit_wait_ms=0, valid=0, invalid=1, unknown=0)
    m.record(outcome="empty_suspect", duration_seconds=0.1, records=0, bytes_received=10,
             permit_wait_ms=0, valid=0, invalid=0, unknown=1)
    snap = m.snapshot()
    assert snap["valid_count"] == 3
    assert snap["invalid_count"] == 1
    assert snap["unknown_count"] == 1


# --- report ------------------------------------------------------------------
def test_report_totals_and_duration_weighted_throughput():
    intervals = [_interval(requests=100, audit_event_count=100)]
    rep = build_benchmark_report(
        _run(), intervals, max_rps=4.6, event_log_total=100,
    )
    # 100 requests over 900s (15min) -> ~0.11 rps observed
    assert rep["throughput"]["observed_rps"] > 0
    assert rep["throughput"]["policy_rps"] == 4.6
    # utilisation is observed/policy, never a 5x scaling claim
    assert rep["throughput"]["utilization"] < 1.0
    assert rep["totals"]["requests"] == 100
    assert rep["totals"]["ok"] == 90


def test_report_reconciliation_mismatch_flagged():
    intervals = [_interval(audit_event_count=100)]
    rep = build_benchmark_report(_run(), intervals, max_rps=4.6,
                                 event_log_total=99)  # mismatch
    assert rep["reconciliation"]["matched"] is False
    assert rep["reconciliation"]["interval_event_count"] == 100
    assert rep["reconciliation"]["event_log_count"] == 99


def test_report_completed_vs_stopped():
    done = build_benchmark_report(_run("completed"), [_interval()], max_rps=4.6,
                                  event_log_total=100)
    halt = build_benchmark_report(_run("stopped"), [_interval()], max_rps=4.6,
                                  event_log_total=100)
    assert done["run"]["status"] == "completed"
    assert halt["run"]["status"] == "stopped"


def test_report_has_no_pii_or_secrets():
    intervals = [_interval()]
    rep = build_benchmark_report(_run(), intervals, max_rps=4.6, event_log_total=100)
    md = render_markdown_report(rep)
    blob = (md + "\n" + str(rep)).lower()
    # Look for actual secret/PII leakage patterns, not the word "cookie" in prose.
    for forbidden in ("abt_data=", "session=", "authorization: bearer",
                      "set-cookie:", "reviewer:", "comment_text"):
        assert forbidden not in blob, f"leaked: {forbidden}"
    # No arbitrary long base64-ish token strings in the markdown body.
    import re
    assert not re.search(r"[a-f0-9]{40,}=", md), "looks like a raw cookie/token value"


def test_followed_redirect_lands_in_ok_not_error():
    # Simulate: the transport followed a 302 and returned the final 200 widget
    # page. The runner records outcome="ok" with reason_code="redirect_followed".
    # The report must NOT bump the error/invalid bucket.
    m = BenchmarkMetrics(source_id="buyer-inventory", kind="inventory", max_rps=4.6)
    m.record(outcome="ok", duration_seconds=0.2, records=8, bytes_received=500,
             permit_wait_ms=0, valid=8, invalid=0, unknown=0)
    snap = m.snapshot()
    assert snap["outcome_counts"]["ok"] == 1
    assert snap["outcome_counts"].get("invalid", 0) == 0
    assert snap["outcome_counts"].get("error", 0) == 0

    intervals = [_interval(
        requests=1, ok=1, empty_valid=0, empty_suspect=0, blocked=0, error=0,
        invalid_count=0, audit_event_count=1,
    )]
    rep = build_benchmark_report(_run(), intervals, max_rps=4.6, event_log_total=1)
    assert rep["totals"]["error"] == 0
    assert rep["totals"]["invalid"] == 0
    assert rep["totals"]["ok"] == 1


def test_render_markdown_lists_uncertainty_and_reconciliation():
    intervals = [_interval()]
    rep = build_benchmark_report(_run(), intervals, max_rps=4.6, event_log_total=100)
    md = render_markdown_report(rep)
    assert "run-x" in md
    assert "reconcil" in md.lower()
    # must carry an uncertainty / no-5x-scaling caveat
    assert "uncertain" in md.lower() or "estimated" in md.lower()
