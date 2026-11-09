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
    load_benchmark_policy,
    require_live_authorization,
)
from collector.errors import PolicyViolation

HERE = os.path.dirname(__file__)
CFG = os.path.join(HERE, "..", "config", "benchmark")


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, dt):
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


# --- token bucket with fake clock -------------------------------------------
def test_rps_and_burst_enforced():
    clock = FakeClock()
    lim = BudgetLimiter({"buyer-inventory": _policy(max_rps=2.0, burst=5.0)}, clock=clock)
    for _ in range(5):
        lim.acquire("buyer-inventory")  # burst allows 5
    with pytest.raises(BudgetExhausted):
        lim.acquire("buyer-inventory")  # bucket empty
    clock.advance(0.5)  # +1 token at 2 rps
    lim.acquire("buyer-inventory")
    with pytest.raises(BudgetExhausted):
        lim.acquire("buyer-inventory")  # only 1 refilled


def test_run_budget_blocks():
    clock = FakeClock()
    lim = BudgetLimiter({"s": _policy(max_requests=3, burst=100)}, clock=clock)
    for _ in range(3):
        lim.acquire("s")
    with pytest.raises(BudgetExhausted):
        lim.acquire("s")


def test_daily_budget_block():
    clock = FakeClock()
    lim = BudgetLimiter({"s": _policy(max_requests_per_day=2, burst=100, max_requests=1000)}, clock=clock)
    lim.acquire("s"); lim.acquire("s")
    with pytest.raises(BudgetExhausted):
        lim.acquire("s")


def test_shared_budget_across_tasks():
    clock = FakeClock()
    pol = _policy(source_id="shared", burst=4.0, max_rps=100)
    lim = BudgetLimiter({"shared": pol}, clock=clock)
    # two "tasks" draw from the same source bucket: 4 burst, 5th refused
    for _ in range(4):
        lim.acquire("shared")
    with pytest.raises(BudgetExhausted):
        lim.acquire("shared")


def test_review_inventory_limits_are_isolated():
    clock = FakeClock()
    inv = _policy(source_id="buyer-inventory", burst=2.0)
    rev = _policy(source_id="buyer-reviews", kind="reviews", burst=1.0)
    lim = BudgetLimiter({"buyer-inventory": inv, "buyer-reviews": rev}, clock=clock)
    lim.acquire("buyer-inventory"); lim.acquire("buyer-inventory")
    with pytest.raises(BudgetExhausted):
        lim.acquire("buyer-inventory")
    # reviews bucket untouched -> still works
    lim.acquire("buyer-reviews")
    with pytest.raises(BudgetExhausted):
        lim.acquire("buyer-reviews")


def test_retries_consume_budget():
    clock = FakeClock()
    lim = BudgetLimiter({"s": _policy(burst=2.0, max_rps=100)}, clock=clock)
    p1 = lim.acquire("s"); p2 = lim.acquire("s")  # tokens -> 0
    lim.release(p1); lim.release(p2)
    clock.advance(0.1)  # refill back to burst=2
    lim.acquire("s")  # retry attempt consumes a fresh token
    lim.acquire("s")
    with pytest.raises(BudgetExhausted):
        lim.acquire("s")  # exhausted


def test_concurrency_limit_holds():
    clock = FakeClock()
    lim = BudgetLimiter({"s": _policy(max_concurrency=2, burst=100)}, clock=clock)
    p1 = lim.acquire("s")
    p2 = lim.acquire("s")
    with pytest.raises(BudgetExhausted):
        lim.acquire("s")
    lim.release(p1)
    lim.acquire("s")  # slot freed


def test_example_yaml_files_are_offline_not_guessed():
    inv = load_benchmark_policy(os.path.join(CFG, "buyer-inventory.example.yaml"), mode="offline")
    rev = load_benchmark_policy(os.path.join(CFG, "buyer-reviews.example.yaml"), mode="offline")
    assert inv.mode == "offline" and inv.authorized is False
    assert rev.mode == "offline" and rev.authorized is False
    # offline must never raise on live-authorisation check
    require_live_authorization(inv)
    require_live_authorization(rev)
