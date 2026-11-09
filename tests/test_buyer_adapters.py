"""T4: isolated inventory / review adapters.

Adapters fetch through an injected BuyerTransport (Fake by default) and reuse
Kit's pure parsers. They never call BuyerClient.ensure_creds / PoolClient /
cdp_warmup, never rotate proxy or identity, and never touch the network in
offline tests.

Rules under test:
  * only requested SKUs produce observations (page provenance attached);
  * an absent wanted SKU yields NO invented zero;
  * a valid reviews widget maps its records;
  * out-of-range review scores are isolated, not counted;
  * missing / wrong widget -> empty_suspect, never an empty "success";
  * fixtures cause no network.
"""
from __future__ import annotations

import json
import os

import pytest

from collector.benchmark.adapters import (
    BuyerTransport,
    ResponseEnvelope,
    collect_inventory_page,
    collect_review_page,
)
from collector.benchmark.outcomes import classify_buyer_response

HERE = os.path.dirname(__file__)
SAMPLES = os.path.join(HERE, "..", "samples", "benchmark")


class FakeTransport:
    """Offline transport returning a canned envelope; records calls."""

    def __init__(self, envelope: ResponseEnvelope):
        self._env = envelope
        self.calls = []

    def fetch_page(self, page_path, session=None) -> ResponseEnvelope:
        self.calls.append(page_path)
        return self._env


def _load(name):
    with open(os.path.join(SAMPLES, name), encoding="utf-8") as f:
        return json.load(f)


# --- inventory --------------------------------------------------------------
def test_inventory_maps_only_wanted_skus_with_provenance():
    body = _load("buyer_inventory_page.json")
    env = ResponseEnvelope(200, "application/json", body)
    tr = FakeTransport(env)
    obs = collect_inventory_page(
        tr, "/search/?text=igrushka",
        wanted_skus={"111222333", "444555666", "777888999"},
        observed_at="2026-11-09T10:00:00Z",
    )
    assert len(obs) == 3
    by_sku = {o.sku: o for o in obs}
    # provenance
    assert by_sku["111222333"].page_path == "/search/?text=igrushka"
    assert by_sku["111222333"].source == "ozon_buyer"
    # normal
    assert by_sku["111222333"].stock_proxy_max_items == 1011
    # capped hot product: both fields kept, is_capped
    hot = by_sku["444555666"]
    assert hot.stock_proxy_max_items == 2000
    assert hot.stock_text_remaining == 3359
    assert hot.is_capped is True
    # missing maxItems -> NULL, not 0
    assert by_sku["777888999"].stock_proxy_max_items is None
    assert by_sku["777888999"].stock_text_remaining is None


def test_inventory_absent_sku_invents_no_zero():
    body = _load("buyer_inventory_page.json")
    env = ResponseEnvelope(200, "application/json", body)
    tr = FakeTransport(env)
    obs = collect_inventory_page(
        tr, "/search/?text=igrushka",
        wanted_skus={"999999999"},  # not on the page
        observed_at="2026-11-09T10:00:00Z",
    )
    assert obs == []  # no invented 0 stock


def test_wrong_widget_is_empty_suspect_not_success():
    body = {"widgetStates": {"someUnrelatedWidget-1-1": {"foo": 1}}}
    env = ResponseEnvelope(200, "application/json", body)
    tr = FakeTransport(env)
    assert classify_buyer_response(200, "application/json", body, "inventory") == "empty_suspect"
    obs = collect_inventory_page(
        tr, "/search/?x", wanted_skus={"111222333"},
        observed_at="2026-11-09T10:00:00Z",
    )
    assert obs == []


# --- reviews ----------------------------------------------------------------
def test_reviews_maps_valid_records_and_isolates_bad_score():
    body = _load("buyer_reviews_widget.json")
    env = ResponseEnvelope(200, "application/json", body)
    tr = FakeTransport(env)
    rows = collect_review_page(
        tr, sku="444555666", page_path="/product/444555666/reviews/",
        observed_at="2026-11-09T10:00:00Z",
    )
    scores = sorted(r.score for r in rows)
    assert scores == [4, 5]  # the score=9 review is isolated, not counted
    by_id = {r.review_id: r for r in rows}
    assert "rev-0001" in by_id and "rev-0002" in by_id
    assert "rev-0003" not in by_id  # invalid score dropped


def test_reviews_missing_widget_is_empty_suspect():
    body = {"widgetStates": {"webOther-1-1": {}}}
    env = ResponseEnvelope(200, "application/json", body)
    tr = FakeTransport(env)
    rows = collect_review_page(
        tr, sku="1", page_path="/product/1/reviews/",
        observed_at="2026-11-09T10:00:00Z",
    )
    assert rows == []


def test_fixtures_attempt_no_network():
    body = _load("buyer_inventory_page.json")
    env = ResponseEnvelope(200, "application/json", body)
    tr = FakeTransport(env)
    collect_inventory_page(tr, "/x", {"111222333"}, "2026-11-09T10:00:00Z")
    assert tr.calls == ["/x"]  # only the injected call; no socket opened
