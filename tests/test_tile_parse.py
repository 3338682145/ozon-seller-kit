"""买家 tile 纯解析的离线单测（不联网、不起浏览器）。

运行：python3 -m unittest discover -s tests -v
"""
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "ozon_tile_parse", ROOT / "ozon_buyer" / "tile_parse.py"
)
tile_parse = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tile_parse)

_MISSING = object()


def _tile(advert=_MISSING, max_items=_MISSING, use_main_state_fallback=False):
    """构造一张最小可解析的搜索卡片（结构与 entrypoint-api 的 tile 一致）。"""
    tile = {
        "sku": "1234567",
        "action": {"link": "/product/1234567/?advert=1"},
        "cellTrackingInfo": {"title": "Тестовый товар", "price": "1 299 ₽", "reviewCount": "1 234"},
    }
    if advert is not _MISSING:
        tile["trackingInfo"] = {"click": {"custom": {"advertLite": advert}}}
    if max_items is not _MISSING:
        if use_main_state_fallback:
            tile["mainState"] = [{"type": "quantityButton", "quantityButton": {"maxItems": max_items}}]
        else:
            tile["multiButton"] = {"ozonButton": {"addToCart": {"quantityButton": {"maxItems": max_items}}}}
    return tile


class AdvertFlagTest(unittest.TestCase):
    """is_advert 必须是三态，不能把未知压成 False。"""

    def test_missing_tracking_info_is_unknown(self):
        self.assertIsNone(tile_parse.parse_advert_flag(_tile()))

    def test_explicit_true(self):
        self.assertIs(tile_parse.parse_advert_flag(_tile(advert=True)), True)

    def test_explicit_false(self):
        self.assertIs(tile_parse.parse_advert_flag(_tile(advert=False)), False)

    def test_explicit_null_is_unknown(self):
        self.assertIsNone(tile_parse.parse_advert_flag(_tile(advert=None)))

    def test_empty_object_is_unknown(self):
        self.assertIsNone(tile_parse.parse_advert_flag(_tile(advert={})))

    def test_non_dict_tile_is_unknown(self):
        self.assertIsNone(tile_parse.parse_advert_flag(None))
        self.assertIsNone(tile_parse.parse_advert_flag("not a tile"))


class StockMaxTest(unittest.TestCase):
    """stock_max 规范为 int/None，0 与「无信息」必须可区分。"""

    def test_int_value(self):
        self.assertEqual(tile_parse.parse_stock_max(_tile(max_items=12)), 12)

    def test_string_value(self):
        self.assertEqual(tile_parse.parse_stock_max(_tile(max_items="12")), 12)

    def test_thousand_separator(self):
        self.assertEqual(tile_parse.parse_stock_max(_tile(max_items="1 234")), 1234)

    def test_zero_is_preserved(self):
        self.assertEqual(tile_parse.parse_stock_max(_tile(max_items=0)), 0)

    def test_missing_is_none(self):
        self.assertIsNone(tile_parse.parse_stock_max(_tile()))

    def test_main_state_fallback(self):
        tile = _tile(max_items="2 000", use_main_state_fallback=True)
        self.assertEqual(tile_parse.parse_stock_max(tile), 2000)

    def test_garbage_is_none(self):
        self.assertIsNone(tile_parse.parse_stock_max(_tile(max_items="n/a")))

    def test_bool_is_rejected(self):
        # bool 是 int 的子类，不能被当成库存数字
        self.assertIsNone(tile_parse.parse_stock_max(_tile(max_items=True)))


class WidgetKeyTest(unittest.TestCase):
    """collector 与 http 必须认同同一批 widget key。"""

    def test_recognised_keys(self):
        for key in ("searchResultsV2-1", "tileGridDesktop-2", "tile-3", "searchResultsV2"):
            self.assertTrue(tile_parse.is_tile_widget_key(key), key)

    def test_rejected_keys(self):
        for key in ("header", "footer", "webSale", None, 123):
            self.assertFalse(tile_parse.is_tile_widget_key(key), key)


class IterTileItemsTest(unittest.TestCase):
    def test_unwraps_string_body(self):
        page = {"body": json.dumps({"widgetStates": {"searchResultsV2-1": json.dumps({"items": [{"sku": "1"}]})}})}
        got = list(tile_parse.iter_tile_items(page))
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0][1]["items"][0]["sku"], "1")

    def test_reports_malformed_widget_instead_of_silence(self):
        errors = []
        page = {"widgetStates": {"searchResultsV2-1": "{not json", "header-1": "{}"}}
        self.assertEqual(list(tile_parse.iter_tile_items(page, errors)), [])
        self.assertEqual(len(errors), 1)
        self.assertIn("JSONDecodeError", errors[0]["error"])

    def test_non_list_payload_is_reported(self):
        errors = []
        page = {"widgetStates": {"tile-1": json.dumps(["not", "a", "dict"])}}
        list(tile_parse.iter_tile_items(page, errors))
        self.assertEqual(len(errors), 1)

    def test_no_widget_states(self):
        self.assertEqual(list(tile_parse.iter_tile_items({})), [])
        self.assertEqual(list(tile_parse.iter_tile_items(None)), [])


if __name__ == "__main__":
    unittest.main()
