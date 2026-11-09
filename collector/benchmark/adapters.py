"""Isolated inventory / review adapters.

The adapters ONLY:
  * fetch through an injected ``BuyerTransport`` (Fake/offline by default; a
    live HTTP transport borrows the leased session's cookie/ua/impersonate and
    follows redirects, but never solves the challenge, rotates proxy or
    identity -- those live in the cookie supply gate);
  * normalise with Kit's pure parsers (``extract_skus_from_page`` /
    ``parse_reviews``) and the V2 contracts.

They never call ``BuyerClient.ensure_creds``, ``PoolClient`` or ``cdp_warmup``.
In offline tests no socket is opened.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

from collector.benchmark.contracts import (
    InventoryObservation,
    ReviewObservation,
    validate_inventory_record,
    validate_review_record,
)


@dataclass
class ResponseEnvelope:
    status_code: int
    content_type: str
    body: Any  # parsed envelope dict (or raw string)
    final_url: str = ""


class BuyerTransport(Protocol):
    def fetch_page(self, page_path: str, session: Any = None) -> ResponseEnvelope: ...


# --- Kit pure-parser reuse (lazy import; no network at import time) -----------
def _extract_tiles(body: Any) -> List[dict]:
    from ozon_buyer.collector import extract_skus_from_page
    try:
        return extract_skus_from_page(body) or []
    except Exception:
        return []


def _text_by_sku(body: Any) -> Dict[str, Optional[str]]:
    """Walk the tile grid and pull the Russian 'осталось N' copy per SKU.

    Kit's extractor surfaces maxItems but not the low-stock copy; V2 adds the
    Russian-aware text extraction here (the old http.py only matched Chinese
    '仅剩').
    """
    out: Dict[str, Optional[str]] = {}
    if not isinstance(body, dict):
        return out
    ws = body.get("widgetStates", {})
    if not isinstance(ws, dict):
        return out
    for key, raw in ws.items():
        if not any(m in key for m in ("searchResultsV2", "tileGrid")):
            continue
        try:
            val = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            continue
        for it in (val or {}).get("items", []) or []:
            sku = it.get("sku") or it.get("id")
            link = (it.get("action") or {}).get("link") or ""
            if not sku and link:
                import re
                m = re.search(r"/product/.*?(\d{6,14})", link.split("?")[0])
                if m:
                    sku = m.group(1)
            if not sku:
                continue
            text = None
            for st in it.get("mainState") or []:
                if st.get("type") == "textDS":
                    t = (st.get("textDS") or {}).get("text") or ""
                    if "остал" in t.lower():
                        text = t
                        break
            out[str(sku)] = text
    return out


def collect_inventory_page(
    transport: BuyerTransport,
    page_path: str,
    wanted_skus: set,
    observed_at: str,
    session: Any = None,
) -> List[InventoryObservation]:
    env = transport.fetch_page(page_path, session)
    tiles = _extract_tiles(env.body)
    texts = _text_by_sku(env.body)
    wanted = {str(s) for s in wanted_skus}
    out: List[InventoryObservation] = []
    for t in tiles:
        sku = str(t.get("sku_id") or "").strip()
        if not sku or sku not in wanted:
            continue
        obs = validate_inventory_record({
            "sku": sku,
            "page_path": page_path,
            "source": "ozon_buyer",
            "observed_at": observed_at,
            "max_items": t.get("stock_max"),
            "stock_text_raw": texts.get(sku),
        })
        out.append(obs)
    return out


def collect_review_page(
    transport: BuyerTransport,
    sku: str,
    page_path: str,
    observed_at: str,
    session: Any = None,
) -> List[ReviewObservation]:
    env = transport.fetch_page(page_path, session)
    from ozon_buyer.detail import parse_reviews
    try:
        parsed = parse_reviews(env.body.get("widgetStates", {}) if isinstance(env.body, dict) else {})
    except Exception:
        parsed = None
    if not parsed:
        return []
    out: List[ReviewObservation] = []
    for row in parsed.get("rows", []) or []:
        obs = validate_review_record({
            "sku": str(sku),
            "review_id": row.get("uuid"),
            "score": row.get("rating"),
            "observed_at": observed_at,
            "source": "ozon_buyer",
        })
        # out-of-range score is isolated (dropped); a valid score with a missing
        # review_id is still kept (review_id stays NULL, never invented).
        if obs.field_status.get("score") == "invalid":
            continue
        out.append(obs)
    return out
