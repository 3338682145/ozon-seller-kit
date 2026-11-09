"""Build the sanitised JSON + Markdown buyer benchmark report.

The report aggregates 15-minute ``BenchmarkInterval`` rows into run-level
totals, duration-weighted throughput, latency spread and an explicit
reconciliation check (sum of interval audit_event_count == terminal event log
count). It NEVER contains review body, author, cookie, token or URL query
strings. Throughput numbers are single-process observed values; the report
carries an explicit uncertainty note and never claims a 5-Worker linear scale
or "physical stock accuracy".
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_benchmark_report(run: Any, intervals: List[Any], *,
                          max_rps: float,
                          event_log_total: Optional[int] = None) -> Dict[str, Any]:
    run_start = getattr(run, "started_at", None)
    run_stop = getattr(run, "stopped_at", None) or datetime.now(timezone.utc)
    if run_start is None:
        duration_s = 0.0
    else:
        if run_start.tzinfo is None:
            run_start = run_start.replace(tzinfo=timezone.utc)
        if run_stop.tzinfo is None:
            run_stop = run_stop.replace(tzinfo=timezone.utc)
        duration_s = max(0.0, (run_stop - run_start).total_seconds())

    totals = {
        "requests": 0, "records": 0, "ok": 0, "empty_valid": 0,
        "empty_suspect": 0, "blocked": 0, "error": 0,
        "valid": 0, "invalid": 0, "unknown": 0, "bytes": 0,
    }
    interval_event_total = 0
    peak_inflight = 0
    p50 = p95 = p99 = None
    window_rows = []
    for iv in intervals:
        totals["requests"] += int(getattr(iv, "requests", 0) or 0)
        totals["records"] += int(getattr(iv, "records", 0) or 0)
        totals["ok"] += int(getattr(iv, "ok", 0) or 0)
        totals["empty_valid"] += int(getattr(iv, "empty_valid", 0) or 0)
        totals["empty_suspect"] += int(getattr(iv, "empty_suspect", 0) or 0)
        totals["blocked"] += int(getattr(iv, "blocked", 0) or 0)
        totals["error"] += int(getattr(iv, "error", 0) or 0)
        totals["valid"] += int(getattr(iv, "valid_count", 0) or 0)
        totals["invalid"] += int(getattr(iv, "invalid_count", 0) or 0)
        totals["unknown"] += int(getattr(iv, "unknown_count", 0) or 0)
        totals["bytes"] += int(getattr(iv, "bytes_received", 0) or 0)
        interval_event_total += int(getattr(iv, "audit_event_count", 0) or 0)
        # carry the latest window's latency spread (per-window percentiles are
        # already persisted; run-level = most recent window, not a fake average)
        p50 = getattr(iv, "latency_p50_ms", None)
        p95 = getattr(iv, "latency_p95_ms", None)
        p99 = getattr(iv, "latency_p99_ms", None)
        window_rows.append({
            "window_start": _iso(getattr(iv, "window_start", None)),
            "requests": int(getattr(iv, "requests", 0) or 0),
            "ok": int(getattr(iv, "ok", 0) or 0),
            "error": int(getattr(iv, "error", 0) or 0),
            "p95_ms": getattr(iv, "latency_p95_ms", None),
        })

    observed_rps = round(totals["requests"] / duration_s, 4) if duration_s > 0 else 0.0
    utilization = round(observed_rps / max_rps, 4) if max_rps > 0 else None

    reconciled: Optional[bool]
    if event_log_total is None:
        reconciled = None
    else:
        reconciled = interval_event_total == int(event_log_total)

    status = getattr(run, "status", "unknown")
    return {
        "run": {
            "run_id": getattr(run, "run_id", None),
            "kind": getattr(run, "kind", None),
            "source_id": getattr(run, "source_id", None),
            "mode": getattr(run, "mode", None),
            "status": status,
            "stop_reason": getattr(run, "stop_reason", None),
            "started_at": _iso(run_start),
            "stopped_at": _iso(run_stop),
            "duration_seconds": round(duration_s, 3),
            "policy_hash": getattr(run, "policy_hash", None),
            "policy_version": intervals[0].policy_version if intervals else None,
            "schema_version": intervals[0].schema_version if intervals else None,
        },
        "totals": totals,
        "throughput": {
            "observed_rps": observed_rps,
            "policy_rps": max_rps,
            "utilization": utilization,
            "estimate_status": "observed",  # measured single-process
        },
        "latency": {"p50_ms": p50, "p95_ms": p95, "p99_ms": p99},
        "reconciliation": {
            "interval_event_count": interval_event_total,
            "event_log_count": event_log_total,
            "matched": reconciled,
        },
        "windows": window_rows,
        "uncertainty": [
            "Single-process observed throughput. Do NOT linearly extrapolate to 5 Workers.",
            "stock_proxy_max_items is a per-purchase quantity cap, not physical stock.",
            "Conservative starting limits (20 concurrency / 30 uses-per-cookie / 4.6 rps) are estimated until a 12h approved run re-tunes them.",
        ],
    }


def render_markdown_report(report: Dict[str, Any]) -> str:
    r = report
    run = r["run"]
    t = r["totals"]
    tp = r["throughput"]
    rec = r["reconciliation"]
    lines = [
        f"# Buyer Benchmark Report — {run.get('run_id')}",
        "",
        f"- mode: `{run.get('mode')}`  status: **{run.get('status')}**  "
        f"kind: `{run.get('kind')}`  source: `{run.get('source_id')}`",
        f"- window: {run.get('started_at')} → {run.get('stopped_at')} "
        f"({run.get('duration_seconds')}s)",
        f"- policy_version: `{run.get('policy_version')}`  "
        f"schema_version: `{run.get('schema_version')}`",
        "",
        "## Totals",
        f"- requests: {t['requests']}  records: {t['records']}  bytes: {t['bytes']}",
        f"- ok: {t['ok']}  empty_valid: {t['empty_valid']}  "
        f"empty_suspect: {t['empty_suspect']}  blocked: {t['blocked']}  "
        f"error: {t['error']}",
        f"- valid: {t['valid']}  invalid: {t['invalid']}  unknown: {t['unknown']}",
        "",
        "## Throughput (single process, observed)",
        f"- observed_rps: {tp['observed_rps']}  policy_rps cap: {tp['policy_rps']}  "
        f"utilization: {tp['utilization']}",
        "",
        "## Reconciliation",
        f"- interval audit_event_count sum: {rec['interval_event_count']}",
        f"- terminal event log count: {rec['event_log_count']}  "
        f"matched: **{rec['matched']}**",
        "",
        "## Windows",
    ]
    for w in r.get("windows", []):
        lines.append(f"- {w['window_start']}: requests={w['requests']} "
                     f"ok={w['ok']} error={w['error']} p95_ms={w['p95_ms']}")
    lines += ["", "## Uncertainty", ""]
    for u in r.get("uncertainty", []):
        lines.append(f"- {u}")
    lines.append("")
    return "\n".join(lines)
