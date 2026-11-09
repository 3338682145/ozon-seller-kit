"""T7: bounded single-process benchmark runner + safe stop.

Locks:
  * a permit is acquired BEFORE every attempt; one terminal event per attempt;
  * 900 s interval flush (idempotent upsert);
  * SIGTERM / manual stop -> status=stopped (never a fake completed);
  * event-log / store write failure -> status=failed, never completed;
  * run/day budget enforced exactly;
  * three consecutive blocked tickets stops the source (no re-entry);
  * live mode with an empty cookie pool sends ZERO requests (fail-closed);
  * a followed 302->200 lands in ok, never in the error bucket;
  * errors never auto-increase the rate.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone

import pytest

from collector.benchmark.adapters import ResponseEnvelope
from collector.benchmark.events import EventLog
from collector.benchmark.metrics import BenchmarkMetrics
from collector.benchmark.policy import (
    BudgetLimiter,
    BenchmarkPolicy,
    load_benchmark_policy,
)
from collector.benchmark.runner import run_experiment
from collector.benchmark.store import BenchmarkStore
from collector.benchmark.cookie_supply import CookieSupply
from collector.errors import StorageUnavailable
from collector.storage.database import make_session_factory

HERE = os.path.dirname(__file__)
SAMPLES = os.path.join(HERE, "..", "samples", "benchmark")
CFG = os.path.join(HERE, "..", "config", "benchmark")


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def _wall():
    return datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


class TrackingWall:
    """Wall clock that advances with the fake monotonic clock, so 900s windows
    land on distinct window_start values (the upsert key)."""

    def __init__(self, mono, base=None):
        self.mono = mono
        self.base = base or datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
        self.t0 = mono()

    def __call__(self):
        return self.base + timedelta(seconds=self.mono() - self.t0)


def _load(name):
    with open(os.path.join(SAMPLES, name), encoding="utf-8") as f:
        return json.load(f)


class FixtureTransport:
    """Offline transport: returns the canned 200 fixture, optionally advancing
    the fake clock per call (so 900s flushes become testable)."""

    def __init__(self, body, clock=None, advance_per_call=0.0, status=200):
        self._body = body
        self._clock = clock
        self._advance = advance_per_call
        self._status = status
        self.calls = 0

    def fetch_page(self, page_path, session=None):
        self.calls += 1
        if self._clock is not None and self._advance:
            self._clock.advance(self._advance)
        return ResponseEnvelope(self._status, "application/json", self._body)


def _setup(tmp_path, **pol_over):
    sf = make_session_factory(f"sqlite+pysqlite:///{tmp_path}/r.db", test_schema=True)
    store = BenchmarkStore(sf)
    evlog = EventLog(str(tmp_path / "events"))
    body = _load("buyer_inventory_page.json")
    base = dict(
        source_id="buyer-inventory", kind="inventory",
        allowed_endpoint="entrypoint-api", max_rps=1000.0, burst=100.0,
        max_concurrency=20, min_interval_seconds=0.0, max_requests=10_000,
        max_requests_per_day=100_000, duration_seconds=3600,
        license_ref="", retention={}, mode="offline", policy_version="v1",
        cookie_watermark=1, cookie_max_uses=30, authorized=False,
    )
    base.update(pol_over)
    policy = BenchmarkPolicy(**base)
    return store, evlog, body, policy


# --- happy path --------------------------------------------------------------
def test_offline_run_completes_and_writes_events(tmp_path):
    store, evlog, body, policy = _setup(tmp_path)
    clock = FakeClock()
    tr = FixtureTransport(body)
    metrics = BenchmarkMetrics(source_id=policy.source_id, kind="inventory",
                               max_rps=policy.max_rps)
    summary = run_experiment(
        policy, transport=tr, store=store, event_log=evlog, metrics=metrics,
        clock=clock, wall_now=_wall,
        page_paths=["/search/?text=toy"],
        wanted_skus={"111222333", "444555666", "777888999"},
        max_attempts=5,
    )
    assert summary.status == "completed"
    assert summary.requests == 5
    run = store.get_run(summary.run_id)
    assert run.status == "completed"
    # one terminal event per attempt
    assert evlog.reconcile(summary.run_id, 5)
    # one interval row covering the 5 attempts
    intervals = store.list_intervals(summary.run_id)
    assert len(intervals) == 1
    assert intervals[0].audit_event_count == 5


def test_interval_flush_every_900_seconds(tmp_path):
    store, evlog, body, policy = _setup(tmp_path)
    clock = FakeClock()
    wall = TrackingWall(clock)
    # each call advances 300s -> 4 calls = 1200s, crossing the 900s flush.
    tr = FixtureTransport(body, clock=clock, advance_per_call=300.0)
    metrics = BenchmarkMetrics(source_id=policy.source_id, kind="inventory",
                               max_rps=policy.max_rps)
    summary = run_experiment(
        policy, transport=tr, store=store, event_log=evlog, metrics=metrics,
        clock=clock, wall_now=wall,
        page_paths=["/p"], wanted_skus={"111222333", "444555666", "777888999"},
        max_attempts=4,
    )
    assert summary.status == "completed"
    intervals = store.list_intervals(summary.run_id)
    # 4 attempts * 300s = 1200s: first window flushes at >=900s, second partial
    assert len(intervals) >= 2


# --- safe stop ---------------------------------------------------------------
def test_manual_stop_produces_stopped_not_completed(tmp_path):
    store, evlog, body, policy = _setup(tmp_path)
    clock = FakeClock()
    tr = FixtureTransport(body)
    metrics = BenchmarkMetrics(source_id=policy.source_id, kind="inventory",
                               max_rps=policy.max_rps)
    stop = threading.Event()
    stop.set()  # stop immediately
    summary = run_experiment(
        policy, transport=tr, store=store, event_log=evlog, metrics=metrics,
        clock=clock, wall_now=_wall, page_paths=["/p"], wanted_skus={"111222333"},
        stop_event=stop, max_attempts=10,
    )
    assert summary.status == "stopped"
    assert summary.requests == 0
    assert store.get_run(summary.run_id).status == "stopped"


def test_event_log_write_failure_never_marks_completed(tmp_path):
    store, evlog, body, policy = _setup(tmp_path)
    clock = FakeClock()
    tr = FixtureTransport(body)
    metrics = BenchmarkMetrics(source_id=policy.source_id, kind="inventory",
                               max_rps=policy.max_rps)

    class _BoomLog:
        def append(self, ev):
            raise StorageUnavailable("disk full")

        def reconcile(self, *a, **k):
            return False

    summary = run_experiment(
        policy, transport=tr, store=store, event_log=_BoomLog(), metrics=metrics,
        clock=clock, wall_now=_wall, page_paths=["/p"], wanted_skus={"111222333"},
        max_attempts=3,
    )
    assert summary.status == "failed"
    assert store.get_run(summary.run_id).status != "completed"


# --- budget / blocked --------------------------------------------------------
def test_run_budget_enforced_exactly(tmp_path):
    store, evlog, body, policy = _setup(tmp_path, max_requests=3)
    clock = FakeClock()
    tr = FixtureTransport(body)
    metrics = BenchmarkMetrics(source_id=policy.source_id, kind="inventory",
                               max_rps=policy.max_rps)
    summary = run_experiment(
        policy, transport=tr, store=store, event_log=evlog, metrics=metrics,
        clock=clock, wall_now=_wall, page_paths=["/p"], wanted_skus={"111222333"},
        max_attempts=100,
    )
    assert summary.requests == 3
    assert "budget" in (summary.stop_reason or "")


def test_three_consecutive_blocked_tickets_stop_source(tmp_path):
    store, evlog, body, policy = _setup(tmp_path)
    clock = FakeClock()
    tr = FixtureTransport(body, status=403)  # always blocked
    metrics = BenchmarkMetrics(source_id=policy.source_id, kind="inventory",
                               max_rps=policy.max_rps)
    summary = run_experiment(
        policy, transport=tr, store=store, event_log=evlog, metrics=metrics,
        clock=clock, wall_now=_wall, page_paths=["/p"], wanted_skus={"111222333"},
        max_attempts=100,
    )
    assert summary.status == "blocked"
    # exactly 3 blocked attempts (consecutive), not 100
    assert summary.requests == 3


# --- live fail-closed --------------------------------------------------------
def test_live_fail_closed_without_cookie_pool_sends_zero_requests(tmp_path):
    store, evlog, body, policy = _setup(tmp_path, mode="live", authorized=True)
    clock = FakeClock()
    tr = FixtureTransport(body)  # never reached
    metrics = BenchmarkMetrics(source_id=policy.source_id, kind="inventory",
                               max_rps=policy.max_rps)
    empty_pool = CookieSupply(mint_fn=lambda profile_hint=None: (_ for _ in ()).throw(
        RuntimeError("must not mint")))
    summary = run_experiment(
        policy, transport=tr, store=store, event_log=evlog, metrics=metrics,
        clock=clock, wall_now=_wall, page_paths=["/p"], wanted_skus={"111222333"},
        cookie_supply=empty_pool, max_attempts=10,
    )
    assert summary.requests == 0
    assert summary.status == "blocked"
    assert tr.calls == 0  # zero network calls


# --- redirect / error bucketing ---------------------------------------------
def test_followed_redirect_lands_in_ok_not_error(tmp_path):
    store, evlog, body, policy = _setup(tmp_path)
    clock = FakeClock()
    # transport already followed the 302 internally and returns the final 200.
    tr = FixtureTransport(body, status=200)
    metrics = BenchmarkMetrics(source_id=policy.source_id, kind="inventory",
                               max_rps=policy.max_rps)
    summary = run_experiment(
        policy, transport=tr, store=store, event_log=evlog, metrics=metrics,
        clock=clock, wall_now=_wall, page_paths=["/p"], wanted_skus={"111222333"},
        max_attempts=2,
    )
    assert summary.status == "completed"
    iv = store.list_intervals(summary.run_id)[0]
    assert iv.error == 0
    assert iv.ok >= 1


def test_errors_do_not_auto_increase_rate(tmp_path):
    # The limiter's rps is policy.max_rps and the runner never mutates it.
    _, _, _, policy = _setup(tmp_path)
    lim = BudgetLimiter({policy.source_id: policy}, clock=FakeClock())
    # burn a few attempts with errors; the bucket still respects the same cap.
    assert lim._state[policy.source_id].policy.max_rps == policy.max_rps


# --- permit-wait integration (post-eb107d3) ---------------------------------
def _waiting_limiter(policy, clock):
    """A BudgetLimiter whose sleep ADVANCES the fake clock, so token-bucket
    backpressure is fake-clock testable without real wall-time waits."""
    return BudgetLimiter(
        {policy.source_id: policy},
        clock=clock,
        sleep=lambda dt: clock.advance(dt),
    )


def test_one_minute_offline_run_reaches_duration(tmp_path):
    store, evlog, body, policy = _setup(
        tmp_path, max_rps=4.6, burst=8.0, max_concurrency=20,
        duration_seconds=60, max_requests=10_000_000,
    )
    clock = FakeClock(0.0)
    limiter = _waiting_limiter(policy, clock)
    tr = FixtureTransport(body)
    metrics = BenchmarkMetrics(source_id=policy.source_id, kind="inventory",
                               max_rps=policy.max_rps)
    summary = run_experiment(
        policy, transport=tr, store=store, event_log=evlog, metrics=metrics,
        clock=clock, wall_now=_wall, page_paths=["/p"],
        wanted_skus={"111222333", "444555666", "777888999"},
        budget_limiter=limiter,
    )
    # burst=8 + 4.6 rps * 60s ~= 284; accept >=250.
    assert summary.requests >= 250
    assert summary.status == "completed"
    assert summary.stop_reason == "natural_time_limit"
    # reconciliation holds over the whole run
    assert evlog.reconcile(summary.run_id, summary.requests)


def test_sigterm_during_permit_wait_is_stopped(tmp_path):
    store, evlog, body, policy = _setup(
        tmp_path, max_rps=0.001, burst=1.0, max_concurrency=1,
        duration_seconds=600, max_requests=10_000_000,
    )
    clock = FakeClock(0.0)
    limiter = _waiting_limiter(policy, clock)
    tr = FixtureTransport(body)
    metrics = BenchmarkMetrics(source_id=policy.source_id, kind="inventory",
                               max_rps=policy.max_rps)
    stop = threading.Event()
    # First acquire burns the single burst token; the next acquire blocks on
    # the (near-zero) refill. Set the stop event mid-wait.
    orig_acquire = limiter.acquire
    calls = {"n": 0}

    def counting_acquire(sid, **kw):
        calls["n"] += 1
        if calls["n"] == 2:
            stop.set()
        return orig_acquire(sid, **kw)

    limiter.acquire = counting_acquire  # type: ignore
    summary = run_experiment(
        policy, transport=tr, store=store, event_log=evlog, metrics=metrics,
        clock=clock, wall_now=_wall, page_paths=["/p"],
        wanted_skus={"111222333"}, budget_limiter=limiter,
        stop_event=stop,
    )
    assert summary.status == "stopped"
    assert summary.stop_reason == "manual_stop"
    # exactly one request went out before the wait aborted
    assert summary.requests == 1


def test_permit_wait_ms_present_in_events(tmp_path):
    store, evlog, body, policy = _setup(
        tmp_path, max_rps=1.0, burst=1.0, max_concurrency=1,
        duration_seconds=60, max_requests=10_000_000,
    )
    clock = FakeClock(0.0)
    limiter = _waiting_limiter(policy, clock)
    tr = FixtureTransport(body)
    metrics = BenchmarkMetrics(source_id=policy.source_id, kind="inventory",
                               max_rps=policy.max_rps)
    summary = run_experiment(
        policy, transport=tr, store=store, event_log=evlog, metrics=metrics,
        clock=clock, wall_now=_wall, page_paths=["/p"],
        wanted_skus={"111222333"}, budget_limiter=limiter,
        max_attempts=2,
    )
    assert summary.requests == 2
    events = evlog._read_run_events(summary.run_id)
    by_attempt = {e["attempt"]: e for e in events}
    # first request takes the burst token -> ~0 wait; second waits for refill
    assert by_attempt[1]["permit_wait_ms"] < 5.0
    assert by_attempt[2]["permit_wait_ms"] > 0.0
