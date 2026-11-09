"""T0: Cookie supply gate.

The pool logic (lease least-used, mark_dead, replenish, redaction) is exercised
offline with an injected mint function. The real CDP mint is heavy/network-bound
and is only driven by the `--mint-once` CLI plus the documented online smoke.

Hard invariants under test:
  * an empty pool NEVER implicitly mints inside lease() (no surprise browser);
  * lease() picks the least-used non-dead session and bumps use_count;
  * mark_dead removes a session from rotation WITHOUT resetting use_count;
  * replenish(watermark) explicitly fills up to the watermark;
  * serialised events never carry the cookie_header plaintext;
  * launch args strip proxies (--no-proxy-server) and env proxies are removed;
  * fingerprint.audit() rejects cross-machine assembled combos.
"""
from __future__ import annotations

import time

import pytest

from collector.benchmark import fingerprint
from collector.benchmark.cookie_supply import (
    CookieSupply,
    MintFailed,
    PoolEmpty,
    Session,
    build_launch_args,
    session_redacted,
    strip_proxy_env,
)


def _mk(sid: str, clock, use_count: int = 0) -> Session:
    return Session(
        id=sid,
        cookie_header="abt_data=" + ("z" * 700) + "; ssid=abc",
        ua="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/146.0.0.0",
        impersonate="chrome146",
        profile_id="macbook-pro-14-m3",
        minted_at=clock(),
        use_count=use_count,
    )


def test_pool_empty_lease_does_not_implicitly_mint():
    calls = []

    def mint_fn(**_kw):
        calls.append(1)
        return _mk("s1", time.time)

    sup = CookieSupply(mint_fn=mint_fn, clock=time.time)
    with pytest.raises(PoolEmpty):
        sup.lease()
    assert calls == []  # lease must not open a browser


def test_lease_picks_least_used_and_counts():
    clock = lambda: 1000.0  # noqa: E731
    sup = CookieSupply(mint_fn=lambda **_k: None, clock=clock)
    sup._sessions = {"a": _mk("a", clock, use_count=5), "b": _mk("b", clock, use_count=1)}

    s1 = sup.lease()
    assert s1.id == "b" and s1.use_count == 2  # b was 1 -> 2
    s2 = sup.lease()
    # after b=2, a=5 -> a still lower? a=5 > b=2, so b should win again.
    assert s2.id == "b"
    assert sup._sessions["b"].use_count == 3


def test_mark_dead_drops_from_rotation_but_keeps_count():
    clock = lambda: 1000.0  # noqa: E731
    sup = CookieSupply(mint_fn=lambda **_k: None, clock=clock)
    sup._sessions = {"a": _mk("a", clock)}
    sup.lease()  # use_count 1
    sup.mark_dead("a")
    assert sup._sessions["a"].state == "dead"
    assert sup._sessions["a"].use_count == 1  # NOT reset
    with pytest.raises(PoolEmpty):
        sup.lease()


def test_replenish_fills_to_watermark_and_not_above():
    clock = lambda: 1000.0  # noqa: E731
    seq = iter(["s1", "s2", "s3", "s4", "s5"])

    def mint_fn(**_k):
        return _mk(next(seq), clock)

    sup = CookieSupply(mint_fn=mint_fn, clock=clock)
    sup.replenish(3)
    assert sup.available_count() == 3
    sup.replenish(5)
    assert sup.available_count() == 5


def test_session_redacted_has_no_cookie_plaintext():
    clock = lambda: 1000.0  # noqa: E731
    s = _mk("s1", clock)
    ev = session_redacted(s)
    assert "cookie_header" not in ev
    # the raw value must not leak into the serialised event
    assert "abt_data=zzz" not in str(ev)
    assert "zzzzz" not in str(ev)
    # but length metadata is allowed
    assert ev["cookie_len"] == len(s.cookie_header)
    assert ev["id"] == "s1"


def test_launch_args_force_no_proxy():
    args = build_launch_args("/usr/local/bin/chromium", 9222, "/tmp/udd", headless=True)
    assert "--no-proxy-server" in args
    assert not any(a.startswith("--proxy-server=") for a in args)


def test_strip_proxy_env_removes_every_case_variant():
    env = {
        "PATH": "/usr/bin",
        "HTTP_PROXY": "http://vortex:8080",
        "http_proxy": "http://vortex:8080",
        "HTTPS_PROXY": "http://vortex:8080",
        "https_proxy": "http://vortex:8080",
        "ALL_PROXY": "socks5://127.0.0.1",
    }
    out = strip_proxy_env(env)
    for key in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        assert key not in out
    assert out["PATH"] == "/usr/bin"


def test_vendored_profiles_self_consistent():
    for i in range(12):
        p = fingerprint.pick(seed=i)
        assert fingerprint.audit(p) == [], f"profile {p['id']} failed audit"


def test_fingerprint_audit_blocks_cross_machine_combo():
    p = fingerprint.pick(seed=1)  # some macOS/Windows row
    assert fingerprint.audit(p) == []
    bad = dict(p)
    # keep the macOS UA string but swap platform to Linux -> contradiction
    bad["platform"] = "Linux"
    bad["platform_ver"] = "14.6.1"
    problems = fingerprint.audit(bad)
    assert problems, "cross-machine assembled fingerprint must be rejected"
