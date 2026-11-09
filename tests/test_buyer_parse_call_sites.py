"""调用点回归测试：http.parse_items / http.parse_tile / collector.extract_skus_from_page。

这些模块在导入时会加载 curl_cffi（TLS 指纹库）。缺少依赖时整组跳过，
保证纯解析测试仍可在任何环境跑。
"""
import json
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import curl_cffi  # noqa: F401
except ImportError:  # pragma: no cover
    curl_cffi = None


def _tile(advert_marker="missing", max_items=None):
    tile = {
        "sku": "7654321",
        "action": {"link": "/product/7654321/"},
        "cellTrackingInfo": {"title": "Товар", "price": "999 ₽", "reviewCount": "56"},
    }
    if advert_marker == "true":
        tile["trackingInfo"] = {"click": {"custom": {"advertLite": True}}}
    elif advert_marker == "false":
        tile["trackingInfo"] = {"click": {"custom": {"advertLite": False}}}
    if max_items is not None:
        tile["multiButton"] = {"ozonButton": {"addToCart": {"quantityButton": {"maxItems": max_items}}}}
    return tile


def _page(widget_key, items):
    return {"widgetStates": {widget_key: json.dumps({"items": items})}}


@unittest.skipUnless(curl_cffi, "curl_cffi not installed")
class ParseItemsTest(unittest.TestCase):
    def test_search_results_v2_widget_is_recognised(self):
        """回归：旧实现只认 tileGridDesktop，搜索页的 searchResultsV2 会被判空。"""
        from ozon_buyer import http

        rows = http.parse_items(json.dumps(_page("searchResultsV2-1", [_tile()])))
        self.assertEqual(len(rows), 1)

    def test_tile_grid_desktop_still_works(self):
        from ozon_buyer import http

        self.assertEqual(len(http.parse_items(json.dumps(_page("tileGridDesktop-1", [_tile()])))), 1)

    def test_malformed_widget_does_not_blank_the_page(self):
        from ozon_buyer import http

        payload = {"widgetStates": {"searchResultsV2-1": "{oops", "tile-1": json.dumps({"items": [_tile()]})}}
        self.assertEqual(len(http.parse_items(json.dumps(payload))), 1)

    def test_no_items_returns_empty(self):
        from ozon_buyer import http

        self.assertEqual(http.parse_items(json.dumps({"widgetStates": {"header-1": "{}"}})), [])


@unittest.skipUnless(curl_cffi, "curl_cffi not installed")
class ParseTileTest(unittest.TestCase):
    def test_advert_tristate(self):
        from ozon_buyer import http

        self.assertIsNone(http.parse_tile(_tile(), 1)["is_advert"])
        self.assertIs(http.parse_tile(_tile("true"), 1)["is_advert"], True)
        self.assertIs(http.parse_tile(_tile("false"), 1)["is_advert"], False)

    def test_stock_max_is_int(self):
        from ozon_buyer import http

        self.assertEqual(http.parse_tile(_tile(max_items="1 000"), 1)["stock_max"], 1000)


@unittest.skipUnless(curl_cffi, "curl_cffi not installed")
class ExtractSkusTest(unittest.TestCase):
    def test_tristate_advert_and_int_stock(self):
        from ozon_buyer import collector

        rows = collector.extract_skus_from_page(_page("searchResultsV2-1", [_tile(max_items="24")]))
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["is_advert"])
        self.assertEqual(rows[0]["stock_max"], 24)
        self.assertEqual(rows[0]["title"], "Товар")

    def test_errors_list_receives_widget_failure(self):
        from ozon_buyer import collector

        payload = {"widgetStates": {"searchResultsV2-1": "{broken"}}
        errors = []
        self.assertEqual(collector.extract_skus_from_page(payload, errors=errors), [])
        self.assertEqual(len(errors), 1)

    def test_backward_compatible_without_errors_list(self):
        from ozon_buyer import collector

        payload = {"widgetStates": {"searchResultsV2-1": "{broken"}}
        self.assertEqual(collector.extract_skus_from_page(payload), [])


if __name__ == "__main__":
    unittest.main()
