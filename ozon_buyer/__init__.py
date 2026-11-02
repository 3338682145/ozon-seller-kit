"""
Ozon 买家端前台 (www.ozon.ru) 本地采集器模块。
支持免登录高并发采集：商品搜索、类目商品、SKU 详情、变体矩阵、全量属性、
真实物理库存上限 (stock_max)、评价与 1 星差评排雷、同款跟卖商工商资质等。
"""
from .api import BuyerClient
from .collector import (
    cdp_warmup,
    extract_skus_from_page,
    fetch_sku_reviews,
    fetch_sku_seller_info,
    load_valid_cookie,
    request_entrypoint_page,
)
from .detail import parse_pdp1, parse_pdp2, parse_reviews
from .env import detect_proxy, get_chrome_executable, parse_count_num, parse_num
from .http import parse_tile

__all__ = [
    "BuyerClient",
    "cdp_warmup",
    "detect_proxy",
    "extract_skus_from_page",
    "fetch_sku_reviews",
    "fetch_sku_seller_info",
    "get_chrome_executable",
    "load_valid_cookie",
    "parse_count_num",
    "parse_num",
    "parse_pdp1",
    "parse_pdp2",
    "parse_reviews",
    "parse_tile",
    "request_entrypoint_page",
]
