"""Source policy + fixed single-process budget limiter.

Inventory and reviews are independent sources with independent budgets. When a
policy file omits numeric limits we fall back to the conservative Kit starting
values (20 concurrency, 30 uses/cookie, 4.6 rps) and mark them ``estimated``;
we do NOT reject and we do NOT adopt ozon-crawler-local constants.

Live mode without explicit authorisation fails closed (PolicyViolation). The
budget limiter is a token bucket driven by an injectable (monotonic) clock so
rps / burst / concurrency / run and daily budgets are fake-clock testable.
Retries consume a fresh token. A per-ticket 403/429 marks that ticket dead in
the cookie pool (T0) -- it does not stop the whole source.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from collector.errors import PolicyViolation

# Conservative Kit starting values (estimated until the 12h run re-tunes them).
DEFAULTS = dict(
    max_rps=4.6,
    burst=8.0,
    max_concurrency=20,
    min_interval_seconds=0.0,
    max_requests=100_000,
    max_requests_per_day=1_000_000,
    duration_seconds=43200,
    cookie_watermark=1,
    cookie_max_uses=30,
)


@dataclass
class BenchmarkPolicy:
    source_id: str
    kind: str  # inventory | reviews
    allowed_endpoint: str
    max_rps: float
    burst: float
    max_concurrency: int
    min_interval_seconds: float
    max_requests: int
    max_requests_per_day: int
    duration_seconds: int
    license_ref: str
    retention: dict
    mode: str  # offline | live
    policy_version: str
    cookie_watermark: int
    cookie_max_uses: int
    authorized: bool = False

    def __post_init__(self) -> None:
        _validate(self)


def _validate(p: BenchmarkPolicy) -> None:
    if p.cookie_watermark < 1:
        raise PolicyViolation("cookie_watermark must be >= 1")
    if p.cookie_max_uses < 1:
        raise PolicyViolation("cookie_max_uses must be >= 1")
    if p.max_concurrency < 1:
        raise PolicyViolation("max_concurrency must be >= 1")
    if p.max_rps <= 0:
        raise PolicyViolation("max_rps must be > 0")


def load_benchmark_policy(path: Optional[str], mode: str) -> BenchmarkPolicy:
    """Load a YAML policy, merging conservative defaults.

    ``path`` may be None -> pure defaults (offline). Unknown/empty numeric
    fields fall back to DEFAULTS rather than rejecting.
    """
    data: dict = {}
    if path:
        import yaml
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

    def num(key, cast=float, default=None):
        v = data.get(key, default)
        if v is None:
            return cast(DEFAULTS[key])
        try:
            return cast(v)
        except (TypeError, ValueError):
            return cast(DEFAULTS[key])

    p = BenchmarkPolicy(
        source_id=data.get("source_id") or "buyer-benchmark",
        kind=data.get("kind") or "inventory",
        allowed_endpoint=data.get("allowed_endpoint") or "entrypoint-api",
        max_rps=num("max_rps"),
        burst=num("burst"),
        max_concurrency=int(num("max_concurrency", int)),
        min_interval_seconds=num("min_interval_seconds"),
        max_requests=int(num("max_requests", int)),
        max_requests_per_day=int(num("max_requests_per_day", int)),
        duration_seconds=int(num("duration_seconds", int)),
        license_ref=data.get("license_ref") or "",
        retention=data.get("retention") or {},
        mode=mode,
        policy_version=data.get("policy_version") or "v1",
        cookie_watermark=int(num("cookie_watermark", int)),
        cookie_max_uses=int(num("cookie_max_uses", int)),
        authorized=bool(data.get("authorized", False)),
    )
    _validate(p)
    return p


def require_live_authorization(policy: BenchmarkPolicy) -> None:
    """Offline mode always passes. Live mode requires explicit authorisation and
    concrete numeric limits; anything else fails closed."""
    if policy.mode != "live":
        return
    if not policy.authorized:
        raise PolicyViolation("live benchmark requires authorized: true")
    if policy.max_rps is None or policy.max_concurrency is None:
        raise PolicyViolation("live benchmark requires concrete rps/concurrency")


class BudgetExhausted(Exception):
    """Raised when the limiter refuses an acquire; carries the refusal reason."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class PermitWaitAborted(Exception):
    """Waiting for a rate/concurrency permit was interrupted by the run clock
    or a stop event. This is NOT a terminal budget exhaustion -- the runner maps
    it to stopped/stop, not stopped/budget."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason  # "deadline" | "stop"


@dataclass
class Permit:
    source_id: str
    permit_wait_ms: float = 0.0
    token: bool = True


class _SourceState:
    def __init__(self, policy: BenchmarkPolicy):
        self.policy = policy
        self.tokens: float = policy.burst
        self.last: float = 0.0
        self.in_use: int = 0
        self.used_run: int = 0
        self.used_day: int = 0


_WAIT_SLICE_S = 0.05  # backpressure slice; refill on every slice


class BudgetLimiter:
    """Per-source token bucket. Single process; a shared Redis permit is a
    separate multi-process integration test, not this gate.

    Backpressure contract (spec 10.2): rps and concurrency limits WAIT (with a
    recorded ``permit_wait_ms``) rather than terminating the run. Only a real
    terminal budget (run / daily max_requests) or an unknown source raises
    ``BudgetExhausted``. Waiting can be interrupted by a deadline or a stop
    event, which raises ``PermitWaitAborted`` (distinct reason).
    """

    def __init__(
        self,
        policies: Dict[str, BenchmarkPolicy],
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._clock = clock
        self._sleep = sleep
        self._state = {sid: _SourceState(p) for sid, p in policies.items()}

    def _refill(self, st: _SourceState, now: float) -> None:
        if st.last == 0.0:
            st.last = now
        elapsed = max(0.0, now - st.last)
        st.tokens = min(st.policy.burst, st.tokens + elapsed * st.policy.max_rps)
        st.last = now

    def acquire(self, source_id: str, *, deadline: Optional[float] = None,
                stop_event: Any = None) -> Permit:
        st = self._state.get(source_id)
        if st is None:
            raise BudgetExhausted(f"unknown source {source_id}")

        # Terminal budgets are checked up front and after every wait slice.
        if st.used_run >= st.policy.max_requests:
            raise BudgetExhausted("run budget exhausted")
        if st.used_day >= st.policy.max_requests_per_day:
            raise BudgetExhausted("daily budget exhausted")

        wait_start = self._clock()
        while True:
            now = self._clock()
            self._refill(st, now)
            if st.in_use < st.policy.max_concurrency and st.tokens >= 1.0:
                st.tokens -= 1.0
                st.in_use += 1
                st.used_run += 1
                st.used_day += 1
                return Permit(source_id=source_id,
                              permit_wait_ms=(self._clock() - wait_start) * 1000.0)

            # terminal guard during a long wait
            if st.used_run >= st.policy.max_requests or \
               st.used_day >= st.policy.max_requests_per_day:
                raise BudgetExhausted("budget exhausted")
            if deadline is not None and now >= deadline:
                raise PermitWaitAborted("deadline")
            if stop_event is not None and stop_event.is_set():
                raise PermitWaitAborted("stop")
            self._sleep(_WAIT_SLICE_S)

    def release(self, permit: Permit) -> None:
        st = self._state.get(permit.source_id)
        if st is not None:
            st.in_use = max(0, st.in_use - 1)
