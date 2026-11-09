"""ClickHouse append-only fact writer; ReplacingMergeTree versions dedup by key."""
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
import json
from collector.errors import StorageUnavailable
from collector.storage.bulk import stable_id

FACT_TABLES = ("fact_product_daily", "fact_price_history", "fact_sales_daily", "fact_inventory_history", "fact_keyword_daily", "fact_serp_observation", "fact_keyword_sku_daily", "fact_reviews_daily", "fact_category_daily", "fact_collection_metrics")
FIELDS = ("record_key", "source", "observed_at", "calculated_at", "data_type", "dataset_version", "algorithm_version", "ozon_id", "keyword", "position", "is_advert", "price_rub", "gross_units", "gmv_rub", "net_units_est", "net_gmv_est", "metric_value", "payload")


class MemoryFactsSink:
    def __init__(self):
        self.tables: dict[str, dict[str, dict]] = {table: {} for table in FACT_TABLES}

    def write(self, records: list[dict], gold: list[dict]) -> None:
        for table, row in build_rows(records, gold):
            self.tables[table][row["record_key"]] = row


class ClickHouseFactsSink:
    def __init__(self, host: str, user: str, password: str):
        import clickhouse_connect
        self.client = clickhouse_connect.get_client(host=host, username=user, password=password)

    def write(self, records: list[dict], gold: list[dict]) -> None:
        grouped = {}
        for table, row in build_rows(records, gold):
            grouped.setdefault(table, []).append([row.get(c) for c in FIELDS])
        try:
            for table, rows in grouped.items():
                self.client.insert(table, rows, column_names=FIELDS)
        except Exception as exc:
            raise StorageUnavailable("ClickHouse fact write failed") from exc


def _row(table: str, r: dict, *, metric_value: Decimal | None = None):
    day = r["observed_at"].date().isoformat()
    # Product/price/sales facts are keyed by product, NOT by the keyword used
    # to discover that product. SERP facts retain query/slot identity.
    slot = r["observed_at"].isoformat() if table in {"fact_price_history", "fact_inventory_history", "fact_serp_observation"} else day
    scoped_kw = r.get("keyword") if table in {"fact_serp_observation", "fact_keyword_sku_daily", "fact_keyword_daily"} else None
    scoped_pos = r.get("position") if table == "fact_serp_observation" else None
    key = stable_id(f"{table}:{r.get('source')}:{r.get('ozon_id')}:{scoped_kw}:{scoped_pos}:{slot}:{r.get('dataset_version')}")
    return {"record_key": key, "source": r["source"], "observed_at": r["observed_at"], "calculated_at": r["calculated_at"],
            "data_type": r["data_type"], "dataset_version": r["dataset_version"], "algorithm_version": r["algorithm_version"],
            "ozon_id": r.get("ozon_id") or "", "keyword": r.get("keyword") or "",
            "position": r.get("position"), "is_advert": r.get("is_advert"),
            "price_rub": r.get("price_rub"), "gross_units": r.get("gross_units_28d"),
            "gmv_rub": r.get("gross_gmv_rub_28d"),
            "net_units_est": r.get("net_units_est_28d"), "net_gmv_est": r.get("net_gmv_est_rub_28d"),
            "metric_value": metric_value,
            "payload": json.dumps({k: str(r[k]) if isinstance(r[k], Decimal) else r[k]
                                   for k in ("observed_sku_count", "observed_ad_slots", "rank_delta_7d", "rank_delta_30d", "avg_price_rub", "redemption_rate_pct")
                                   if k in r}, ensure_ascii=False)}


def build_rows(records: list[dict], gold: list[dict]):
    for r in records:
        yield "fact_product_daily", _row("fact_product_daily", r)
        if r["price_rub"] is not None:
            yield "fact_price_history", _row("fact_price_history", r)
        if r["gross_units_28d"] is not None:
            yield "fact_sales_daily", _row("fact_sales_daily", r)
        if r.get("keyword") and r.get("position"):
            yield "fact_serp_observation", _row("fact_serp_observation", r)
            yield "fact_keyword_sku_daily", _row("fact_keyword_sku_daily", r)
    for r in gold:
        yield "fact_keyword_daily", _row("fact_keyword_daily", r, metric_value=Decimal(r["observed_sku_count"]))
