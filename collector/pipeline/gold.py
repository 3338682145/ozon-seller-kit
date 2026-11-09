"""Gold metrics: only compute statistics justified by observed records."""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

ALGORITHM_VERSION = "gold-v1"


def keyword_sku_metrics(records: list[dict], *, version: str) -> list[dict]:
    by_kw = defaultdict(list)
    for r in records:
        if r.get("keyword") and r.get("position") is not None:
            by_kw[r["keyword"]].append(r)
    now = datetime.now(timezone.utc)
    results = []
    for kw, group in by_kw.items():
        unique_skus = {r["ozon_id"] for r in group}
        prices = [r["price_rub"] for r in group if r["price_rub"] is not None]
        adverts = [r for r in group if r["is_advert"] is True]
        # Presence in a SERP is not proof of the full searchable universe.
        results.append({"keyword": kw, "observed_sku_count": len(unique_skus),
                        "observed_ad_slots": len(adverts),
                        "min_observed_price_rub": min(prices) if prices else None,
                        "source": group[0]["source"], "observed_at": max(r["observed_at"] for r in group),
                        "calculated_at": now, "data_type": "observation",
                        "dataset_version": version, "algorithm_version": ALGORITHM_VERSION,
                        "rank_delta_7d": None, "rank_delta_30d": None})
    return results
