"""T3: source policy + fixed budget limiter (fake-clock driven).

Inventory and reviews are independent sources. Missing numeric limits fall back
to the conservative Kit starting values (20 concurrency, 30 uses/cookie, 4.6
rps) rather than rejecting. Live mode without explicit authorisation fails
closed. Retries consume budget. A per-ticket 403/429 breaks that ticket, not
the whole source.
"""
from __future__ import annotations

import os

import pytest

from collector.benchmark.policy import (
    BudgetExhausted,
    BudgetLimiter,
    BenchmarkPolicy,
    PermitWaitAborted,
    load_benchmark_policy,
    require_live_authorization,
)
from collector.errors import PolicyViolation

HERE = os.path.dirname(__file__)
CFG = os.path.join(HERE, "..", "config", "benchmark")


class FakeClock:
    """Fake monotonic clock whose sleep advances the clock (no real waiting)."""

    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt

    def sleep(self, dt):
        self.t += dt


def _policy(**over) -> BenchmarkPolicy:
    base = dict(
        source_id="buyer-inventory", kind="inventory",
        allowed_endpoint="entrypoint-api", max_rps=4.6, burst=8.0,
        max_concurrency=20, min_interval_seconds=0.0, max_requests=10_000,
        max_requests_per_day=100_000, duration_seconds=3600,
        license_ref="", retention={}, mode="offline", policy_version="v1",
        cookie_watermark=1, cookie_max_uses=30, authorized=False,
    )
    base.update(over)
    return BenchmarkPolicy(**base)


# --- defaults / validation ---------------------------------------------------
def test_missing_budget_falls_back_to_conservative_defaults():
    p = load_benchmark_policy(None, mode="offline")
    assert p.max_concurrency == 20
    assert p.cookie_max_uses == 30
    assert p.max_rps == 4.6


def test_bad_cookie_watermark_or_max_uses_rejected():
    with pytest.raises(PolicyViolation):
        _policy(cookie_watermark=0)
    with pytest.raises(PolicyViolation):
        _policy(cookie_max_uses=0)


def test_live_requires_explicit_authorization():
    off = _policy(mode="offline")
    require_live_authorization(off)  # offline passes

    live = _policy(mode="live", authorized=False)
    with pytest.raises(PolicyViolation):
        require_live_authorization(live)


# --- token bucket with fake clock (backpressure, not termination) -----------
def _limiter(policy, clock):
    return BudgetLimiter({"s": policy}, clock=clock, sleep=clock.sleep)


class _Stop:
    def __init__(self):
        self.flag = False

    def is_set(self):
        return self.flag

    def set(self):
        self.flag = True


def test_rps_exhaustion_waits_instead_of_terminating():
    clock = FakeClock()
    lim = _limiter(_policy(max_rps=1.0, burst=1.0), clock)
    permits = [lim.acquire("s") for _ in range(5)]  # all granted, none lost
    waits = [p.permit_wait_ms for p in permits]
    assert waits[0] == 0.0            # first is instant
    assert sum(waits[1:]) > 0.0       # later ones waited via backpressure


def test_rps_and_burst_enforced():
    # burst allows the first 5 instantly; the 6th waits rather than terminating
    clock = FakeClock()
    lim = _limiter(_policy(max_rps=2.0, burst=5.0), clock)
    grants = [lim.acquire("s") for _ in range(5)]
    assert all(g.permit_wait_ms == 0.0 for g in grants)
    sixth = lim.acquire("s")  # waits for refill, does NOT raise
    assert sixth.permit_wait_ms > 0.0


def test_run_budget_still_terminal():
    clock = FakeClock()
    lim = _limiter(_policy(max_requests=3, burst=100), clock)
    for _ in range(3):
        lim.acquire("s")
    with pytest.raises(BudgetExhausted):
        lim.acquire("s")  # terminal: run budget exhausted


def test_daily_budget_block():
    clock = FakeClock()
    lim = _limiter(_policy(max_requests_per_day=2, burst=100, max_requests=1000), clock)
    lim.acquire("s"); lim.acquire("s")
    with pytest.raises(BudgetExhausted):
        lim.acquire("s")  # terminal: daily budget


