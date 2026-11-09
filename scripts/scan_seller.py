#!/usr/bin/env python3
"""店铺全量扫描 + 差分对比

用 /seller/<slug>/?page=N&sorting=popular（36 条/页）串行翻页，扫完一家店的全部在售 SKU，
存成基线快照；再跑一次即可与上一份基线做差分（新增/下架/价格变动/库存变动/评分变动）。

用法:
  python scripts/scan_seller.py --sellers meliora-2709553
  python scripts/scan_seller.py --sellers meliora-2709553 --diff
  python scripts/scan_seller.py --sellers meliora-2709553,2709553 --max-pages 60 --delay 0.8

输出: data/seller_baselines/<slug>_<YYYYMMDD-HHMMSS>.json
      --diff 时另存 <slug>_diff_<时间>.json
"""
import argparse
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ozon_buyer.collector import (  # noqa: E402
    load_valid_cookie,
    cdp_warmup,
    save_cookie_cache,
    request_entrypoint_page,
    extract_skus_from_page,
)

DEFAULT_PROXY = os.environ.get("OZON_PROXY")  # 默认 None = 直连；代理出口会被 Ozon 判为风控
FIELDS = ("sku_id", "title", "price", "rating", "reviews_count", "stock_max", "link", "is_advert")


def get_creds(force=False, proxy=None):
    creds = None if force else load_valid_cookie()
    if creds:
        return creds
    sys.stderr.write("[i] cookie 缺失或过期，启动浏览器预热...\n")
    creds = cdp_warmup(target_url="https://www.ozon.ru/", proxy=proxy, no_proxy=(proxy is None))
    if creds and creds.get("cookie"):
        save_cookie_cache(creds)
    return creds


def scan_one(seller, pages, delay, proxy):
    """串行翻页扫一家店，返回快照 dict"""
    creds = get_creds(proxy=proxy)
    if not creds:
        raise RuntimeError("无法取得 cookie（预热失败）")

    base = f"/seller/{seller}/"
    rows = {}
    page_log = []
    t0 = time.time()
    rebuilt = 0

    for p in range(1, pages + 1):
        url = f"{base}?page={p}&sorting=popular"
        items = None
        for attempt in range(2):
            try:
                data = request_entrypoint_page(url, creds, proxy)
                items = extract_skus_from_page(data)
                break
            except RuntimeError as e:
                msg = str(e)
                if "403" in msg or "401" in msg:
                    if attempt == 0:
                        rebuilt += 1
                        sys.stderr.write(f"[i] p{p} 触发 {msg}，重建 cookie 重试...\n")
                        creds = get_creds(force=True, proxy=proxy)
                        time.sleep(3)
                        continue
                raise
        if items is None:
            break

        new = [x for x in items if x.get("sku_id") and x["sku_id"] not in rows]
        for x in new:
            rows[x["sku_id"]] = {k: x.get(k) for k in FIELDS}
        page_log.append([p, len(items), len(new), len(rows), round(time.time() - t0, 2)])
        sys.stderr.write(f"  p{p}: tile={len(items)} 新增={len(new)} 累计={len(rows)}\n")

        if not items or not new:
            break
        if p < pages:
            time.sleep(delay)

    return {
        "seller": seller,
        "base_path": base,
        "mode": "sorting=popular (36/页, 串行)",
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "pages": page_log,
        "page_count": len(page_log),
        "total": len(rows),
        "elapsed": round(time.time() - t0, 2),
        "cookie_rebuilds": rebuilt,
        "skus": list(rows.values()),
    }


def latest_baseline(seller, out_dir, exclude=None):
    files = sorted(glob.glob(os.path.join(out_dir, f"{seller}_*.json")))
    files = [f for f in files if os.path.basename(f) != exclude]
    return files[-1] if files else None


def diff_snapshots(prev, cur):
    a = {x["sku_id"]: x for x in prev.get("skus", [])}
    b = {x["sku_id"]: x for x in cur.get("skus", [])}
    added = sorted(set(b) - set(a))
    removed = sorted(set(a) - set(b))
    common = set(a) & set(b)

    def num(v):
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    price_c, stock_c, rating_c = [], [], []
    for s in common:
        pa, pb = num(a[s].get("price")), num(b[s].get("price"))
        if pa is not None and pb is not None and pa != pb:
            price_c.append({
                "sku_id": s,
                "old": pa, "new": pb,
                "delta": round(pb - pa, 2),
                "delta_pct": round((pb - pa) / pa * 100, 2) if pa else None,
                "title": b[s].get("title"),
            })
        sa, sb = num(a[s].get("stock_max")), num(b[s].get("stock_max"))
        if sa != sb:
            stock_c.append({"sku_id": s, "old": a[s].get("stock_max"), "new": b[s].get("stock_max")})
        ra, rb = num(a[s].get("rating")), num(b[s].get("rating"))
        if ra is not None and rb is not None and ra != rb:
            rating_c.append({"sku_id": s, "old": ra, "new": rb})

    return {
        "seller": cur.get("seller"),
        "from": {"captured_at": prev.get("captured_at"), "total": prev.get("total")},
        "to": {"captured_at": cur.get("captured_at"), "total": cur.get("total")},
        "added": added,
        "removed": removed,
        "added_count": len(added),
        "removed_count": len(removed),
        "common": len(common),
        "price_changed": price_c,
        "stock_changed": stock_c,
        "rating_changed": rating_c,
    }


def main():
    ap = argparse.ArgumentParser(description="店铺全量扫描与差分")
    ap.add_argument("--sellers", required=True, help="逗号分隔的店铺 slug 或 id")
    ap.add_argument("--max-pages", type=int, default=80, help="单店最大翻页数（默认 80，约 2880 品）")
    ap.add_argument("--delay", type=float, default=0.8, help="页间隔秒（默认 0.8）")
    ap.add_argument("--proxy", default=DEFAULT_PROXY, help="代理地址；默认直连（代理出口已被 Ozon 风控）")
    ap.add_argument("--out-dir", default="data/seller_baselines", help="基线输出目录")
    ap.add_argument("--diff", action="store_true", help="与上一份基线做差分")
    args = ap.parse_args()

    proxy = args.proxy
    sellers = [s.strip() for s in args.sellers.split(",") if s.strip()]
    os.makedirs(args.out_dir, exist_ok=True)

    for seller in sellers:
        sys.stderr.write(f"\n=== 扫描 {seller} ===\n")
        snap = scan_one(seller, args.max_pages, args.delay, proxy)
        fname = f"{seller}_{time.strftime('%Y%m%d-%H%M%S')}.json"
        path = os.path.join(args.out_dir, fname)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=2)
        print(f"[scan] {seller}: {snap['total']} 个 SKU / {snap['page_count']} 页 / "
              f"{snap['elapsed']}s → {path}")

        if args.diff:
            prev_path = latest_baseline(seller, args.out_dir, exclude=fname)
            if not prev_path:
                print("  [diff] 没有历史基线，跳过（已存本次为基线）")
                continue
            prev = json.load(open(prev_path, encoding="utf-8"))
            d = diff_snapshots(prev, snap)
            dpath = os.path.join(args.out_dir, f"{seller}_diff_{time.strftime('%Y%m%d-%H%M%S')}.json")
            with open(dpath, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
            print(f"  [diff] 对比 {os.path.basename(prev_path)} → "
                  f"新增 {d['added_count']} / 下架 {d['removed_count']} / 共同 {d['common']} / "
                  f"调价 {len(d['price_changed'])} / 库存变动 {len(d['stock_changed'])} → {dpath}")


if __name__ == "__main__":
    main()
