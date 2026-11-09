"""T1: Lock buyer inventory + review data contracts.

Hard rules under test:
  * maxItems is a PER-PURCHASE CAP proxy, never physical stock -- no
    ``physical_stock`` field may exist.
  * inventory has TWO parallel fields: ``stock_proxy_max_items`` (tile
    maxItems) and ``stock_text_remaining`` (the Russian "осталось N" copy).
  * when maxItems hits the 2000 ceiling, BOTH are kept and ``is_capped`` is
    True -- merging them would produce a flat 2000 series on hot products.
  * missing stock stays NULL, never 0; 0 and NULL are distinct.
  * review score, when present, must be an integer 1..5; out-of-range is
    isolated as invalid and must not enter a valid count.
  * a missing review_id stays NULL -- never synthesised from author+comment.
"""
from __future__ import annotations

from collector.benchmark.contracts import (
    SCHEMA_VERSION,
    InventoryObservation,
    ReviewObservation,
    validate_inventory_record,
    validate_review_record,
)


def _inv(**over):
    base = {
        "sku": "1234567890",
        "page_path": "/search/?text=igrushka",
        "source": "ozon_buyer",
        "region": None,
        "observed_at": "2026-11-09T10:00:00Z",
        "max_items": 1011,
        "stock_text_raw": "Осталось 1011 шт.",
    }
    base.update(over)
    return base


def test_max_items_is_proxy_not_physical():
    obs = validate_inventory_record(_inv(max_items=1011, stock_text_raw="Осталось 1011 шт."))
    assert isinstance(obs, InventoryObservation)
    assert obs.stock_proxy_max_items == 1011
    assert "physical_stock" not in vars(obs)
    assert obs.schema_version == SCHEMA_VERSION


def test_capped_max_items_keeps_text_value():
    obs = validate_inventory_record(
        _inv(max_items=2000, stock_text_raw="3359 ед осталось")
    )
    assert obs.stock_proxy_max_items == 2000
    assert obs.stock_text_remaining == 3359
    assert obs.is_capped is True


def test_unknown_stock_stays_null_not_zero():
    obs = validate_inventory_record(_inv(max_items=None, stock_text_raw=None))
    assert obs.stock_proxy_max_items is None
    assert obs.stock_text_remaining is None
    assert obs.is_capped is False


def test_explicit_zero_is_distinct_from_null():
    obs = validate_inventory_record(_inv(max_items=0, stock_text_raw=None))
    assert obs.stock_proxy_max_items == 0  # sold out, a real observed value
    assert obs.stock_text_remaining is None


def test_noninteger_or_negative_stock_invalid():
    bad = validate_inventory_record(_inv(max_items=-5, stock_text_raw=None))
    assert bad.stock_proxy_max_items is None
    assert bad.field_status.get("stock_proxy_max_items") == "invalid"

    frac = validate_inventory_record(_inv(max_items=12.7, stock_text_raw=None))
    assert frac.stock_proxy_max_items is None
    assert frac.field_status.get("stock_proxy_max_items") == "invalid"


def test_capped_inventory_is_not_physical():
    obs = validate_inventory_record(_inv(max_items=2000, stock_text_raw="Осталось 7 шт."))
    assert obs.is_capped is True
    # capped does NOT mean "2000 physical units"; the text value is the truth
    assert obs.stock_text_remaining == 7
    assert "physical_stock" not in vars(obs)


def test_review_score_range_and_null():
    ok = validate_review_record(
        {"sku": "1", "review_id": "r-1", "score": 5,
         "observed_at": "2026-11-09T10:00:00Z", "source": "ozon_buyer"}
    )
    assert isinstance(ok, ReviewObservation)
    assert ok.score == 5

    bad = validate_review_record(
        {"sku": "1", "review_id": "r-2", "score": 7,
         "observed_at": "2026-11-09T10:00:00Z", "source": "ozon_buyer"}
    )
    assert bad.score is None
    assert bad.field_status.get("score") == "invalid"

    missing = validate_review_record(
        {"sku": "1", "review_id": None, "score": None,
         "observed_at": "2026-11-09T10:00:00Z", "source": "ozon_buyer"}
    )
    assert missing.score is None
    assert missing.field_status.get("score") is None


def test_missing_review_id_does_not_invent_dedupe_key():
    obs = validate_review_record(
        {"sku": "1", "review_id": None, "score": 4,
         "author": "Ivan P.", "comment": "nice",
         "observed_at": "2026-11-09T10:00:00Z", "source": "ozon_buyer"}
    )
    assert obs.review_id is None  # NOT synthesised from author+comment
    assert obs.score == 4
