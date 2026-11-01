#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卖家端 cookie 探活（2026-11-01 逆向修正版）

修正点：
  · 旧的把 stamps[1] 当 issueTs 且用本地时间(UTC+8)相减 → 恒定输出 ~6h，误判成"8h 轮换"。
    实测 token 时间戳是 UTC+2，stamps[0]=会话建立，stamps[1]=最后写入。
  · 实测该接口 200 时不轮换 __Secure-token；所以本探针只回答"还能不能用"。

输出一行: <STATUS> <CODE> <HOURS_SINCE_LAST_SET|None>
  OK   200 0.1   可用
  FAIL 401 0.1   鉴权失效（必须重签，没有客户端 refresh 端点）
  AUTH 403 0.1   abt_data 掉了（同样重签）
  NET  0   ...   网络问题，别动 cookie
  THR  429 ...   被限流，别动 cookie
  ERR  0   None  jar 读不到
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DIR = Path.home() / ".config" / "ozon-seller"
STAMP_TZ = timezone(timedelta(hours=2))  # 实测：stamp = cookie_set_utc + 2h
PROBE = "/api/search-query-analytics/v1/accessibility/enabled_features"


def last_set_hours(token: str) -> float | None:
    stamps = [s for s in token.split(".") if len(s) == 14 and s.isdigit()]
    if len(stamps) < 2:
        return None
    try:
        last = datetime.strptime(stamps[1], "%Y%m%d%H%M%S").replace(tzinfo=STAMP_TZ)
    except ValueError:
        return None
    return round((datetime.now(timezone.utc) - last).total_seconds() / 3600, 1)


def main() -> int:
    try:
        from ozon_seller import Jar
        from ozon_seller.api import BASE
        jar = Jar.load()
        cookie, ua, cid = jar.cookie, jar.ua, jar.company_id
    except Exception:  # noqa: BLE001
        # 退路：直接读文件，不依赖包
        try:
            cookie = (DIR / "cookie.txt").read_text().strip()
            ua = (DIR / "cookie.ua").read_text().strip()
            cid = str(json.loads((DIR / "meta.json").read_text()).get("company_id") or "5149811")
            BASE = "https://seller.ozon.ru"
        except Exception:
            print("ERR 0 None")
            return 0

    tok = ""
    for p in cookie.split("; "):
        if p.startswith("__Secure-token="):
            tok = p.split("=", 1)[1]
            break
    hours = last_set_hours(tok)

    url = f"{BASE}{PROBE}?sellerId={cid}&userId=0"
    req = urllib.request.Request(url, headers={
        "user-agent": ua,
        "accept": "application/json, text/plain, */*",
        "origin": BASE,
        "referer": f"{BASE}/app/analytics-search/search-results/explainer",
        "x-o3-app-name": "seller-ui",
        "x-o3-page-type": "analytics-search",
        "x-o3-language": "zh-Hans",
        "x-o3-company-id": str(cid),
        "cookie": cookie,
    })
    try:
        r = urllib.request.urlopen(req, timeout=25)
        code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception:  # noqa: BLE001
        print(f"NET 0 {hours}")
        return 0

    if code == 200:
        print(f"OK 200 {hours}")
    elif code == 429:
        print(f"THR 429 {hours}")
    elif code in (401, 403):
        # 403 是 abt_data 掉，401 是会话死；两者都只能重签
        print(f"{'FAIL' if code == 401 else 'AUTH'} {code} {hours}")
    else:
        print(f"NET {code} {hours}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
