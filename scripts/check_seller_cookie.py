#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核验卖家端 cookie jar 是否仍可用于 seller.ozon.ru 分析接口。

用法:
    python3 scripts/check_seller_cookie.py
    python3 scripts/check_seller_cookie.py --json

退出码:
    0  可用
    2  cookie / uuid 失效（需重新 mint）
    3  被限流（cookie 没坏，过 10-20 分钟再看）
    4  网络问题
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ozon_seller import AuthExpired, SellerClient  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        client = SellerClient()
    except AuthExpired as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2

    r = client.probe()
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))

    if r.get("ok"):
        if not args.json:
            print(f"✓ 可用 | 店铺 {r['company_id']} | 对照词 {r['control_items']} 条 | "
                  f"{r['latency_ms']}ms | 签发于 {r['minted_at']}")
        return 0

    err = r.get("error")
    if err == "throttled":
        print(f"⚠ 限流（cookie 未失效）: {r.get('detail')}", file=sys.stderr)
        return 3
    if err == "auth":
        print(f"✗ 鉴权失效: {r.get('detail')}\n  → bash scripts/refresh_seller_cookie.sh", file=sys.stderr)
        return 2
    print(f"✗ 网络/其他: {r.get('detail')}", file=sys.stderr)
    return 4


if __name__ == "__main__":
    sys.exit(main())
