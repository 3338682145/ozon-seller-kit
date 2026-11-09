"""Executable CLI for the buyer 12-hour benchmark.

Offline (the only mode that actually runs today):

    python -m collector.benchmark.cli \\
        --mode offline --kind inventory \\
        --policy config/benchmark/buyer-inventory.example.yaml \\
        --fixture samples/benchmark/buyer_inventory_page.json \\
        --duration-seconds 60 --out /tmp/bench-out/

Live mode requires an explicit approved policy (``authorized: true``) and a
working cookie supply. With no minted sessions it fails CLOSED: zero requests,
status=blocked, and a report explaining the blocker. There is NO default live
mode -- omitting ``--mode`` exits rather than guessing.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import tempfile
from datetime import datetime, timezone

from collector.benchmark.adapters import ResponseEnvelope
from collector.benchmark.events import EventLog
from collector.benchmark.metrics import BenchmarkMetrics
from collector.benchmark.policy import (
    BenchmarkPolicy,
    load_benchmark_policy,
    require_live_authorization,
)
from collector.benchmark.report import build_benchmark_report, render_markdown_report
from collector.benchmark.runner import run_experiment
from collector.benchmark.store import BenchmarkStore
from collector.storage.database import make_session_factory


class _FixtureTransport:
    """Offline transport: returns the canned fixture, zero sockets."""

    def __init__(self, body, status=200):
        self._body = body
        self._status = status

    def fetch_page(self, page_path, session=None) -> ResponseEnvelope:
        return ResponseEnvelope(self._status, "application/json", self._body)


def _parse_wanted_skus(raw):
    if not raw:
        return None
    return {s.strip() for s in raw.split(",") if s.strip()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Buyer 12-hour benchmark runner")
    ap.add_argument("--mode", choices=["offline", "live"], required=True)
    ap.add_argument("--kind", choices=["inventory", "reviews"], default="inventory")
    ap.add_argument("--policy", default=None, help="path to benchmark YAML policy")
    ap.add_argument("--fixture", default=None, help="offline: path to canned JSON")
    ap.add_argument("--duration-seconds", type=int, default=60)
    ap.add_argument("--out", default=None, help="output directory")
    ap.add_argument("--wanted-skus", default=None,
                    help="comma-separated SKUs to observe")
    ap.add_argument("--max-attempts", type=int, default=None,
                    help="test hook: cap attempts")
    args = ap.parse_args(argv)

    out = args.out or tempfile.mkdtemp(prefix="ozon-bench-")
    os.makedirs(out, exist_ok=True)

    policy = load_benchmark_policy(args.policy, mode=args.mode)
    # CLI override for the smoke duration.
    policy.duration_seconds = args.duration_seconds

    stop_event = _install_signal_handlers()

    if args.mode == "live":
        # Fail closed: no live transport is auto-created and no cookie supply is
        # auto-minted here. The runner will lease from an (empty) pool and stop
        # with status=blocked, requests=0.
        try:
            require_live_authorization(policy)
        except Exception as e:
            print(json.dumps({"status": "blocked", "reason": f"policy: {e}"},
                             ensure_ascii=False))
            return 2
        cookie_supply = None  # would be CookieSupply(); minting is operator-driven
    else:
        cookie_supply = None
        if not args.fixture or not os.path.exists(args.fixture):
            print(json.dumps({"status": "failed",
                              "reason": "offline mode requires --fixture"},
                             ensure_ascii=False))
            return 2
        with open(args.fixture, encoding="utf-8") as f:
            body = json.load(f)

    db_path = os.path.join(out, "benchmark.sqlite")
    sf = make_session_factory(f"sqlite+pysqlite:///{db_path}", test_schema=True)
    store = BenchmarkStore(sf)
    event_log = EventLog(os.path.join(out, "events"))
    metrics = BenchmarkMetrics(source_id=policy.source_id, kind=policy.kind,
                               max_rps=policy.max_rps)

    if args.mode == "offline":
        transport = _FixtureTransport(body)
    else:
        # live: no transport wired up (no egress). The runner's lease attempt
        # on an empty pool will block out before any fetch.
        transport = _FixtureTransport({})  # never called

    wanted = _parse_wanted_skus(args.wanted_skus)
    summary = run_experiment(
        policy, transport=transport, store=store, event_log=event_log,
        metrics=metrics, page_paths=["/search/?text=toys"],
        wanted_skus=wanted or set(), stop_event=stop_event,
        max_attempts=args.max_attempts, cookie_supply=cookie_supply,
    )

    run_row = store.get_run(summary.run_id)
    intervals = store.list_intervals(summary.run_id)
    # count terminal events on disk for reconciliation
    event_count = _count_events(event_log, summary.run_id)
    report = build_benchmark_report(run_row, intervals, max_rps=policy.max_rps,
                                   event_log_total=event_count)
    md = render_markdown_report(report)

    with open(os.path.join(out, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as f:
        f.write(md)

    print(json.dumps({
        "run_id": summary.run_id, "status": summary.status,
        "stop_reason": summary.stop_reason, "requests": summary.requests,
        "intervals": summary.intervals, "mode": policy.mode,
        "out_dir": out,
    }, ensure_ascii=False))
    return 0 if summary.status in ("completed", "stopped") else 1


def _count_events(event_log: EventLog, run_id: str) -> int:
    try:
        return len(event_log._read_run_events(run_id))
    except Exception:
        return -1


def _install_signal_handlers():
    import threading
    stop = threading.Event()

    def _handler(signum, frame):
        stop.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handler)
        except Exception:
            pass
    return stop


if __name__ == "__main__":
    raise SystemExit(main())
