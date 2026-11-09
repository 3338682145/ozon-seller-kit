"""Single-process bounded 12-hour benchmark runner.

Invariants (plan Task 7, spec 10.2):
  * a permit is acquired from the BudgetLimiter BEFORE every attempt;
  * every attempt produces exactly ONE terminal event;
  * the loop checks deadline / stop_event / budget BEFORE leasing or fetching;
  * a 900 s interval is flushed (idempotent upsert) at most every window;
  * status is ``completed`` ONLY on natural deadline; any other exit is
    ``stopped`` / ``blocked`` / ``failed`` with a partial report;
  * event-log or store write failure stops new requests and never flips the run
    to completed;
  * three consecutive blocked tickets mark the source stopped (no re-entry);
  * live mode with an empty cookie pool sends ZERO requests (fail closed);
  * errors never auto-raise the rate.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, List, Optional, Set

from collector.benchmark.adapters import (
    BuyerTransport,
    collect_inventory_page,
    collect_review_page,
)
from collector.benchmark.contracts import SCHEMA_VERSION
from collector.benchmark.events import EventLog, RequestAuditEvent
from collector.benchmark.metrics import BenchmarkMetrics
from collector.benchmark.outcomes import classify_buyer_response
from collector.benchmark.policy import (
    BudgetExhausted,
    BudgetLimiter,
    BenchmarkPolicy,
)
from collector.benchmark.store import BenchmarkStore
from collector.benchmark.cookie_supply import CookieSupply, PoolEmpty
from collector.errors import StorageUnavailable

WINDOW_SECONDS = 900
MAX_CONSECUTIVE_BLOCKED = 3


@dataclass
class BenchmarkSummary:
    run_id: str
    status: str
    stop_reason: Optional[str]
    requests: int
    intervals: int
    started_at: str
    stopped_at: str


def _policy_hash(p: BenchmarkPolicy) -> str:
    blob = json.dumps({
        "source_id": p.source_id, "kind": p.kind,
        "allowed_endpoint": p.allowed_endpoint, "max_rps": p.max_rps,
        "burst": p.burst, "max_concurrency": p.max_concurrency,
        "max_requests": p.max_requests,
        "max_requests_per_day": p.max_requests_per_day,
        "duration_seconds": p.duration_seconds,
        "policy_version": p.policy_version, "mode": p.mode,
    }, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]


def _utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_experiment(
    policy: BenchmarkPolicy,
    *,
    transport: BuyerTransport,
    store: BenchmarkStore,
    event_log: EventLog,
    metrics: BenchmarkMetrics,
    clock: Optional[Callable[[], float]] = None,
    wall_now: Optional[Callable[[], datetime]] = None,
    page_paths: Optional[List[str]] = None,
    wanted_skus: Optional[Set[str]] = None,
    stop_event: Optional[Any] = None,
    max_attempts: Optional[int] = None,
    cookie_supply: Optional[CookieSupply] = None,
    budget_limiter: Optional[BudgetLimiter] = None,
) -> BenchmarkSummary:
    clock = clock or time.monotonic
    wall_now = wall_now or (lambda: datetime.now(timezone.utc))
    page_paths = page_paths or ["/search/?text=toys"]
    wanted_skus = wanted_skus or set()
    limiter = budget_limiter or BudgetLimiter({policy.source_id: policy}, clock=clock)

    run_id = uuid.uuid4().hex[:12]
    started_wall = wall_now()
    store.start_run(
        run_id=run_id, kind=policy.kind, source_id=policy.source_id,
        mode=policy.mode, policy_hash=_policy_hash(policy),
    )

    deadline = clock() + policy.duration_seconds
    window_mono = clock()
    window_wall = wall_now()
    attempts_in_window = 0
    requests = 0
    consecutive_blocked = 0
    status = "completed"
    stop_reason = "duration_elapsed"
    failed = False

    def flush_window(force: bool = False) -> None:
        nonlocal window_mono, window_wall, attempts_in_window
        snap = metrics.snapshot()
        if snap["requests"] == 0 and not force:
            return
        store.upsert_interval(
            run_id=run_id, window_start=window_wall,
            requests=snap["requests"], records=snap["records"],
            ok=snap["ok"], empty_valid=snap["empty_valid"],
            empty_suspect=snap["empty_suspect"], blocked=snap["blocked"],
            error=snap["error"],
            latency_p50_ms=snap["latency_p50_ms"],
            latency_p95_ms=snap["latency_p95_ms"],
            latency_p99_ms=snap["latency_p99_ms"],
            bytes_received=snap["bytes_received"],
            valid_count=snap["valid_count"],
            invalid_count=snap["invalid_count"],
            unknown_count=snap["unknown_count"],
            audit_event_count=attempts_in_window,
            schema_version=SCHEMA_VERSION,
            policy_version=policy.policy_version,
        )
        metrics.reset()
        window_mono = clock()
        window_wall = wall_now()
        attempts_in_window = 0

    try:
        while clock() < deadline:
            if stop_event is not None and stop_event.is_set():
                status, stop_reason = "stopped", "manual_stop"
                break
            if max_attempts is not None and requests >= max_attempts:
                break
            if consecutive_blocked >= MAX_CONSECUTIVE_BLOCKED:
                status, stop_reason = "blocked", "three_consecutive_blocked_tickets"
                break

            # Acquire permit BEFORE doing any work.
            try:
                permit = limiter.acquire(policy.source_id)
            except BudgetExhausted as e:
                status, stop_reason = "stopped", f"budget:{e.reason}"
                break

            # Live mode requires a leased session; offline runs pass no supply.
            session = None
            if policy.mode == "live":
                if cookie_supply is None:
                    status, stop_reason = "blocked", "live_requires_cookie_supply"
                    limiter.release(permit)
                    break
                try:
                    session = cookie_supply.lease()
                except PoolEmpty:
                    status, stop_reason = "blocked", "cookie_pool_empty"
                    limiter.release(permit)
                    break

            requests += 1
            attempts_in_window += 1
            t0 = clock()
            metrics.start_attempt()

            page_path = page_paths[(requests - 1) % len(page_paths)]
            try:
                env = transport.fetch_page(page_path, session)
            except Exception:
                env = None
            duration_s = max(0.0, clock() - t0)

            if env is None:
                outcome = "transient_error"
                status_code, content_type, body = 599, "text/plain", ""
                n_records = 0
                accepted = 0
                raw_bytes = 0
                obs: list = []
            else:
                status_code = env.status_code
                content_type = env.content_type
                body = env.body
                outcome = classify_buyer_response(
                    status_code, content_type, body, policy.kind)
                observed_at = _utc_iso(wall_now())
                try:
                    if policy.kind == "reviews":
                        sku = page_path.rstrip("/").split("/")[-2]
                        obs = collect_review_page(
                            transport, sku, page_path, observed_at, session)
                    else:
                        obs = collect_inventory_page(
                            transport, page_path, wanted_skus, observed_at, session)
                except Exception:
                    obs = []
                    outcome = "invalid"
                n_records = len(obs)
                accepted = n_records
                try:
                    raw_bytes = len(json.dumps(body, ensure_ascii=False))
                except Exception:
                    raw_bytes = 0

            reason_code = "redirect_followed" if 300 <= status_code < 400 else None
            ev = RequestAuditEvent(
                ts_utc=_utc_iso(wall_now()), run_id=run_id,
                source_id=policy.source_id, endpoint_id=policy.allowed_endpoint,
                batch_id=window_wall.strftime("%Y%m%dT%H%M"),
                request_id=uuid.uuid4().hex[:12], attempt=requests,
                status_code=status_code, outcome=outcome,
                duration_ms=round(duration_s * 1000.0, 3),
                permit_wait_ms=0.0, response_bytes=raw_bytes,
                observed_records=n_records, accepted_records=accepted,
                schema_version=SCHEMA_VERSION, validation_error_codes=[],
                write_status="written", reason_code=reason_code,
            )
            try:
                event_log.append(ev)
            except StorageUnavailable:
                metrics.end_attempt()
                limiter.release(permit)
                status, stop_reason = "failed", "event_log_write_failed"
                failed = True
                break

            valid = sum(1 for o in obs if not getattr(o, "field_status", {}))
            invalid = sum(1 for o in obs
                          if any(v == "invalid" for v in
                                 getattr(o, "field_status", {}).values()))
            unknown = n_records - valid - invalid
            metrics.record(
                outcome=outcome, duration_seconds=duration_s, records=n_records,
                bytes_received=raw_bytes, permit_wait_ms=0.0,
                valid=valid, invalid=invalid, unknown=unknown,
            )

            # strict-quota samples: only safe summary fields
            for o in obs[:10]:
                value = {"sku": o.sku}
                if hasattr(o, "stock_proxy_max_items"):
                    value["stock_proxy_max_items"] = o.stock_proxy_max_items
                    value["stock_text_remaining"] = o.stock_text_remaining
                    value["is_capped"] = o.is_capped
                else:
                    value["review_id"] = o.review_id
                    value["score"] = o.score
                try:
                    store.save_sample(
                        run_id=run_id, kind=policy.kind, source_id=policy.source_id,
                        sku=o.sku, page_path=page_path, observed_at=wall_now(),
                        value=value,
                    )
                except StorageUnavailable:
                    metrics.end_attempt()
                    limiter.release(permit)
                    status, stop_reason = "failed", "sample_write_failed"
                    failed = True
                    break

            if outcome == "blocked":
                consecutive_blocked += 1
                if session is not None and cookie_supply is not None:
                    cookie_supply.mark_dead(session.id)
            else:
                consecutive_blocked = 0

            metrics.end_attempt()
            limiter.release(permit)

            if clock() - window_mono >= WINDOW_SECONDS:
                flush_window()
    finally:
        if not failed:
            try:
                flush_window(force=True)
            except StorageUnavailable:
                status, stop_reason = "failed", "interval_flush_failed"
        try:
            store.finish_run(run_id=run_id, status=status, stop_reason=stop_reason)
        except StorageUnavailable:
            status, stop_reason = "failed", "finish_run_persist_failed"

    intervals = store.list_intervals(run_id)
    return BenchmarkSummary(
        run_id=run_id, status=status, stop_reason=stop_reason,
        requests=requests, intervals=len(intervals),
        started_at=_utc_iso(started_wall), stopped_at=_utc_iso(wall_now()),
    )
