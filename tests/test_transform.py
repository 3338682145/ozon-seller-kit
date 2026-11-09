from decimal import Decimal
import pytest
from collector.pipeline.clean import clean_records, normalize_keyword, decimal_ru
from collector.pipeline.gold import keyword_sku_metrics


def test_russian_keyword_price_and_uncertainty():
    assert normalize_keyword("  Ёлка   Антистресс ") == "елка антистресс"
    assert decimal_ru("1 234,56 ₽") == Decimal("1234.56")
    assert decimal_ru("1.234,56 руб") == Decimal("1234.56")
    b = clean_records([{"sku": "1", "keyword": "Ёлка", "price": "299,10 ₽", "soldCount": 3, "redemptionRate": None}], "mock", "v1")
    assert b.records[0]["net_units_est_28d"] is None
    assert b.records[0]["data_type"] == "platform_stat"
    assert b.issues == []


def test_quality_records_flagged_not_invented():
    b = clean_records([{"sku": "bad", "price": 10}, {"sku": "123", "price": -1, "position": -7, "redemptionRate": 105}], "mock", "v1")
    assert len(b.records) == 1
    assert {x["issue_type"] for x in b.issues} == {"invalid_sku", "negative_price", "invalid_position", "invalid_redemption_rate"}
    assert b.records[0]["price_rub"] is None
    assert b.records[0]["position"] is None


def test_gold_rank_delta_unknown_until_historical_samples():
    b = clean_records([{"sku": "111", "keyword": "test", "position": 1}], "mock", "v1")
    g = keyword_sku_metrics(b.records, version="v1")
    assert g[0]["rank_delta_7d"] is None
    assert g[0]["rank_delta_30d"] is None


def test_sparse_old_snapshot_does_not_erase_master(rig):
    from datetime import datetime, timezone
    from collector.storage.bulk import write_silver
    from collector.storage.models import Product
    from collector.pipeline.clean import clean_records
    j = rig["jobs"].create(source_id="mock", endpoint="sample", kind="sku", payload={})
    with rig["sf"].begin() as db:
        write_silver(db, clean_records([{"sku":"77", "title":"trusted title", "price":"100", "observed_at":"2026-11-09T00:00:00Z"}], "mock", "v1"), j.id)
    with rig["sf"].begin() as db:
        write_silver(db, clean_records([{"sku":"77", "title":None, "price":None, "observed_at":"2026-11-10T00:00:00Z"}], "mock", "v2"), j.id)
    with rig["sf"]() as db:
        p = db.get(Product,"77")
        assert p.title == "trusted title"
        assert p.price_rub == 100
    with rig["sf"].begin() as db:
        write_silver(db, clean_records([{"sku":"77", "title":"stale", "price":"5", "observed_at":"2026-11-08T00:00:00Z"}], "mock", "v0"), j.id)
    with rig["sf"]() as db:
        p = db.get(Product, "77")
        assert p.title == "trusted title" and p.price_rub == 100
