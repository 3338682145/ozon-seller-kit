"""Replayable Gold analytics with provenance gates, not synthetic projections.

Every metric is explicitly sample-scoped. Missing distinct historical snapshots,
Seller IDs, platform volumes or denominators yield None, not a guessed zero.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from collector.pipeline.clean import normalize_keyword, observed_utc, decimal_ru

ALGORITHM_VERSION = "gold-analytics-v1"


def _valid(r: dict) -> bool:
    return bool(r.get("ozon_id") and r.get("observed_at"))


def rank_change(history: list[dict], keyword: str, ozon_id: str, days: int, *, as_of: datetime | None = None, advert: bool | None = False) -> int | None:
    """Positive means improved (old rank - latest rank); exact calendar days only.

    Do not mix paid and organic slots. Unknown ad labels are excluded.
    """
    if days <= 0 or advert is None:
        return None
    kw = normalize_keyword(keyword)
    dated = []
    for row in history:
        if normalize_keyword(str(row.get("keyword") or "")) != kw or str(row.get("ozon_id")) != str(ozon_id) or row.get("is_advert") is not advert:
            continue
        try:
            position = int(row["position"])
            if position <= 0:
                continue
            dt = observed_utc(row["observed_at"])
        except (ValueError, TypeError, KeyError):
            continue
        dated.append((dt, position))
    if not dated:
        return None
    as_of = observed_utc(as_of) if as_of else max(x[0] for x in dated)
    latest_date = as_of.date()
    old_date = latest_date - timedelta(days=days)
    # Last observation for that date wins, preventing an invented interpolated rank.
    today = [x for x in dated if x[0].date() == latest_date]
    old = [x for x in dated if x[0].date() == old_date]
    if not today or not old:
        return None
    return max(old, key=lambda x:x[0])[1] - max(today, key=lambda x:x[0])[1]


def sample_cr4(records: list[dict]) -> dict[str, Any]:
    """Concentration among matched P6 products only, NOT whole-market CR4."""
    sku_units = {}
    for row in records:
        units = decimal_ru(row.get("gross_units_28d"))
        if units is not None and units >= 0 and row.get("ozon_id"):
            sku_units[str(row["ozon_id"])] = units
    total = sum(sku_units.values(), Decimal(0))
    ratio = (sum(sorted(sku_units.values(), reverse=True)[:4], Decimal(0)) / total) if total else None
    return {"cr4_matched_sample": ratio, "matched_skus": len(sku_units), "source_scope": "matched_platform_stat_only"}


def price_change_percent(history: list[dict], ozon_id: str) -> Decimal | None:
    """Two distinct timestamps required; does not conflate SKU variants."""
    series = {}
    for row in history:
        if str(row.get("ozon_id")) != str(ozon_id):
            continue
        price = decimal_ru(row.get("price_rub"))
        if price is None or price < 0:
            continue
        dt = observed_utc(row.get("observed_at"))
        series[dt] = price
    if len(series) < 2:
        return None
    old, current = sorted(series)[-2:]
    return (series[current] - series[old]) * 100 / series[old] if series[old] else None


def observed_ad_share(records: list[dict]) -> Decimal | None:
    """Ads among labeled slots; unknown ad states excluded from denominator."""
    flags = [r["is_advert"] for r in records if r.get("is_advert") is not None and r.get("position") is not None]
    return Decimal(sum(f is True for f in flags)) / len(flags) if flags else None


def brand_hhi(records: list[dict]) -> dict[str, Any]:
    """Share-of-observed SKU HHI, only when every SKU has an identified brand."""
    brands = {}
    for row in records:
        if row.get("ozon_id"):
            brands[str(row["ozon_id"])] = row.get("brand_id")
    if not brands or any(not x for x in brands.values()):
        return {"hhi": None, "brand_coverage": sum(bool(x) for x in brands.values()), "observed_skus": len(brands)}
    by_brand = defaultdict(int)
    for brand in brands.values():
        by_brand[brand] += 1
    n = Decimal(len(brands))
    return {"hhi": sum((Decimal(count) / n) ** 2 for count in by_brand.values()),
            "brand_coverage": len(brands), "observed_skus": len(brands)}


def entry_score(max_slot30: int | None, new_top10_share: Decimal | None) -> Decimal | None:
    """Reproducible documented formula; only accepts verified input observations."""
    if max_slot30 is None or new_top10_share is None or max_slot30 < 0 or not Decimal(0) <= new_top10_share <= Decimal(1):
        return None
    return Decimal(100) * (Decimal("0.60") * (1 - min(Decimal(max_slot30)/10, Decimal(1))) +
                           Decimal("0.40") * min(new_top10_share/Decimal("0.40"), Decimal(1)))
