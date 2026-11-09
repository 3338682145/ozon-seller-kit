"""Deterministic fixture source; no network or browser dependencies."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from collector.adapters.base import CollectionTask, SourceAdapter
from collector.errors import DataQualityError


class MockAdapter(SourceAdapter):
    def __init__(self, file_path: str):
        self.file_path = file_path

    async def prepare(self, task: CollectionTask) -> None:
        if task.kind not in {"keyword", "sku", "category", "shop", "import"}:
            raise DataQualityError("unsupported job kind")

    async def fetch(self, task: CollectionTask) -> dict[str, Any]:
        if task.payload.get("simulate_error"):
            from collector.errors import TransientSourceError, PermissionLost
            if task.payload["simulate_error"] == "403":
                raise PermissionLost("HTTP 403")
            raise TransientSourceError("mock fault")
        return json.loads(Path(self.file_path).read_text(encoding="utf-8"))

    async def parse(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        rows = response.get("records")
        if not isinstance(rows, list):
            raise DataQualityError("fixture lacks records array")
        return rows
