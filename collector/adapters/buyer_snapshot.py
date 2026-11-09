"""Offline-only reuse of upstream *pure* parsing code. No browser warm-up.

Actual Buyer network access remains blocked pending explicit legal authorization.
"""
from __future__ import annotations
from typing import Any
from collector.adapters.base import CollectionTask, SourceAdapter
from collector.errors import DataQualityError, PermissionLost

PARSERS = {
    "buyer_search": ("ozon_buyer.collector", "extract_skus_from_page"),
    "buyer_detail": ("ozon_buyer.detail", "parse_pdp1"),
    "buyer_reviews": ("ozon_buyer.detail", "parse_reviews"),
    "buyer_offers": ("ozon_buyer.browser", "offers_extract"),
}


class BuyerSnapshotAdapter(SourceAdapter):
    def __init__(self, source_id: str):
        if source_id not in PARSERS:
            raise ValueError("unknown buyer snapshot parser")
        self.source_id = source_id

    async def prepare(self, task: CollectionTask) -> None:
        if task.payload.get("url") or "snapshot" not in task.payload:
            raise PermissionLost("offline snapshot only; live Buyer collection disabled")

    async def fetch(self, task: CollectionTask) -> dict[str, Any]:
        return task.payload["snapshot"]

    async def parse(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        # Optional upstream dependencies may be absent in an overlay-only checkout.
        import importlib
        mod, fn = PARSERS[self.source_id]
        try:
            parser = getattr(importlib.import_module(mod), fn)
        except (ImportError, AttributeError) as exc:
            raise DataQualityError("upstream Buyer parser unavailable; use original repository checkout") from exc
        result = parser(response if self.source_id == "buyer_search" else response.get("widgetStates", {}))
        if isinstance(result, dict):
            return result.get("reviews") or result.get("sellers") or [result]
        if not isinstance(result, list):
            raise DataQualityError("unsupported upstream parse result")
        return result
