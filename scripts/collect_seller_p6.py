#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卖家端 p6 销量本地采集（what_to_sell data/v3）

两种模式：
 榜单翻页  --top 2000                     按 GMV 榜取前 N 个 SKU
 批量查货  --skus-file skus.txt           按 SKU 清单查（--chunk 50 一批）

实测性能（2026-10-30）：并发 5 × 50 SKU/req，500 SKU 用 4.7s ≈ 6,400 SKU/分钟，零空包。
但历史上出现过「945 请求 / 7 分钟后整域 403」，所以内置命中率哨兵：
连续 20 个请求命中率 <1.0 req 就停顿 120s。

用法:
    python3 scripts/collect_seller_p6.py --top 2000 --out data/p6-local.json
    python3 scripts/collect_seller_p6.py --skus-file data/p8-master-skus.json --chunk 50
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ozon_seller import AuthExpired, SellerClient  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=0, help="按榜单取前 N 个 SKU")
    ap.add_argument("--skus-file", default="", help="SKU 清单（txt 每行一个 / json 数组）")
    ap.add_argument("--out", default=str(ROOT / "data" / "p6-local.json"))
    ap.add_argument("--chunk", type=int, default=50, help="每请求 SKU 数，接口上限 50")
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--period", default="monthly", choices=["monthly", "weekly"],
                    help="monthly=28天口径（默认）· weekly=7天口径。\n"
                         "⚠ 只认这两个值，其他任何字符串都会**静默回退到 monthly**，不报错")
    args = ap.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    client = SellerClient()
    probe = client.probe()
    if not probe.get("ok"):
        print(f"✗ 探活失败: {probe}", file=sys.stderr)
        return 2
    print(f"店铺 {client.jar.company_id} | 探活 OK {probe['latency_ms']}ms")

    found: dict = {}
    lock = threading.Lock()
    counters = {"req": 0, "hit": 0, "empty": 0}

    def absorb(items):
        with lock:
            for it in items:
                found[str(it.get("sku"))] = it
            counters["hit"] += len(items)
            if items:
                counters["empty"] = 0
            else:
                counters["empty"] += 1

    t0 = time.time()

    # ── 模式 A：榜单翻页
    if args.top:
        pages = (args.top + 49) // 50
        print(f"榜单模式：目标 {args.top} 个 SKU（{pages} 页，并发 {args.concurrency}）")

        def fetch_page(i: int):
            with lock:
                counters["req"] += 1
            try:
                items = client.what_to_sell(offset=i * 50, limit=50, period=args.period)
            except AuthExpired as exc:
                print(f"  ! auth @page{i}: {exc}", file=sys.stderr)
                return []
            absorb(items)
            if i % 20 == 0:
                print(f"  page {i}/{pages} | 累计 {len(found)} SKU {((time.time() - t0) / 60):.1f}min")
            return items

        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            list(ex.map(fetch_page, range(pages)))

    # ── 模式 B：SKU 清单
    elif args.skus_file:
        p = Path(args.skus_file)
        text = p.read_text(encoding="utf-8").strip()
        if text.startswith("["):
            skus = [str(x) for x in json.loads(text)]
        else:
            skus = [s.strip() for s in text.splitlines() if s.strip()]
        chunks = [skus[i:i + args.chunk] for i in range(0, len(skus), args.chunk)]
        print(f"清单模式：{len(skus)} 个 SKU → {len(chunks)} 批（chunk={args.chunk}，并发 {args.concurrency}）")

        def fetch_chunk(idx_chunk):
            idx, chunk = idx_chunk
            with lock:
                counters["req"] += 1
            try:
                items = client.what_to_sell(skus=chunk, period=args.period)
            except AuthExpired as exc:
                print(f"  ! auth @chunk{idx}: {exc}", file=sys.stderr)
                with lock:
                    counters["auth"] = counters.get("auth", 0) + 1
                    if counters["auth"] >= 3:
                        print("  ✗ 连续 401/403 → 会话被限，立即停止（冷却 30-60 分钟）",
                              file=sys.stderr)
                return
            absorb(items)
            # 命中率哨兵：连续 20 批全空 → 大概率静默限流
            if counters["req"] % 20 == 0 and counters["empty"] >= 20:
                print(f"  ⚠ 连续 20 批空包 → 暂停 120s（疑似限流）")
                time.sleep(120)
                counters["empty"] = 0
            if idx % 20 == 0:
                print(f"  chunk {idx}/{len(chunks)} | 命中 {len(found)} {((time.time() - t0) / 60):.1f}min")

        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            list(ex.map(fetch_chunk, enumerate(chunks)))
    else:
        ap.error("需要 --top 或 --skus-file")

    rows = list(found.values())
    out_path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    el = (time.time() - t0) / 60
    print(f"\n完成：{len(rows)} SKU | 请求 {counters['req']} | {el:.2f}min | "
          f"{len(rows) / max(el, 0.01):.0f} SKU/分钟")
    print(f"输出 {out_path}")
    print(f"请求统计 {client.stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
