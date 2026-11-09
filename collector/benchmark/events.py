"""Durable, sanitised JSONL event log.

Every HTTP attempt produces exactly ONE terminal event. The log serialises only
the runtime-contract whitelist (spec 10.1); cookie / authorization / URL query
strings / review author / comment / exception text are never stored.

Rotation is by day and by size; retention (30 days for request events) is the
operator's job. A failed append raises ``StorageUnavailable`` and must stop the
run -- no evidence-less requests.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from collector.errors import StorageUnavailable

WHITELIST = (
    "ts_utc", "run_id", "source_id", "endpoint_id", "batch_id", "request_id",
    "attempt", "status_code", "outcome", "duration_ms", "permit_wait_ms",
    "response_bytes", "observed_records", "accepted_records", "schema_version",
    "validation_error_codes", "raw_sha256", "write_status", "reason_code",
)

MAX_BYTES = 10 * 1024 * 1024  # 10 MB before rotation


@dataclass
class RequestAuditEvent:
    ts_utc: str
    run_id: str
    source_id: str
    endpoint_id: str
    batch_id: str
    request_id: str
    attempt: int
    status_code: int
    outcome: str
    duration_ms: float
    permit_wait_ms: float
    response_bytes: int
    observed_records: int
    accepted_records: int
    schema_version: str
    validation_error_codes: List[str] = field(default_factory=list)
    raw_sha256: Optional[str] = None
    write_status: str = "written"
    reason_code: Optional[str] = None


def safe_event_dict(event: RequestAuditEvent) -> dict:
    """Serialise ONLY whitelist keys. raw_sha256 is dropped unless explicitly
    present (it is only ever recorded with approval)."""
    out: Dict[str, Any] = {}
    data = vars(event)
    for key in WHITELIST:
        if key == "raw_sha256":
            continue  # never emit a raw digest by default
        out[key] = data.get(key)
    return out


class EventLog:
    """JSONL log rotated by day and size. Fail-closed on write/read errors."""

    def __init__(self, directory: str) -> None:
        self.dir = directory
        os.makedirs(self.dir, exist_ok=True)

    def _path(self) -> str:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return os.path.join(self.dir, f"events-{day}.jsonl")

    def _maybe_rotate(self, path: str) -> None:
        if os.path.exists(path) and os.path.getsize(path) >= MAX_BYTES:
            # simple rotate to .1
            alt = path + ".1"
            if os.path.exists(alt):
                os.remove(alt)
            os.rename(path, alt)

    def _write_line(self, line: str) -> None:  # pragma: no cover - thin seam
        path = self._path()
        self._maybe_rotate(path)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def append(self, event: RequestAuditEvent) -> None:
        try:
            self._write_line(json.dumps(safe_event_dict(event), ensure_ascii=False))
        except StorageUnavailable:
            raise
        except Exception as e:  # disk full, permissions, ...
            raise StorageUnavailable(f"event log write failed: {e}") from e

    def _read_run_events(self, run_id: str) -> List[dict]:
        out: List[dict] = []
        path = self._path()
        if not os.path.exists(path):
            return out
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    if rec.get("run_id") == run_id:
                        out.append(rec)
        except Exception:
            # unreadable log -> fail closed
            raise StorageUnavailable("event log unreadable during reconcile")
        return out

    def reconcile(self, run_id: str, expected_attempts: int) -> bool:
        """True iff exactly ``expected_attempts`` terminal events exist for
        run_id and every (request_id, attempt) is unique."""
        try:
            events = self._read_run_events(run_id)
        except StorageUnavailable:
            return False
        if len(events) != expected_attempts:
            return False
        seen = set()
        for ev in events:
            key = (ev.get("request_id"), ev.get("attempt"))
            if key in seen:
                return False
            seen.add(key)
        return True
