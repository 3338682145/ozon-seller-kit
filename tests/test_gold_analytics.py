from datetime import datetime, timedelta, timezone
from decimal import Decimal
from collector.pipeline.analytics import (rank_change, sample_cr4, price_change_percent,
                                          observed_ad_share, brand_hhi, entry_score)

def test_rank_delta_needs_two_real_observations_seven_days_apart():
    today = datetime(2026,11,9,tzinfo=timezone.utc)
    hist = [{"keyword":"Ёлка", "ozon_id":"5", "position":3, "is_advert":False, "observed_at":today},
            {"keyword":"елка", "ozon_id":"5", "position":8, "is_advert":False, "observed_at":today-timedelta(days=7)},
            {"keyword":"елка", "ozon_id":"5", "position":1, "is_advert":True, "observed_at":today-timedelta(days=7)}]
    assert rank_change(hist, "ёлка", "5", 7) == 5
    assert rank_change(hist, "ёлка", "5", 30) is None
    assert rank_change(hist, "ёлка", "5", 7, advert=True) is None


def test_sample_share_and_brand_confidence():
    sample = [{"ozon_id":str(i), "gross_units_28d":i, "brand_id":"A" if i%2 else "B"} for i in range(1,6)]
    x = sample_cr4(sample)
    assert x["cr4_matched_sample"] == Decimal(14) / Decimal(15)
    assert brand_hhi(sample)["hhi"] == Decimal(13)/Decimal(25)
    assert brand_hhi([{"ozon_id":"1", "brand_id":None}])["hhi"] is None
    assert sample_cr4([{"ozon_id":"1", "gross_units_28d":None}])["cr4_matched_sample"] is None


def test_price_hist_and_unknown_ad_labels():
    old = datetime(2026,11,1,tzinfo=timezone.utc)
    rows = [{"ozon_id":"7", "price_rub":"100", "observed_at":old},
            {"ozon_id":"7", "price_rub":"120", "observed_at":old+timedelta(days=1)}]
    assert price_change_percent(rows,"7") == Decimal(20)
    assert price_change_percent(rows[:1],"7") is None
    assert observed_ad_share([{"is_advert":None,"position":1}]) is None
    assert observed_ad_share([{"is_advert":True,"position":2}, {"is_advert":False,"position":3}]) == Decimal("0.5")


def test_entry_score_does_not_guess_missing_inputs():
    assert entry_score(3, Decimal("0.30")) == Decimal(72)
    assert entry_score(None, Decimal("0.3")) is None
    assert entry_score(1, Decimal("1.1")) is None


def test_fact_keys_do_not_duplicate_product_from_multiple_keywords():
    from collector.pipeline.clean import clean_records
    from collector.storage.facts import MemoryFactsSink
    dt = "2026-11-09T00:00:00Z"
    batch = clean_records([{"sku":"101", "keyword":"Ёлка", "position":1, "price":"99", "observed_at":dt},
                           {"sku":"101", "keyword":"игрушки", "position":3, "price":"99", "observed_at":dt}],"mock","v1")
    sink = MemoryFactsSink()
    sink.write(batch.records, [])
    assert len(sink.tables["fact_product_daily"]) == 1
    assert len(sink.tables["fact_price_history"]) == 1
    assert len(sink.tables["fact_serp_observation"]) == 2
    assert len(sink.tables["fact_keyword_sku_daily"]) == 2
