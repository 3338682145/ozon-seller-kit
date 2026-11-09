"""V2 buyer data contracts.

Inventory observations carry TWO PARALLEL stock fields (spec 10.3):

  * ``stock_proxy_max_items`` -- the tile's ``maxItems`` (the per-purchase
    quantity cap). It is a PROXY, never verified physical stock. Above 2000 it
    is clamped to 2000 by the platform.
  * ``stock_text_remaining`` -- the integer parsed from the Russian tile copy
    ``"N ед осталось"`` / ``"Осталось N шт."``. This is the truth on hot
    products where maxItems is clamped.

When ``max_items == 2000`` we set ``is_capped=True`` and keep BOTH fields.
Merging them into one would produce a flat 2000 series on hot sellers.

Missing stock is NULL, never 0. 0 (genuinely sold out) is a distinct observed
value from NULL (widget absent / field drifted).

Reviews: ``score`` when present must be an integer 1..5; out-of-range is
isolated as invalid. A missing ``review_id`` stays NULL and is never synthesised
from author + comment (that would create a fake dedupe key).

Source of truth for the widget shape: ``ozon_buyer/collector.py:
extract_skus_from_page`` (maxItems path ``multiButton.ozonButton.addToCart.
quantityButton.maxItems`` with mainState fallback) and ``ozon_buyer/detail.py:
parse_reviews``. This module does not re-implement scraping; it normalises the
already-parsed tile/envelope into the V2 observation and flags drift.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

SCHEMA_VERSION = "buyer-v2-1"

# Platform hard cap for the per-purchase quantity button. At/above this the
# value is clamped; the real remaining count lives in the tile copy.
MAX_ITEMS_CAP = 2000

# Russian low-stock copy: "Осталось N шт." / "N ед осталось" / "N шт".
_STOCK_TEXT_RE = re.compile(r"(\d+)\s*(?:ед|шт|pieces|pc)", re.IGNORECASE)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _coerce_int(value: Any) -> Optional[int]:
    """Coerce to int; reject bool, float and non-numeric strings.

    Returns None when the value is missing OR invalid (caller records the
    invalid flag). Negative is invalid stock.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return None  # non-integer -> invalid
    if isinstance(value, str):
        s = value.strip().replace(" ", "")
        if re.fullmatch(r"-?\d+", s):
            return int(s)
    return None


def parse_stock_text(text: Optional[str]) -> Optional[int]:
    """Parse the Russian 'осталось N' copy into an int. None if absent."""
    if not text:
        return None
    if "осталось" not in text.lower() and "остал" not in text.lower():
        return None
    m = _STOCK_TEXT_RE.search(text)
    if not m:
        return None
    return int(m.group(1))


@dataclass
class InventoryObservation:
    sku: str
    page_path: str
    source: str
    observed_at: str
    stock_proxy_max_items: Optional[int] = None
    stock_text_remaining: Optional[int] = None
    region: Optional[str] = None
    is_capped: bool = False
    schema_version: str = SCHEMA_VERSION
    raw_field_paths: Dict[str, str] = field(default_factory=dict)
    field_status: Dict[str, str] = field(default_factory=dict)


@dataclass
class ReviewObservation:
    sku: str
    review_id: Optional[str]
    score: Optional[int]
    observed_at: str
    source: str
    schema_version: str = SCHEMA_VERSION
    field_status: Dict[str, str] = field(default_factory=dict)


def validate_inventory_record(data: Dict[str, Any]) -> InventoryObservation:
    """Normalise a per-tile dict into an InventoryObservation.

    Expected keys: sku, page_path, source, region, observed_at, max_items,
    stock_text_raw. Missing values become NULL; invalid values are flagged in
    ``field_status`` and left NULL rather than faked to 0.
    """
    sku = str(data.get("sku") or "").strip()
    page_path = data.get("page_path") or ""
    source = data.get("source") or "ozon_buyer"
    region = data.get("region")
    observed_at = data.get("observed_at") or _now_iso()

    status: Dict[str, str] = {}

    raw_max = data.get("max_items", None)
    max_items = _coerce_int(raw_max)
    if raw_max is not None and (max_items is None or max_items < 0):
        status["stock_proxy_max_items"] = "invalid"
        max_items = None

    text_remaining = parse_stock_text(data.get("stock_text_raw"))
    if data.get("stock_text_raw") and text_remaining is None:
        # present but unparseable -> leave NULL, flag drift
        status["stock_text_remaining"] = "unparsed"

    is_capped = max_items == MAX_ITEMS_CAP

    return InventoryObservation(
        sku=sku,
        page_path=page_path,
        source=source,
        region=region,
        observed_at=observed_at,
        stock_proxy_max_items=max_items,
        stock_text_remaining=text_remaining,
        is_capped=is_capped,
        raw_field_paths={
            "stock_proxy_max_items": "multiButton.ozonButton.addToCart.quantityButton.maxItems",
            "stock_text_remaining": "mainState[textDS].text",
        },
        field_status=status,
    )


def validate_review_record(data: Dict[str, Any]) -> ReviewObservation:
    """Normalise a per-review dict into a ReviewObservation.

    Expected keys: sku, review_id, score, observed_at, source.
    Score out of 1..5 is isolated as invalid (left NULL). review_id missing
    stays NULL; author/comment are NOT used to invent a dedupe key.
    """
    sku = str(data.get("sku") or "").strip()
    review_id = data.get("review_id")
    observed_at = data.get("observed_at") or _now_iso()
    source = data.get("source") or "ozon_buyer"

    status: Dict[str, str] = {}
    score_raw = data.get("score", None)
    score: Optional[int] = None
    if score_raw is not None:
        s = _coerce_int(score_raw)
        if s is not None and 1 <= s <= 5:
            score = s
        else:
            status["score"] = "invalid"

    return ReviewObservation(
        sku=sku,
        review_id=review_id,
        score=score,
        observed_at=observed_at,
        source=source,
        field_status=status,
    )
