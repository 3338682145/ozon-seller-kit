"""All sources must implement the same five-stage contract."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from collector.errors import DataQualityError


@dataclass(frozen=True)
class CollectionTask:
    job_id: str
    source_id: str
    endpoint: str
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)


class SourceAdapter(ABC):
    async def prepare(self, task: CollectionTask) -> None:
        """Validate permissions and schema; never mint or rotate credentials."""

    @abstractmethod
    async def fetch(self, task: CollectionTask) -> dict[str, Any]: ...

    @abstractmethod
    async def parse(self, response: dict[str, Any]) -> list[dict[str, Any]]: ...

    async def validate(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(records, list):
            raise DataQualityError("adapter must return a list")
        if any(not isinstance(r, dict) for r in records):
            raise DataQualityError("each record must be an object")
        return records

    async def report_error(self, error: Exception, task: CollectionTask) -> dict[str, str]:
        """Sanitize: no URL params, headers, cookie values or response snippets."""
        return {"error_type": type(error).__name__, "source_id": task.source_id, "job_id": task.job_id}