def test_shared_budget_across_tasks():
    clock = FakeClock()
    pol = _policy(source_id="shared", burst=4.0, max_rps=100)
    lim = BudgetLimiter({"shared": pol}, clock=clock, sleep=clock.sleep)
    for _ in range(4):
        lim.acquire("shared")  # burst exhausted
    # 5th waits (backpressure) rather than terminating
    fifth = lim.acquire("shared")
    assert fifth.permit_wait_ms > 0.0


def test_concurrency_backpressure_waits_fake():
    # deterministic fake-clock version: block until release frees a slot
    clock = FakeClock()
    lim = BudgetLimiter({"s": _policy(max_concurrency=1, burst=100.0, max_rps=100.0)},
                         clock=clock, sleep=clock.sleep)
    p1 = lim.acquire("s")
    # p2 can't grant now; release the slot on the first sleep slice
    state = {"released": False}
    orig_sleep = clock.sleep

    def release_sleep(dt):
        if not state["released"]:
            lim.release(p1)
            state["released"] = True
        orig_sleep(dt)
    lim._sleep = release_sleep
    p2 = lim.acquire("s")
    assert state["released"] is True
    assert p2.permit_wait_ms > 0.0


def test_review_inventory_limits_are_isolated():
    clock = FakeClock()
    inv = _policy(source_id="buyer-inventory", burst=2.0, max_rps=100.0)
    rev = _policy(source_id="buyer-reviews", kind="reviews", burst=1.0, max_rps=100.0)
    lim = BudgetLimiter({"buyer-inventory": inv, "buyer-reviews": rev},
                         clock=clock, sleep=clock.sleep)
    lim.acquire("buyer-inventory"); lim.acquire("buyer-inventory")
    # inventory 3rd waits (does not touch reviews)
    inv3 = lim.acquire("buyer-inventory")
    assert inv3.permit_wait_ms > 0.0
    # reviews bucket is independent -> instant grant
    r1 = lim.acquire("buyer-reviews")
    assert r1.permit_wait_ms == 0.0


def test_retries_consume_budget():
    clock = FakeClock()
    lim = _limiter(_policy(burst=2.0, max_rps=100.0), clock)
    p1 = lim.acquire("s"); p2 = lim.acquire("s")  # tokens -> 0
    lim.release(p1); lim.release(p2)
    clock.advance(0.1)  # refill back to burst=2
    a = lim.acquire("s")  # retry consumes a fresh token
    b = lim.acquire("s")
    c = lim.acquire("s")  # waits for refill, does NOT raise
    assert c.permit_wait_ms > 0.0


def test_wait_interrupted_by_deadline():
    clock = FakeClock()
    lim = _limiter(_policy(max_rps=1.0, burst=1.0), clock)
    lim.acquire("s")  # consume the single token
    deadline = clock.t + 0.1  # need ~1.0s at 1 rps; deadline far earlier
    with pytest.raises(PermitWaitAborted) as ei:
        lim.acquire("s", deadline=deadline)
    assert ei.value.reason == "deadline"


def test_wait_interrupted_by_stop_event():
    clock = FakeClock()
    lim = BudgetLimiter({"s": _policy(max_concurrency=1, burst=100.0, max_rps=100.0)},
                        clock=clock, sleep=clock.sleep)
    p1 = lim.acquire("s")
    stop = _Stop()
    # first sleep slice triggers the stop event
    orig_sleep = clock.sleep
    def stop_sleep(dt):
        stop.set()
        orig_sleep(dt)
    lim._sleep = stop_sleep
    with pytest.raises(PermitWaitAborted) as ei:
        lim.acquire("s", stop_event=stop)
    assert ei.value.reason == "stop"


def test_example_yaml_files_are_offline_not_guessed():
    inv = load_benchmark_policy(os.path.join(CFG, "buyer-inventory.example.yaml"), mode="offline")
    rev = load_benchmark_policy(os.path.join(CFG, "buyer-reviews.example.yaml"), mode="offline")
    assert inv.mode == "offline" and inv.authorized is False
    assert rev.mode == "offline" and rev.authorized is False
    # offline must never raise on live-authorisation check
    require_live_authorization(inv)
    require_live_authorization(rev)
