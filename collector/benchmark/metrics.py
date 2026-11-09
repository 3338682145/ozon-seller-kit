"""In-memory 15-minute window accumulator for the buyer benchmark.

The runner owns ONE BenchmarkMetrics per source. Every attempt calls
``start_attempt``/``record``/``end_attempt``; every 900 s the runner snapshots
the window into a ``BenchmarkInterval`` row and calls ``reset()``.

Labels are bounded: only ``source_id`` / ``kind`` / ``outcome`` ever reach
Prometheus -- never a SKU, URL or cookie value. Latency percentiles are computed
from the raw per-attempt durations (not from a pre-bucketed histogram), so the
P50/P95/P99 in the report reflect real observed spread.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

OUTCOMES = ("ok", "empty_valid", "empty_suspect", "blocked", "transient_error", "invalid")


def _percentile(sorted_vals: List[float], pct: float) -> Optional[float]:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return round(sorted_vals[0], 3)
    k = (len(sorted_vals) - 1) * pct / 100.0
    lo = int(math.floor(k))
    hi = min(lo + 1, len(sorted_vals) - 1)
    if lo == hi:
        return round(sorted_vals[lo], 3)
    return round(sorted_vals[lo] + (k - lo) * (sorted_vals[hi] - sorted_vals[lo]), 3)


class BenchmarkMetrics:
    def __init__(self, *, source_id: str, kind: str, max_rps: float,
                 window_seconds: int = 900) -> None:
        self.source_id = source_id
        self.kind = kind
        self.max_rps = max_rps
        self.window_seconds = window_seconds
        self.reset()

    def reset(self) -> None:
        self.requests = 0
        self.records = 0
        self.bytes_received = 0
        self.outcome_counts: Dict[str, int] = {o: 0 for o in OUTCOMES}
        self.valid_count = 0
        self.invalid_count = 0
        self.unknown_count = 0
        self._durations_ms: List[float] = []
        self.permit_wait_ms = 0.0
        self.peak_inflight = 0
        self._inflight = 0

    # -- concurrency bookkeeping -------------------------------------------
    def start_attempt(self) -> None:
        self._inflight += 1
        if self._inflight > self.peak_inflight:
            self.peak_inflight = self._inflight

    def end_attempt(self) -> None:
        self._inflight = max(0, self._inflight - 1)

    # -- per-attempt record ------------------------------------------------
    def record(self, *, outcome: str, duration_seconds: float, records: int,
               bytes_received: int, permit_wait_ms: float = 0.0,
               valid: int = 0, invalid: int = 0, unknown: int = 0) -> None:
        self.requests += 1
        self.records += records
        self.bytes_received += int(bytes_received)
        self.outcome_counts[outcome] = self.outcome_counts.get(outcome, 0) + 1
        self._durations_ms.append(float(duration_seconds) * 1000.0)
        self.permit_wait_ms += float(permit_wait_ms)
        self.valid_count += int(valid)
        self.invalid_count += int(invalid)
        self.unknown_count += int(unknown)

    # -- snapshot for the interval row -------------------------------------
    def snapshot(self) -> dict:
        dur = sorted(self._durations_ms)
        return {
            "requests": self.requests,
            "records": self.records,
            "bytes_received": self.bytes_received,
            "outcome_counts": dict(self.outcome_counts),
            "ok": self.outcome_counts.get("ok", 0),
            "empty_valid": self.outcome_counts.get("empty_valid", 0),
            "empty_suspect": self.outcome_counts.get("empty_suspect", 0),
            "blocked": self.outcome_counts.get("blocked", 0),
            # error bucket = transient_error + invalid (NOT followed redirects)
            "error": (self.outcome_counts.get("transient_error", 0)
                      + self.outcome_counts.get("invalid", 0)),
            "valid_count": self.valid_count,
            "invalid_count": self.invalid_count,
            "unknown_count": self.unknown_count,
            "latency_p50_ms": _percentile(dur, 50),
            "latency_p95_ms": _percentile(dur, 95),
            "latency_p99_ms": _percentile(dur, 99),
            "permit_wait_ms": round(self.permit_wait_ms, 3),
            "peak_inflight": self.peak_inflight,
        }

    # -- optional local Prometheus endpoint (never carries SKU/URL labels) --
    def serve(self, port: int) -> None:  # pragma: no cover - thin seam
        from prometheus_client import Counter, Gauge, Histogram, start_http_server
        start_http_server(port)
        Counter("benchmark_requests_total", "requests", ["source", "kind", "outcome"])
        Histogram("benchmark_duration_seconds", "latency", ["source", "kind"])
        Gauge("benchmark_peak_inflight", "peak inflight", ["source", "kind"])
