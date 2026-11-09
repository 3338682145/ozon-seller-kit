#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按既定字段契约采集库存并落库。

字段契约
--------
形态 1 · 列表磁贴（搜索页 / 卖家页，零加购）
  url:        /search/?text=<kw>&page=N  |  /seller/<slug>/?page=N
  path:       widgetStates["tileGridDesktop-*"].items[i]
                .multiButton.ozonButton.addToCart.quantityButton.maxItems
  skuGrid:    widgetStates["skuGrid-*"].items[i]
                .multiButton.button.addToCartButtonWithQuantity.maxItems
  → kw_sku.stock_max

形态 2 · 商品详情 PDP
  url:        /product/<sku>/
  path:       widgetStates["webAddToCart-*"].firstButton.freeRest
  → sku_pdp_snapshot.pdp_stock_free
  → 回写 sku_dim.pdp_stock_free

用法
----
  python3 scripts/collect_stock_fields.py --keyword "сквиш" --pages 2 --out data/stock_fields.json
  python3 scripts/collect_stock_fields.py --sku 5044498550 --sku 5527434733 --out data/stock_fields.json
  python3 scripts/collect_stock_fields.py --keyword "сквиш" --db data/toys-slim.db

说明
----
* 默认只采集 + 输出 JSON，不建表、不改表结构。
* 给 --db 时仅做「写已有表」：表或列不存在就跳过并提示，绝不自动 CREATE/ALTER。
"""
import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ozon_buyer.collector import (
    cdp_warmup,
    extract_pdp_stock_free,
    extract_skus_from_page,
    load_valid_cookie,
    request_entrypoint_page,
)
from ozon_buyer.env import detect_proxy


def collect_tiles(path, creds, proxy):
    """请求列表页，返回 [{sku, keyword, stock_max, position}]"""
    page = request_entrypoint_page(path, creds, proxy)
    items = extract_skus_from_page(page)
    rows = []
    for idx, it in enumerate(items):
        sku = it.get("sku_id")
        if not sku:
            continue
        rows.append({
            "sku": str(sku),
            "stock_max": it.get("stock_max"),
            "position": idx + 1,
            "title": it.get("title"),
        })
    return rows


def collect_pdp(sku, creds, proxy):
    """请求 PDP，返回 pdp_stock_free"""
    page = request_entrypoint_page(f"/product/{sku}/", creds, proxy)
    return extract_pdp_stock_free(page)


def table_columns(con, table):
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    if not cur.fetchone():
        return None
    cur.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]


def write_db(db_path, kw_sku_rows, pdp_rows):
    """只写已存在的表和列，不做任何建表/改表。"""
    con = sqlite3.connect(db_path)
    report = {"kw_sku": 0, "sku_pdp_snapshot": 0, "sku_dim": 0, "skipped": []}

    cols = table_columns(con, "kw_sku")
    if cols and "stock_max" in cols and "sku" in cols:
        key_col = "keyword" if "keyword" in cols else None
        cur = con.cursor()
        for r in kw_sku_rows:
            if r["stock_max"] is None:
                continue
            if key_col:
                cur.execute(
                    f"UPDATE kw_sku SET stock_max=? WHERE sku=? AND {key_col}=?",
                    (r["stock_max"], r["sku"], r["keyword"]),
                )
            else:
                cur.execute("UPDATE kw_sku SET stock_max=? WHERE sku=?", (r["stock_max"], r["sku"]))
            report["kw_sku"] += cur.rowcount
    else:
        report["skipped"].append("kw_sku 表或列缺失（需 sku / stock_max）")

    cols = table_columns(con, "sku_pdp_snapshot")
    if cols and "pdp_stock_free" in cols and "sku" in cols:
        cur = con.cursor()
        for r in pdp_rows:
            fields = ["sku", "pdp_stock_free"]
            values = [r["sku"], r["pdp_stock_free"]]
            if "captured_at" in cols:
                fields.append("captured_at")
                values.append(r["captured_at"])
            sql = f"INSERT INTO sku_pdp_snapshot ({','.join(fields)}) VALUES ({','.join('?' * len(fields))})"
            cur.execute(sql, values)
            report["sku_pdp_snapshot"] += 1
    else:
        report["skipped"].append("sku_pdp_snapshot 表或列缺失（需 sku / pdp_stock_free）")

    cols = table_columns(con, "sku_dim")
    if cols and "pdp_stock_free" in cols and "sku" in cols:
        cur = con.cursor()
        for r in pdp_rows:
            cur.execute("UPDATE sku_dim SET pdp_stock_free=? WHERE sku=?", (r["pdp_stock_free"], r["sku"]))
            report["sku_dim"] += cur.rowcount
    else:
        report["skipped"].append("sku_dim 表或列缺失（需 sku / pdp_stock_free）")

    con.commit()
    con.close()
    return report


def main():
    ap = argparse.ArgumentParser(description="按字段契约采集库存（tile maxItems / PDP freeRest）")
    ap.add_argument("--keyword", action="append", help="搜索词，可多次传入")
    ap.add_argument("--seller", action="append", help="卖家页路径或 ID，如 2709553")
    ap.add_argument("--sku", action="append", help="指定 SKU（仅采 PDP freeRest）")
    ap.add_argument("--pages", type=int, default=1, help="列表页页数")
    ap.add_argument("--sorting", default="", help="排序：popular/price/discount 每页 36 个；默认排序每页 8 个")
    ap.add_argument("--page-threads", type=int, default=8, help="列表页并发线程（15 页约 7s，15 线程约 3s）")
    ap.add_argument("--threads", type=int, default=3, help="PDP 并发")
    ap.add_argument("--with-pdp", action="store_true", help="未指定 --sku 时，对列表 SKU 一并采 PDP freeRest")
    ap.add_argument("--out", default="data/stock_fields.json", help="JSON 输出路径")
    ap.add_argument("--db", help="SQLite 路径；仅写已有表，不建表")
    ap.add_argument("--delay", type=float, default=0.6, help="请求间隔秒")
    args = ap.parse_args()

    proxy = None if os.environ.get("OZON_USE_PROXY") != "1" else detect_proxy()
    print(f"[*] 网络: {'代理 ' + str(proxy) if proxy else '直连（默认，代理出口会被 Ozon 风控）'}")
    creds = load_valid_cookie()
    if not creds:
        print("[*] 无可用 Cookie，CDP 预热...")
        creds = cdp_warmup(target_url="https://www.ozon.ru/", proxy=proxy, is_adult=True, no_proxy=(proxy is None))
    if not creds:
        print("[!] 预热失败，退出")
        return 2

    kw_rows = []
    kw_tasks = [(kw, p) for kw in (args.keyword or []) for p in range(1, args.pages + 1)]

    def run_kw(task):
        kw, p = task
        path = f"/search/?text={urllib.parse.quote(kw)}" + (f"&page={p}" if p > 1 else "")
        if args.sorting:
            path += f"&sorting={args.sorting}"
        try:
            rows = collect_tiles(path, creds, proxy)
            for r in rows:
                r["keyword"] = kw
                r["page"] = p
            return (kw, p, rows, None)
        except Exception as e:
            return (kw, p, [], f"{type(e).__name__}: {e}")

    if kw_tasks:
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=args.page_threads) as ex:
            for kw, p, rows, err in ex.map(run_kw, kw_tasks):
                if err:
                    print(f"  [!] {kw} p{p} 失败: {err}")
                    continue
                kw_rows.extend(rows)
                hits = sum(1 for r in rows if r["stock_max"] is not None)
                print(f"  [tile] {kw} p{p}: {len(rows)} SKU，stock_max {hits}/{len(rows)}")
        print(f"  [tile] 关键词并发完成：{len(kw_tasks)} 页 / {round(time.time()-t0,2)}s / 唯一 {len({r['sku'] for r in kw_rows})}")

    seller_tasks = []
    for sel in args.seller or []:
        base = sel if sel.startswith("/seller/") else f"/seller/{sel}/"
        for p in range(1, args.pages + 1):
            seller_tasks.append((sel, base.rstrip("/") + f"/?page={p}", p))

    def run_seller(task):
        sel, path, p = task
        try:
            rows = collect_tiles(path, creds, proxy)
            for r in rows:
                r["keyword"] = None
                r["seller"] = sel
                r["page"] = p
            return (sel, p, rows, None)
        except Exception as e:
            return (sel, p, [], f"{type(e).__name__}: {e}")

    if seller_tasks:
        with ThreadPoolExecutor(max_workers=args.page_threads) as ex:
            for sel, p, rows, err in ex.map(run_seller, seller_tasks):
                if err:
                    print(f"  [!] seller {sel} p{p} 失败: {err}")
                    continue
                kw_rows.extend(rows)
                print(f"  [tile] seller {sel} p{p}: {len(rows)} SKU")

    skus = list(args.sku or [])
    if not skus and kw_rows and args.with_pdp:
        skus = sorted({r["sku"] for r in kw_rows})
        print(f"[*] --with-pdp：按列表页 SKU 采集 PDP（{len(skus)} 个）")

    pdp_rows = []

    def run_pdp(sku):
        try:
            return (sku, collect_pdp(sku, creds, proxy), None)
        except Exception as e:
            return (sku, None, f"{type(e).__name__}: {e}")

    if skus:
        with ThreadPoolExecutor(max_workers=args.threads) as ex:
            for sku, free, err in ex.map(run_pdp, skus):
                if err:
                    print(f"  [!] PDP {sku} 失败: {err}")
                    continue
                pdp_rows.append({
                    "sku": str(sku),
                    "pdp_stock_free": free,
                    "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "source_url": f"/product/{sku}/",
                })
                print(f"  [pdp] {sku}: pdp_stock_free={free}")

    payload = {
        "collected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "kw_sku": kw_rows,
        "sku_pdp_snapshot": pdp_rows,
        "sku_dim": [{"sku": r["sku"], "pdp_stock_free": r["pdp_stock_free"]} for r in pdp_rows],
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    tile_hits = sum(1 for r in kw_rows if r["stock_max"] is not None)
    pdp_hits = sum(1 for r in pdp_rows if r["pdp_stock_free"] is not None)
    print(f"\n[+] 输出: {args.out}")
    print(f"    tile stock_max: {tile_hits}/{len(kw_rows)} | PDP freeRest: {pdp_hits}/{len(pdp_rows)}")

    if args.db:
        rep = write_db(args.db, kw_rows, pdp_rows)
        print(f"[+] 落库 {args.db}: kw_sku {rep['kw_sku']} 行 / sku_pdp_snapshot {rep['sku_pdp_snapshot']} 行 / sku_dim {rep['sku_dim']} 行")
        for s in rep["skipped"]:
            print(f"    [skip] {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
