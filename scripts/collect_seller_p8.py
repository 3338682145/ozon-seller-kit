#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卖家端 p8 搜索位本地采集（cookie + 纯 HTTP，无浏览器常驻）

输出与 antistress 的 `data/p8-items.jsonl` 同构，下游 master / keyword_sku 直接吃：
    {"kw": "...", "n": 108, "headers": [...], "items": [...]}
    {"kw": "...", "n": 0, "no_data": true}

用法:
    python3 scripts/collect_seller_p8.py --words data/words.txt --out data/p8-local.jsonl
    python3 scripts/collect_seller_p8.py --words-file data/seerfar-final-todo.txt
    python3 scripts/collect_seller_p8.py --todo-file data/p8-items.jsonl   # 补采已采过的缺失词
    python3 scripts/collect_seller_p8.py --words "сквиш,антистресс" --concurrency 3

实测性能（2026-10-30，店铺 <seller_id>）：
    并发 3 + 空包停顿补采 ≈ 12 词/分钟；纯串行 ≈ 8.9 词/分钟
    并发 6 首发命中率掉到 35%，但停顿 30s 后串行补回 13/13
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

from ozon_seller import AuthExpired, CONTROL_WORDS, Pacer, SellerClient  # noqa: E402


def load_done(path: Path) -> set:
    done = set()
    if not path.exists():
        return done
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("n"):          # 只认有数据的，空包允许重采
            done.add(d.get("kw"))
    return done


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--words", default="", help="逗号分隔，快速测试用")
    ap.add_argument("--words-file", default="", help="一行一个词")
    ap.add_argument("--out", default=str(ROOT / "data" / "p8-local.jsonl"))
    ap.add_argument("--concurrency", type=int, default=1)   # 实测：并发>1 立刻触发静默空包
    ap.add_argument("--pause", type=float, default=28.0, help="空包后停顿秒数")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 个词")
    ap.add_argument("--min-delay", type=float, default=1.2, help="每次请求最小间隔（秒）")
    args = ap.parse_args()

    # ── 词表
    if args.words:
        words = [w.strip() for w in args.words.split(",") if w.strip()]
    elif args.words_file:
        words = [w.strip() for w in
                 Path(args.words_file).read_text(encoding="utf-8").splitlines() if w.strip()]
    else:
        ap.error("需要 --words 或 --words-file")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = load_done(out_path)
    todo = [w for w in words if w not in done]
    if args.limit:
        todo = todo[:args.limit]
    if not todo:
        print(f"没有待采词（已完成 {len(done)} / 共 {len(words)}）")
        return 0

    client = SellerClient()
    print(f"店铺 {client.jar.company_id} | cookie {len(client.jar.cookie_names)} 个 | "
          f"待采 {len(todo)} / 总 {len(words)} | 并发 {args.concurrency}")

    # ── 开跑前先确认会话活着，别白跑
    probe = client.probe()
    if not probe.get("ok"):
        print(f"✗ 探活失败: {probe}", file=sys.stderr)
        if probe.get("error") == "auth":
            print("  → cookie 失效，执行：bash scripts/refresh_seller_cookie.sh", file=sys.stderr)
        return 2
    print(f"探活 OK | 对照词 {probe['control_items']} 条 | {probe['latency_ms']}ms")

    pacer = Pacer(concurrency=args.concurrency, pause_s=args.pause)
    lock = threading.Lock()
    fh = out_path.open("a", encoding="utf-8")
    t0 = time.time()
    counters = {"ok": 0, "empty": 0, "err": 0, "nodata": 0, "throttled": 0}

    def one(kw: str):
        with pacer:
            if args.min_delay:
                time.sleep(args.min_delay)
            try:
                r = client.explainer(kw)
            except AuthExpired as exc:
                with lock:
                    counters["err"] += 1
                    print(f"  ! auth: {exc}", file=sys.stderr)
                return kw, None, "auth"
            except Exception as exc:  # noqa: BLE001
                with lock:
                    counters["err"] += 1
                return kw, None, f"err:{exc}"
        if r["n"] > 0:
            with lock:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                fh.flush()
                counters["ok"] += 1
            return kw, r, None
        with lock:
            counters["empty"] += 1
        return kw, None, "empty"

    # ── 阶段 1：首发。前 10 个词先探水温，空包率 >40% 立刻降级串行
    probe_n = min(10, len(todo))
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        head = list(ex.map(one, todo[:probe_n]))
    head_empty = sum(1 for _, _, tag in head if tag == "empty")
    if head_empty >= max(3, probe_n * 0.4) and args.concurrency > 1:
        print(f"  ⚠ 首发 {probe_n} 词空包 {head_empty} 个 → 判定并发过高，"
              f"剩余降级为串行 + {args.min_delay}s 间隔", file=sys.stderr)
        args.concurrency = 1
        args.min_delay = max(args.min_delay, 1.2)
        pacer = Pacer(concurrency=1, pause_s=args.pause)
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        results = head + list(ex.map(one, todo[probe_n:]))
    empties = [kw for kw, _, tag in results if tag == "empty"]
    auth_fail = sum(1 for _, _, tag in results if tag == "auth")
    print(f"首发：ok={counters['ok']} 空包={len(empties)} 错误={counters['err']} "
          f"用时 {(time.time() - t0) / 60:.1f}min")

    if auth_fail and auth_fail >= max(2, len(todo) // 4):
        print("✗ 大量 auth 失败，cookie/uuid 已失效，停止。", file=sys.stderr)
        fh.close()
        return 2

    # ── 阶段 2：空包先验对照词，区分「限流」vs「真无数据」
    if empties:
        print(f"空包 {len(empties)} 个 → 停顿 {args.pause:.0f}s 后验对照词")
        pacer.pause()
        ctrl = client.probe()
        if not ctrl.get("ok"):
            print(f"  对照词仍空 → 会话被限流，本轮放弃剩余 {len(empties)} 个空包。"
                  f"过 10-20 分钟重跑同命令即可续采（断点在 {out_path}）")
            # 关键：限流导致的不写 no_data，否则下游会把它们当成「真实无数据」污染库
            for kw in empties:
                with lock:
                    fh.write(json.dumps({"kw": kw, "n": 0, "throttled": True},
                                        ensure_ascii=False) + "\n")
            fh.flush()
            counters["throttled"] += len(empties)
        else:
            print(f"  对照词恢复（{ctrl['control_items']} 条）→ 串行补采")
            recovered = 0
            for i, kw in enumerate(empties, 1):
                try:
                    r = client.explainer(kw)
                except Exception as exc:  # noqa: BLE001
                    print(f"  补采 {kw} 失败 {exc}", file=sys.stderr)
                    continue
                if r["n"] > 0:
                    with lock:
                        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                        fh.flush()
                        counters["ok"] += 1
                        recovered += 1
                else:
                    with lock:
                        fh.write(json.dumps({"kw": kw, "n": 0, "no_data": True},
                                            ensure_ascii=False) + "\n")
                        fh.flush()
                        counters["nodata"] += 1
                if i % 5 == 0:
                    time.sleep(1.0)
            print(f"  补回 {recovered}/{len(empties)}")

    fh.close()
    el = (time.time() - t0) / 60
    total_ok = counters["ok"]
    print(f"\n完成：有数据 {total_ok} | 真空 {counters['nodata']} | "
          f"限流待补 {counters['throttled']} | 错误 {counters['err']} | "
          f"{el:.1f}min | {total_ok / el:.1f} 词/分钟")
    print(f"输出 {out_path}")
    print(f"请求统计 {client.stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
