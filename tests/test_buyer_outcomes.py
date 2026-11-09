"""T2: classify buyer responses and sanitise the event log.

Six outcomes: ok | empty_valid | empty_suspect | blocked | transient_error | invalid.

Rules:
  * 401/403/429 and an HTML antibot/challenge page -> blocked (never counted as
    empty stock, never retried on the same ticket).
  * 5xx / 408 / 425 -> transient_error.
  * 200 with the expected widget and records -> ok.
  * 200 with the expected widget but explicitly zero records -> empty_valid.
  * 200 with NO expected widget (silent empty / shape drift) -> empty_suspect.
  * non-JSON / unparseable body -> invalid.
  * 3xx is a normal search-page redirect, NOT a rejection.

The event log serialises only the whitelist keys; cookie, authorization,
token-bearing URLs and review author/comment must never appear.
"""
from __future__ import annotations

import json

import pytest

from collector.benchmark.events import EventLog, RequestAuditEvent, safe_event_dict
from collector.benchmark.outcomes import classify_buyer_response
from collector.errors import StorageUnavailable


def _envelope(widget: dict) -> dict:
    return {"widgetStates": {k: json.dumps(v, ensure_ascii=False) for k, v in widget.items()}}


# --- classification ---------------------------------------------------------
def test_200_with_valid_tile_is_ok():
    body = _envelope({"searchResultsV2-1-5": {"items": [{"sku": 1}, {"sku": 2}]}})
    assert classify_buyer_response(200, "application/json", body, "inventory") == "ok"


def test_200_explicit_empty_reviews_is_empty_valid():
    body = _envelope({"webListReviews-1-1": {"paging": {"total": 0}, "reviews": []}})
    assert classify_buyer_response(200, "application/json", body, "reviews") == "empty_valid"


def test_200_missing_widget_is_empty_suspect():
    body = _envelope({"someOtherWidget-1-1": {"foo": 1}})
    assert classify_buyer_response(200, "application/json", body, "inventory") == "empty_suspect"


def test_access_restriction_blocks_source():
    assert classify_buyer_response(403, "application/json", {}, "inventory") == "blocked"
    assert classify_buyer_response(401, "application/json", {}, "reviews") == "blocked"
    assert classify_buyer_response(429, "application/json", {}, "inventory") == "blocked"


def test_challenge_html_is_blocked():
    body = "<html><head><title>Antibot Challenge Page</title></head><body></body>"
    assert classify_buyer_response(200, "text/html", body, "inventory") == "blocked"


def test_5xx_is_transient_error():
    assert classify_buyer_response(503, "application/json", {}, "inventory") == "transient_error"
    assert classify_buyer_response(500, "application/json", {}, "reviews") == "transient_error"


def test_invalid_json_is_invalid():
    assert classify_buyer_response(200, "application/json", "not-a-json", "inventory") == "invalid"
    assert classify_buyer_response(404, "application/json", {}, "inventory") == "invalid"


def test_redirect_is_not_a_rejection():
    # 3xx is the normal search-page redirect; classify must not call it blocked.
    assert classify_buyer_response(302, "text/html", "", "inventory") in ("empty_suspect", "invalid")


# --- sanitisation ------------------------------------------------------------
def _ev(**over) -> RequestAuditEvent:
    base = dict(
        ts_utc="2026-11-09T10:00:00Z", run_id="run-1", source_id="buyer-inventory",
        endpoint_id="entrypoint", batch_id="b1", request_id="req-1", attempt=1,
        status_code=200, outcome="ok", duration_ms=12.0, permit_wait_ms=1.0,
        response_bytes=1234, observed_records=8, accepted_records=8,
        schema_version="buyer-v2-1", validation_error_codes=[],
        raw_sha256=None, write_status="written", reason_code=None,
    )
    base.update(over)
    return RequestAuditEvent(**base)


def test_event_never_serializes_secret_fields():
    ev = _ev()
    d = safe_event_dict(ev)
    blob = json.dumps(d, ensure_ascii=False)
    for forbidden in ("cookie", "authorization", "bearer", "set-cookie", "http://", "https://",
                      "author", "comment", "token", "abt_data="):
        assert forbidden not in blob.lower(), f"leaked {forbidden}: {blob}"
    # whitelist only (raw_sha256 is dropped by safe_event_dict unless explicitly approved)
    expected = {"ts_utc", "run_id", "source_id", "endpoint_id", "batch_id", "request_id",
                "attempt", "status_code", "outcome", "duration_ms", "permit_wait_ms",
                "response_bytes", "observed_records", "accepted_records", "schema_version",
                "validation_error_codes", "write_status", "reason_code"}
    assert set(d.keys()) == expected


# --- durable log + reconciliation -------------------------------------------
def test_one_terminal_event_per_attempt(tmp_path):
    log = EventLog(tmp_path)
    log.append(_ev(request_id="r1", attempt=1))
    log.append(_ev(request_id="r1", attempt=2))
    # exactly 2 attempts for run-1
    assert log.reconcile("run-1", expected_attempts=2) is True
    # duplicate (request_id, attempt) -> fail closed
    log.append(_ev(request_id="r1", attempt=1))
    assert log.reconcile("run-1", expected_attempts=3) is False


def test_log_write_failure_halts_run(tmp_path, monkeypatch):
    log = EventLog(tmp_path)
    ev = _ev(request_id="r9", attempt=1)
    # simulate disk failure
    monkeypatch.setattr(EventLog, "_write_line", lambda self, line: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(StorageUnavailable):
        log.append(ev)


def test_log_interval_count_reconciliation(tmp_path):
    log = EventLog(tmp_path)
    for i in range(5):
        log.append(_ev(request_id=f"r{i}", attempt=1))
    assert log.reconcile("run-1", expected_attempts=5) is True
    # a different run_id with mismatched count
    log.append(_ev(run_id="run-2", request_id="x", attempt=1))
    assert log.reconcile("run-1", expected_attempts=6) is False
