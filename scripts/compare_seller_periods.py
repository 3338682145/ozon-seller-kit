#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同一批 SKU 拉 7 天口径 + 28 天口径，对比出「短期拐点」

背景（2026-10-30 实测）：p6 `what_to_sell/data/v3` 的 `filter.period` **只有两个有效值**：
    weekly   → 7 天口径
    monthly  → 28 天口径（默认）
其他任何字符串（"7d" / "28d" / "WEEKLY" / "daily" …）**静默回退到 monthly，不报错**。
所以必须严格传这两个值之一，否则你以为采的是 7 天，其实是 28 天。

同一 SKU 两个口径会给出完全不同的结论。实测 3107016631：
    monthly: sold=218  gmv=845,494  salesDynamics=-15.4%   ← 28 天在跌
    weekly : sold=74   gmv=258,241  salesDynamics=+52.8%   ← 最近 7 天在反弹
→ 这叫「月度还在跌但短期已反弹」，是补货/加推的先行信号。单一口径看不到。

用法:
    python3 scripts/compare_seller_periods.py --skus-file /tmp/skus.txt --out data/period-cmp.json
    python3 scripts/compare_seller_periods.py --skus 3107016631,5081332378

⚠ 限流：p8 与 p6 共用会话配额。本脚本会打 2 倍请求，跑前确认会话是干净的，
   并且不要和其它采集任务同时跑。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ozon_seller import AuthExpired, SellerClient  # noqa: E402


def pull(client: SellerClient, skus: list[str], period: str, chunk: int) -> dict:
    out = {}
    for i in range(0, len(skus), chunk):
        part = skus[i:i + chunk]
        try:
            items = client.what_to_sell(skus=part, period=period)
        except AuthExpired:
            raise
        for it in items:
            out[str(it.get("sku"))] = it
        print(f"  [{period}] {min(i + chunk, len(skus))}/{len(skus)} 命中 {len(out)}", file=sys.stderr)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skus", default="")
    ap.add_argument("--skus-file", default="")
    ap.add_argument("--chunk", type=int, default=50)
    ap.add_argument("--out", default=str(ROOT / "data" / "period-cmp.json"))
    a = ap.parse_args()

    if a.skus:
        skus = [s.strip() for s in a.skus.split(",") if s.strip()]
    elif a.skus_file:
        p = Path(a.skus_file)
        txt = p.read_text(encoding="utf-8").strip()
        skus = json.loads(txt) if txt.startswith("[") else [x.strip() for x in txt.splitlines() if x.strip()]
        skus = [str(s) for s in skus]
    else:
        ap.error("需要 --skus 或 --skus-file")

    client = SellerClient()
    probe = client.probe()
    if not probe.get("ok"):
        print(f"✗ 探活失败，先别跑: {probe}", file=sys.stderr)
        return 2
    print(f"店铺 {client.jar.company_id} | {len(skus)} 个 SKU | 两轮请求", file=sys.stderr)

    m = pull(client, skus, "monthly", a.chunk)
    w = pull(client, skus, "weekly", a.chunk)

    rows = []
    for s in skus:
        M, W = m.get(s), w.get(s)
        if not M and not W:
            continue
        def f(d, k):
            try:
                return float(d.get(k)) if d and d.get(k) not in (None, "") else None
            except (TypeError, ValueError):
                return None
        ms, ws = f(M, "soldCount"), f(W, "soldCount")
        # 7 天折算成 28 天，和月度比 → 短期是否在加速
        proj = ws * 4 if ws is not None else None
        accel = round(proj / ms, 2) if (proj and ms) else None
        rows.append({
            "sku": s,
            "name": ((M or W).get("name") or "")[:60],
            "price": f(M, "avgPrice") or f(W, "avgPrice"),
            "monthly_sold": ms, "monthly_gmv": f(M, "gmvSum"),
            "monthly_dyn": f(M, "salesDynamics"),
            "weekly_sold": ws, "weekly_gmv": f(W, "gmvSum"),
            "weekly_dyn": f(W, "salesDynamics"),
            "week_proj_28d": round(proj, 0) if proj else None,
            "accel": accel,          # >1 = 最近一周在加速，<1 = 在减速
            "signals": ("周度反弹" if (accel and accel > 1.15 and (f(M, "salesDynamics") or 0) < 0)
                        else ("周度走弱" if (accel and accel < 0.85 and (f(W, "salesDynamics") or 0) < 0)
                              else "")),
        })

    rows.sort(key=lambda r: -(r["accel"] or -1))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n{'SKU':<12}{'月销':>7}{'月环比':>8}{'周销':>6}{'周环比':>8}{'周折28天':>9}{'加速比':>7}  信号")
    for r in rows[:20]:
        print(f"{r['sku']:<12}{r['monthly_sold'] or 0:>7.0f}"
              f"{(r['monthly_dyn'] if r['monthly_dyn'] is not None else 0):>7.1f}%"
              f"{r['weekly_sold'] or 0:>6.0f}"
              f"{(r['weekly_dyn'] if r['weekly_dyn'] is not None else 0):>7.1f}%"
              f"{r['week_proj_28d'] or 0:>9.0f}"
              f"{(r['accel'] if r['accel'] is not None else 0):>7.2f}  {r['signals']}")
    print(f"\n共 {len(rows)} 个 SKU → {a.out}")
    print("加速比 >1.15 = 最近一周在加速（月度虽跌但短期反弹）· <0.85 = 周度也在跌")
    return 0


if __name__ == "__main__":
    sys.exit(main())
