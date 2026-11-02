#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探活 + 算 __Secure-token 年龄，给 auto_renew_seller_cookie.sh 用

输出一行: <STATUS> <CODE> <AGE_HOURS>
  OK 200 6.0 / FAIL 401 6.0 / NET 0 6.0 / ERR 0 None

重要：走 SellerClient，它会**吸收服务端下发的 Set-Cookie**（abt_data 周期性轮换）。
     探活本身就是在保活 —— 不接上游下发的反爬令牌，过一阵就会被前层 nginx 判异常（307 循环）。
"""
from __future__ import annotations

import sys
import urllib.error
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PROBE = "/api/search-query-analytics/v1/accessibility/enabled_features"


def token_age_hours(cookie: str):
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
        from ozon_seller import SellerClient
        c = SellerClient()
    except Exception:  # noqa: BLE001
        print("ERR 0 None")
        return 0

    age = token_age_hours(c.jar.cookie)
    path = f"{PROBE}?sellerId={c.jar.company_id}&userId=0"
    try:
        c.post(path, None, app_name="seller-ui", page_type="analytics-search",
               referer="/app/analytics-search/search-results/explainer")
        print(f"OK 200 {age}")
    except urllib.error.HTTPError as exc:
        print(f"FAIL {exc.code} {age}")
    except Exception:  # noqa: BLE001
        print(f"NET 0 {age}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
