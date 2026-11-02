"""
Ozon 买家端前台 (www.ozon.ru) 本地 Python 采集客户端。
支持免登录高并发采集：商品搜索、类目商品、SKU 详情、变体矩阵、全量属性、
真实物理库存上限 (stock_max)、评价与 1 星差评排雷、同款跟卖商工商资质等。
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
from typing import Any, Dict, List, Optional

try:
    from curl_cffi import requests as cr
except ImportError:
    cr = None

try:
    from .env import detect_proxy, get_chrome_executable, parse_count_num, parse_num
    from .collector import (
        cdp_warmup,
        extract_skus_from_page,
        fetch_sku_reviews,
        fetch_sku_seller_info,
        load_valid_cookie,
        request_entrypoint_page,
    )
    from .detail import parse_pdp1, parse_pdp2, parse_reviews
except (ImportError, ValueError):
    from env import detect_proxy, get_chrome_executable, parse_count_num, parse_num
    from collector import (
        cdp_warmup,
        extract_skus_from_page,
        fetch_sku_reviews,
        fetch_sku_seller_info,
        load_valid_cookie,
        request_entrypoint_page,
    )
    from detail import parse_pdp1, parse_pdp2, parse_reviews


class BuyerClient:
    """
    Ozon 买家端前台 API 客户端（纯 Python HTTP，伪装 Chrome 124 TLS 指纹）。
    无需卖家账号，Cookie 自动静默预热或读本地缓存。
    """

    def __init__(self, proxy: Optional[str] = None):
        if cr is None:
            raise RuntimeError("请先安装 curl_cffi: pip install curl_cffi")
        self.proxy = proxy or detect_proxy()
        self.creds = load_valid_cookie()

    def ensure_creds(self, target_url: str = "https://www.ozon.ru/") -> Dict[str, Any]:
        """确保拥有可用买家端 Cookie，若无或失效则启动静默预热"""
        if not self.creds:
            self.creds = cdp_warmup(target_url=target_url, proxy=self.proxy, is_adult=True)
            if not self.creds:
                raise RuntimeError("买家端 Cookie 预热失败！")
        return self.creds

    def search(self, keyword: str, pages: int = 1) -> List[Dict[str, Any]]:
        """
        按关键词搜索商品，返回包含 stock_max 真实物理可用库存的结构化商品列表
        """
        self.ensure_creds()
        all_items = []
        for p in range(1, pages + 1):
            url = f"/search/?page={p}&text={urllib.parse.quote(keyword)}"
            p_json = request_entrypoint_page(url, self.creds, proxy=self.proxy)
            items = extract_skus_from_page(p_json)
            all_items.extend(items)
            if not items:
                break
        return all_items

    def category(self, category_path: str, pages: int = 1) -> List[Dict[str, Any]]:
        """
        按类目 URL 抓取在售商品列表（含 stock_max 批量库存）
        """
        self.ensure_creds()
        all_items = []
        clean_path = category_path.split("?")[0].rstrip("/")
        for p in range(1, pages + 1):
            url = f"{clean_path}/?page={p}"
            p_json = request_entrypoint_page(url, self.creds, proxy=self.proxy)
            items = extract_skus_from_page(p_json)
            all_items.extend(items)
            if not items:
                break
        return all_items

    def sku_detail(self, sku_id: str | int, include_pdp2: bool = True) -> Dict[str, Any]:
        """
        抓取单个 SKU 完整商品画像：
        - 标题、价格（Ozon卡价/黑标价/原价）
        - 变体全家桶矩阵 (webAspects)
        - 图集与主图视频
        - 属性与短特征 (webCharacteristics)
        - 描述富文本 HTML (webDescription)
        - 卖家信息与大促库存
        """
        self.ensure_creds()
        sku_str = str(sku_id).strip()
        headers = {
            "User-Agent": self.creds.get("ua", "Mozilla/5.0"),
            "Cookie": self.creds.get("cookie", ""),
            "Accept": "application/json",
            "Referer": "https://www.ozon.ru/",
        }
        proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None

        # 第一屏
        api_url = f"https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2?url={urllib.parse.quote(f'/product/{sku_str}/')}"
        resp = cr.get(api_url, headers=headers, impersonate="chrome124", proxies=proxies, timeout=15)
        if resp.status_code != 200:
            return {"sku": sku_str, "error": f"HTTP {resp.status_code}"}

        data = resp.json()
        ws = data.get("widgetStates", {})
        result = {"sku": sku_str, "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        result.update(parse_pdp1(ws))

        # 第二屏（属性与详情描述）
        if include_pdp2:
            pdp2_path = f"/product/{sku_str}/?layout_container=pdpPage2column&layout_page_index=2"
            api2_url = f"https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2?url={urllib.parse.quote(pdp2_path)}"
            try:
                resp2 = cr.get(api2_url, headers=headers, impersonate="chrome124", proxies=proxies, timeout=15)
                if resp2.status_code == 200:
                    ws2 = resp2.json().get("widgetStates", {})
                    result.update(parse_pdp2(ws2))
            except Exception:
                pass

        return result

    def sku_reviews(self, sku_id: str | int, pages: int = 1, sort: str = "score_asc") -> Dict[str, Any]:
        """
        抓取买家评价，默认支持 `sort=score_asc` 差评排雷（1星优先）：
        - score (1~5星), comment, positive, negative, author, photos, usefulness
        """
        self.ensure_creds()
        return fetch_sku_reviews(str(sku_id), self.creds, proxy=self.proxy, pages=pages, sort=sort)

    def other_offers(self, sku_id: str | int) -> List[Dict[str, Any]]:
        """
        抓取跟卖该商品的所有其他卖家（含企业主体全称、ОГРН 注册号、城市、国家、跟卖价格、时效）
        """
        self.ensure_creds()
        sku_str = str(sku_id).strip()
        headers = {
            "User-Agent": self.creds.get("ua", "Mozilla/5.0"),
            "Cookie": self.creds.get("cookie", ""),
            "Accept": "application/json",
            "Referer": "https://www.ozon.ru/",
        }
        proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
        rel_path = f"/modal/otherOffersFromSellers?product_id={sku_str}&sort=price"
        api_url = f"https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2?url={urllib.parse.quote(rel_path)}"

        try:
            resp = cr.get(api_url, headers=headers, impersonate="chrome124", proxies=proxies, timeout=15)
            if resp.status_code != 200:
                return []
            ws = resp.json().get("widgetStates", {})
            for k, v in ws.items():
                if "webSellerList" in k:
                    data = json.loads(v) if isinstance(v, str) else v
                    sellers_raw = data.get("sellers") or []
                    extracted = []
                    for s in sellers_raw:
                        cred = s.get("credentials") or {}
                        extracted.append({
                            "seller_id": s.get("id"),
                            "seller_name": s.get("name"),
                            "company_name": cred.get("name"),
                            "reg_number": cred.get("number"),  # ОГРН / ОГРНИП / 统一信用代码
                            "city": cred.get("city"),
                            "country": cred.get("country"),
                            "price": parse_num(((s.get("price") or {}).get("cardPrice") or {}).get("price")),
                            "delivery_period": ((s.get("delivery") or {}).get("period") or {}).get("text"),
                        })
                    return extracted
        except Exception:
            return []
        return []
