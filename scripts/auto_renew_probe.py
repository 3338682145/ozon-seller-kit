#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探活 + 算 __Secure-token 年龄，给 auto_renew_seller_cookie.sh 用

输出一行: <STATUS> <CODE> <AGE_HOURS>
  OK 200 6.0    可用，token 签发于 6.0 小时前
  FAIL 401 6.0  鉴权失效
  NET 0 6.0     网络问题
  ERR 0 None    jar 读不到
"""
from __future__ import annotations

import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PROBE = "/api/search-query-analytics/v1/accessibility/enabled_features"


def token_age_hours(cookie: str) -> float | None:
    """__Secure-token 点分 10 段，第 6 段（index 5）是 14 位签发时刻"""
    for part in cookie.split("; "):
        if part.startswith("__Secure-token="):
            segs = part.split("=", 1)[1].split(".")
            stamps = [x for x in segs if x.isdigit() and len(x) == 14]
            if len(stamps) >= 2:
                try:
                    issued = datetime.strptime(stamps[1], "%Y%m%d%H%M%S")
                    return round((datetime.now() - issued).total_seconds() / 3600, 1)
                except ValueError:
                    return None
    return None


def main() -> int:
    try:
        from ozon_seller import Jar
        from ozon_seller.api import BASE
        jar = Jar.load()
    except Exception:  # noqa: BLE001
        print("ERR 0 None")
        return 0

    age = token_age_hours(jar.cookie)
    url = f"{BASE}{PROBE}?sellerId={jar.company_id}&userId=0"
    req = urllib.request.Request(url, headers={
        "user-agent": jar.ua,
        "accept": "application/json, text/plain, */*",
        "origin": BASE,
        "referer": f"{BASE}/app/analytics-search/search-results/explainer",
        "x-o3-app-name": "seller-ui",
        "x-o3-page-type": "analytics-search",
        "x-o3-language": "zh-Hans",
        "x-o3-company-id": str(jar.company_id),
        "cookie": jar.cookie,
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            r.read()
        print(f"OK 200 {age}")
    except urllib.error.HTTPError as exc:
        print(f"FAIL {exc.code} {age}")
    except Exception:  # noqa: BLE001
        print(f"NET 0 {age}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
