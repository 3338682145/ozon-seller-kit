"""Crawlab batch entrypoint: enqueue API jobs; NEVER run Redis subtask workers.

Deploy this script as a Crawlab spider after approving the host and API key.
Expected input: a JSON list of {source_id, endpoint, kind, payload, priority?}.
No actual Ozon requests are performed in this script.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
import httpx


def submit_batch(tasks: list[dict], batch_id: str, api_url: str, api_key: str,
                 transport: httpx.BaseTransport | None = None) -> list[str]:
    parsed = urlsplit(api_url)
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"api", "127.0.0.1", "localhost"}):
        raise ValueError("Crawlab API URL must be trusted HTTPS or private Compose host")
    if not api_key or len(batch_id) > 128:
        raise ValueError("API key and bounded batch ID required")
    result = []
    with httpx.Client(base_url=api_url.rstrip("/"), timeout=10,
                      headers={"X-API-Key": api_key}, trust_env=False,
                      follow_redirects=False, transport=transport) as client:
        for i, task in enumerate(tasks):
            if not isinstance(task, dict) or not {"source_id", "endpoint", "kind", "payload"}.issubset(task):
                raise ValueError(f"invalid batch task at index {i}")
            key = hashlib.sha256(f"crawlab:{batch_id}:{i}".encode()).hexdigest()
            res = client.post("/api/v1/jobs", json={**task, "batch_id": batch_id},
                              headers={"Idempotency-Key": key})
            res.raise_for_status()  # no infinite retry or credential renewal
            result.append(res.json()["id"])
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("tasks", type=Path)
    p.add_argument("--batch-id", required=True)
    args = p.parse_args()
    tasks = json.loads(args.tasks.read_text(encoding="utf-8"))
    if not isinstance(tasks, list):
        raise SystemExit("tasks file must be a JSON list")
    jobs = submit_batch(tasks, args.batch_id, os.environ["CRAWLAB_API_URL"], os.environ["CRAWLAB_API_KEY"])
    print(json.dumps({"batch_id": args.batch_id, "enqueued": len(jobs), "job_ids": jobs}))


if __name__ == "__main__":
    main()
