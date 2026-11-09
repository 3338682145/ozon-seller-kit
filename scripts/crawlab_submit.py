#!/usr/bin/env python3
"""Crawlab CLI bridge: schedule ONLY batches through FastAPI.

Runs inside a Crawlab spider (Python stdlib; no collector/driver packages).
MongoDB receives Crawlab metadata/logs, *never* product rows or secrets.
PostgreSQL owns child job state and Redis Streams owns child deliveries.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

MAX_TASKS = 500
MAX_BATCH_BYTES = 1024 * 1024
BATCH_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
SECRET_KEYS = {"cookie", "token", "authorization", "password", "secret", "api_key", "set_cookie", "x_api_key", "access_token", "refresh_token"}
TASK_KEYS = {"source_id", "endpoint", "kind", "payload", "priority"}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _safe_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise ValueError("API endpoint must not include a path or query")
    if parts.scheme == "https" and parts.hostname and not parts.username and not parts.password:
        return url.rstrip("/")
    if parts.scheme == "http" and parts.hostname == "api" and parts.port == 8000 and not parts.username:
        return url.rstrip("/")
    raise ValueError("API endpoint must be HTTPS or the internal http://api:8000 address")


def _contains_secrets(value, depth=0) -> bool:
    if depth > 20:
        return True
    if isinstance(value, dict):
        return any(k.lower().replace("-", "_") in SECRET_KEYS or _contains_secrets(v, depth + 1) for k, v in value.items())
    if isinstance(value, list):
        return any(_contains_secrets(v, depth + 1) for v in value)
    return False


def _validate_tasks(tasks: list[dict], batch_id: str) -> None:
    if not BATCH_ID.fullmatch(batch_id):
        raise ValueError("invalid Crawlab batch ID")
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= MAX_TASKS:
        raise ValueError("batch must contain 1..500 tasks")
    body = json.dumps(tasks, ensure_ascii=False, separators=(",", ":"))
    if len(body.encode("utf-8")) > MAX_BATCH_BYTES:
        raise ValueError("batch tasks file too large")
    for i, task in enumerate(tasks):
        if not isinstance(task, dict) or not {"source_id", "endpoint", "kind", "payload"}.issubset(task):
            raise ValueError(f"invalid batch task {i}")
        if set(task) - TASK_KEYS or not isinstance(task["payload"], dict) or _contains_secrets(task):
            raise ValueError(f"unapproved keys or credential content in task {i}")
        if not all(isinstance(task[k], str) and 0 < len(task[k]) <= 128 for k in ("source_id", "endpoint", "kind")):
            raise ValueError(f"invalid source/endpoint/kind in task {i}")
        if "priority" in task and (not isinstance(task["priority"], int) or isinstance(task["priority"], bool) or not -10 <= task["priority"] <= 10):
            raise ValueError(f"invalid priority in task {i}")


def _make_http_request(method: str, url: str, body: dict | None, api_key: str, idem: str | None = None) -> dict:
    """No implicit proxy, no redirects, no accidental credential forwarding."""
    headers = {"X-API-Key": api_key, "Accept": "application/json"}
    if idem:
        headers["Idempotency-Key"] = idem
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=data, method=method, headers=headers)
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=15) as response:
            if response.status not in (200, 201):
                raise RuntimeError("batch API returned unexpected status")
            return json.loads(response.read(MAX_BATCH_BYTES))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        # Don't leak URL, headers or upstream response body to Crawlab Mongo logs.
        raise RuntimeError("Crawlab batch API request failed; check FastAPI incidents") from None


def _idempotency_key(batch_id: str, position: int, task: dict) -> str:
    canonical = json.dumps(task, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"crawlab:{batch_id}:{position}:{canonical}".encode()).hexdigest()


def submit(tasks: list[dict], batch_id: str, url: str, api_key: str, *, request_fn=None) -> list[str]:
    """At-least-once Crawlab submission, deduped by PG JobService keys.

    request_fn is injectable for offline tests only; no automatic retries.
    """
    _validate_tasks(tasks, batch_id)
    base = _safe_url(url)
    if not api_key:
        raise ValueError("CRAWLAB_API_KEY is required")
    call = request_fn or _make_http_request
    ids = []
    for idx, task in enumerate(tasks):
        res = call("POST", base + "/api/v1/jobs", {**task, "batch_id": batch_id}, api_key,
                   _idempotency_key(batch_id, idx, task))
        if not isinstance(res, dict) or not isinstance(res.get("id"), str):
            raise RuntimeError("batch API returned no job ID")
        ids.append(res["id"])
    return ids


def wait_for_batch(batch_id: str, url: str, api_key: str, *, max_wait: int = 600, poll_seconds: int = 5,
                   request_fn=None, clock=time.monotonic, sleep=time.sleep) -> dict:
    """An optional bounded wait; never let Crawlab mark an unfinished job complete."""
    if not BATCH_ID.fullmatch(batch_id):
        raise ValueError("invalid batch ID")
    if not (1 <= max_wait <= 3600 and 1 <= poll_seconds <= 60):
        raise ValueError("invalid wait budget")
    base = _safe_url(url)
    call = request_fn or _make_http_request
    deadline = clock() + max_wait
    while True:
        r = call("GET", base + "/api/v1/batches/" + quote(batch_id, safe=""), None, api_key, None)
        if r.get("status") in {"completed", "failed", "partial"}:
            return r
        if clock() >= deadline:
            raise TimeoutError("Crawlab batch exceeded bounded wait; monitor FastAPI batch status")
        sleep(min(poll_seconds, max(0, deadline - clock())))


def main() -> int:
    p = argparse.ArgumentParser(description="Crawlab -> PostgreSQL/Redis batch bridge")
    p.add_argument("tasks", type=Path, help="approved JSON task manifest")
    p.add_argument("--batch-id", default=os.environ.get("CRAWLAB_TASK_ID"))
    p.add_argument("--wait", action="store_true", help="wait for Worker completion, up to --max-wait")
    p.add_argument("--max-wait", type=int, default=600)
    args = p.parse_args()
    if not args.tasks.is_file() or args.tasks.stat().st_size > MAX_BATCH_BYTES:
        print("Invalid task manifest file", file=sys.stderr)
        return 2
    # Each independent scheduled execution receives a unique batch. For an
    # exact retry, pass its original --batch-id (e.g., the Crawlab task ID).
    batch_id = args.batch_id or (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + secrets.token_hex(4))
    try:
        tasks = json.loads(args.tasks.read_text(encoding="utf-8"))
        url = os.environ["CRAWLAB_API_URL"]
        key = os.environ["CRAWLAB_API_KEY"]
        ids = submit(tasks, batch_id, url, key)
        # Crawlab task logs are metadata only, no raw rows / cookies / keys.
        print(json.dumps({"batch_id": batch_id, "submitted": len(ids), "job_ids": ids}))
        if args.wait:
            report = wait_for_batch(batch_id, url, key, max_wait=args.max_wait)
            print(json.dumps({"batch_id": batch_id, "status": report["status"],
                              "completed": report["completed"], "failed": report["failed"]}))
            return 0 if report["status"] == "completed" else 3
        return 0
    except Exception as exc:
        # Explicitly do not print upstream exceptions; they may contain secrets.
        print("Crawlab batch submission failed (invalid input, policy or connectivity)", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
