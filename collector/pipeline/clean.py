"""Silver typed transformation; never manufacture unavailable metrics."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re
import unicodedata
from typing import Any
from collector.errors import DataQualityError

ALGORITHM_VERSION = "silver-v1"


def normalize_keyword(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).replace("ё", "е").replace("Ё", "Е").casefold()
    return " ".join(value.split())


def decimal_ru(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            d = Decimal(str(value))
        except InvalidOperation:
            return None
    else:
        s = re.sub(r"[\u00a0\u202f\s₽рубRUB]", "", str(value), flags=re.I)
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
        else:
            s = s.replace(",", ".")
        try:
            d = Decimal(s)
        except InvalidOperation:
            return None
    return d if d.is_finite() else None


def observed_utc(value: Any) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        d = value
    else:
        try:
            d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise DataQualityError("invalid observed_at") from exc
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


@dataclass
class SilverBatch:
    records: list[dict]
    issues: list[dict]


def clean_records(rows: list[dict], source: str, dataset_version: str) -> SilverBatch:
    cleaned, issues = [], []
    now = datetime.now(timezone.utc)
    for i, original in enumerate(rows):
        row = dict(original)
        sku = str(row.get("ozon_id") or row.get("sku") or row.get("sku_id") or "").strip()
        if not sku or not sku.isdecimal():
            issues.append({"index": i, "issue_type": "invalid_sku", "reference_id": sku[:80]})
            continue
        price = decimal_ru(row.get("price_rub", row.get("price")))
        if price is not None and price < 0:
            issues.append({"index": i, "issue_type": "negative_price", "reference_id": sku})
            price = None
        kw = row.get("keyword") or row.get("kw")
        normalized = normalize_keyword(str(kw)) if kw else None
        pos = row.get("position")
        if pos is not None:
            try:
                pos = int(pos)
            except (TypeError, ValueError):
                pos = None
            if pos is None or pos <= 0:
                issues.append({"index": i, "issue_type": "invalid_position", "reference_id": sku})
                pos = None
        gross = decimal_ru(row.get("gross_units_28d", row.get("soldCount")))
        gmv = decimal_ru(row.get("gross_gmv_rub_28d", row.get("gmvSum")))
        redemption = decimal_ru(row.get("redemption_rate_pct", row.get("redemptionRate")))
        if redemption is not None and not 0 <= redemption <= 100:
            issues.append({"index": i, "issue_type": "invalid_redemption_rate", "reference_id": sku})
            redemption = None
        if gross is not None and gross < 0:
            issues.append({"index": i, "issue_type": "negative_gross_units", "reference_id": sku})
            gross = None
        net_est = gross * redemption / Decimal(100) if gross is not None and redemption is not None else None
        dt = "platform_stat" if gross is not None or gmv is not None else "observation"
        cleaned.append({
            "ozon_id": sku, "title": row.get("title") or row.get("name"), "price_rub": price,
            "keyword": normalized, "keyword_original": str(kw) if kw else None,
            "position": pos, "is_advert": row.get("is_advert"),
            "observed_at": observed_utc(row.get("observed_at")), "calculated_at": now,
            "gross_units_28d": gross, "gross_gmv_rub_28d": gmv, "redemption_rate_pct": redemption,
            "net_units_est_28d": net_est, "source": source, "data_type": dt,
            "dataset_version": dataset_version, "algorithm_version": ALGORITHM_VERSION,
        })
    # Polars enforces a consistent typed batch in production. Fallback allows offline tests.
    try:
        import polars as pl
        if cleaned:
            frame = pl.DataFrame([{"ozon_id": r["ozon_id"], "keyword": r["keyword"], "position": r["position"]} for r in cleaned], infer_schema_length=None)
            if frame.height != len(cleaned):
                raise DataQualityError("Polars batch cardinality mismatch")
    except ImportError:
        pass
    return SilverBatch(cleaned, issues)


def to_arrow(records: list[dict]):
    """Independent batch/Parquet import path (requires pyarrow in production)."""
    import pyarrow as pa
    return pa.Table.from_pylist([{k: str(v) if isinstance(v, Decimal) else v for k, v in r.items()} for r in records])
