"""T8: offline end-to-end buyer benchmark.

fixtures -> Adapter -> Runner -> Store -> Report, all in-process, zero sockets.
Asserts:
  * mode=offline;
  * no network is opened (transport is the fixture; no cookie supply);
  * the summary is deterministic for a fixed attempt count;
  * no real Cookie / PII / comment body / author appears in events or report.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

from collector.benchmark.adapters import ResponseEnvelope
from collector.benchmark.events import EventLog
from collector.benchmark.metrics import BenchmarkMetrics
from collector.benchmark.policy import BenchmarkPolicy
from collector.benchmark.report import build_benchmark_report, render_markdown_report
from collector.benchmark.runner import run_experiment
from collector.benchmark.store import BenchmarkStore
from collector.storage.database import make_session_factory

HERE = os.path.dirname(__file__)
SAMPLES = os.path.join(HERE, "..", "samples", "benchmark")


class _NoNetworkTransport:
    """Returns the fixture; raises if anyone tries to touch a real page_path
    that looks like a live host."""

    def __init__(self, body):
        self._body = body
        self.calls = 0

    def fetch_page(self, page_path, session=None) -> ResponseEnvelope:
        assert session is None, "offline e2e must not lease a cookie session"
        assert page_path.startswith("/"), f"unexpected live URL: {page_path}"
        self.calls += 1
        return ResponseEnvelope(200, "application/json", self._body)


def _policy():
    return BenchmarkPolicy(
        source_id="buyer-inventory", kind="inventory",
        allowed_endpoint="entrypoint-api", max_rps=1000.0, burst=100.0,
        max_concurrency=20, min_interval_seconds=0.0, max_requests=10_000,
        max_requests_per_day=100_000, duration_seconds=3600,
        license_ref="", retention={}, mode="offline", policy_version="v1",
        cookie_watermark=1, cookie_max_uses=30, authorized=False,
    )


def test_offline_e2e_pipeline_writes_run_intervals_and_report(tmp_path):
    with open(os.path.join(SAMPLES, "buyer_inventory_page.json"),
              encoding="utf-8") as f:
        body = json.load(f)

    sf = make_session_factory(f"sqlite+pysqlite:///{tmp_path}/e2e.db",
                              test_schema=True)
    store = BenchmarkStore(sf)
    evlog = EventLog(str(tmp_path / "events"))
    tr = _NoNetworkTransport(body)
    metrics = BenchmarkMetrics(source_id="buyer-inventory", kind="inventory",
                               max_rps=1000.0)
    wall = lambda: datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)

    summary = run_experiment(
        _policy(), transport=tr, store=store, event_log=evlog, metrics=metrics,
        wall_now=wall, page_paths=["/search/?text=toys"],
        wanted_skus={"111222333", "444555666", "777888999"},
        max_attempts=4,
    )

    # run finished, mode offline, deterministic 4 attempts
    assert summary.status == "completed"
    assert summary.requests == 4
    run_row = store.get_run(summary.run_id)
    assert run_row.mode == "offline"

    # intervals + reconciliation
    intervals = store.list_intervals(summary.run_id)
    assert len(intervals) == 1
    assert intervals[0].audit_event_count == 4
    assert evlog.reconcile(summary.run_id, 4)

    # report builds and reconciles
    event_count = len(evlog._read_run_events(summary.run_id))
    report = build_benchmark_report(run_row, intervals, max_rps=4.6,
                                    event_log_total=event_count)
    assert report["reconciliation"]["matched"] is True
    md = render_markdown_report(report)

    # no PII / secrets in the on-disk events or the markdown report
    blob = md
    for ev_file in os.listdir(str(tmp_path / "events")):
        with open(os.path.join(str(tmp_path / "events"), ev_file),
                  encoding="utf-8") as f:
            blob += f.read()
    for forbidden in ("abt_data=", "authorization:", "set-cookie",
                      "reviewer", "comment_text"):
        assert forbidden not in blob.lower()
    # no long hex token/cookie blobs
    assert not re.search(r"[a-f0-9]{40,}=", blob.lower())
