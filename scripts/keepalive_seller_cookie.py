#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卖家端 cookie 保活守护

为什么需要它（2026-10-30~11-01 实测）：
  1. `__Secure-token` **不会自动轮换** —— 浏览器里看，连续业务请求前后值完全一样。
     它不是「到期续期」模型，是「登录发放 → 服务端吊销」模型。
  2. 只有 `abt_data`（反爬令牌）每次页面交互都会变（990 → 984 字符…），
     纯 HTTP 客户端拿静态的那份也能用，只要 IP + UA 不变。
  3. 所以能做的保活只有三件事：
     a) **心跳**：定期打一个便宜接口，让会话保持活跃 + 尽早发现吊销
     b) **减量**：控制请求速率（p8 并发只能是 1，见 README 复盘）
     c) **早发现早重签**：401 一出现就重签，别等采集任务跑到一半才死

用法:
    python3 scripts/keepalive_seller_cookie.py                # 探一次，打印状态
    python3 scripts/keepalive_seller_cookie.py --loop 15      # 常驻，每 15 分钟探一次
    python3 scripts/keepalive_seller_cookie.py --status-file ~/.config/ozon-seller/health.json

退出码: 0 正常 / 2 鉴权失效（需重签） / 3 限流 / 4 网络
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ozon_seller import COOKIE_FILE, Jar, SELLER_DIR  # noqa: E402

BASE = "https://seller.ozon.ru"
# 最便宜的鉴权探针：129 字节 / 1.2s。比 explainer（108 条、6-16s）省得多
PROBE = "/api/search-query-analytics/v1/accessibility/enabled_features"
HEALTH = SELLER_DIR / "health.json"


def probe(jar: Jar, timeout: int = 25) -> dict:
    url = f"{BASE}{PROBE}?sellerId={jar.company_id}&userId=0"
    req = urllib.request.Request(url, headers={
        "user-agent": jar.ua,
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-Hans,zh;q=0.9",
        "origin": BASE,
        "referer": f"{BASE}/app/analytics-search/search-results/explainer",
        "x-o3-app-name": "seller-ui",
        "x-o3-page-type": "analytics-search",
        "x-o3-language": "zh-Hans",
        "x-o3-company-id": str(jar.company_id),
        "x-o3-timezone": "Asia/Shanghai",
        "cookie": jar.cookie,
    })
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
        return {"ok": True, "code": 200, "ms": int((time.time() - t0) * 1000),
                "bytes": len(body)}
    except urllib.error.HTTPError as e:
        raw = e.read()
        tag = "auth" if e.code in (401, 403, 307) else "http"
        return {"ok": False, "code": e.code, "error": tag,
                "ms": int((time.time() - t0) * 1000),
                "detail": raw[:160].decode("utf-8", "replace")}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "code": 0, "error": "network",
                "ms": int((time.time() - t0) * 1000), "detail": str(exc)[:160]}


def token_meta(jar: Jar) -> dict:
    """从 __Secure-token 里抠时间戳（格式: p8.<uid>.<x>.<ab>.<sig>.<ts1>.<ts2>.<v>.<sig2>.<hash>）"""
    out = {}
    for part in jar.cookie.split("; "):
        if part.startswith("__Secure-token="):
            segs = part.split("=", 1)[1].split(".")
            stamps = [s for s in segs if s.isdigit() and len(s) == 14]
            if len(stamps) >= 2:
                out["token_ts_1"] = stamps[0]
                out["token_ts_2"] = stamps[1]
            out["token_uid"] = segs[1] if len(segs) > 1 else None
        if part.startswith("abt_data="):
            out["abt_len"] = len(part) - len("abt_data=")
    return out


def once(status_file: Path) -> int:
    try:
        jar = Jar.load()
    except Exception as exc:  # noqa: BLE001
        print(f"✗ jar 读取失败: {exc}", file=sys.stderr)
        return 2

    r = probe(jar)
    tm = token_meta(jar)
    rec = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "company_id": jar.company_id,
        **tm, **r,
    }
    # 历史保留最近 500 条
    hist = []
    if status_file.exists():
        try:
            hist = json.loads(status_file.read_text(encoding="utf-8"))
            if not isinstance(hist, list):
                hist = []
        except Exception:  # noqa: BLE001
            hist = []
    hist.append(rec)
    hist = hist[-500:]
    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.write_text(json.dumps(hist, ensure_ascii=False, indent=1), encoding="utf-8")

    ts = rec.get("checked_at")
    if r["ok"]:
        print(f"✓ {ts} | 店铺 {jar.company_id} | {r['ms']}ms | {r['bytes']}B | "
              f"abt_data {tm.get('abt_len','?')} 字符")
        return 0
    if r["error"] == "auth":
        print(f"✗ {ts} | 鉴权失效 HTTP {r['code']} —— 需要重签\n   {r.get('detail','')}", file=sys.stderr)
        return 2
    if r["error"] == "network":
        print(f"⚠ {ts} | 网络问题 {r.get('detail','')}", file=sys.stderr)
        return 4
    print(f"⚠ {ts} | HTTP {r['code']} {r.get('detail','')}", file=sys.stderr)
    return 3


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status-file", default=str(HEALTH))
    ap.add_argument("--loop", type=int, default=0, help="常驻模式：每隔 N 分钟探一次（0=只探一次）")
    a = ap.parse_args()
    sf = Path(a.status_file)

    if not a.loop:
        return once(sf)

    print(f"保活守护启动：每 {a.loop} 分钟探一次，状态写 {sf}")
    while True:
        rc = once(sf)
        if rc == 2:
            print("→ 鉴权已失效，停止心跳。执行 bash scripts/refresh_seller_cookie.sh 重签后重启", file=sys.stderr)
            print("  （若要在失效时自动重签，外面用 --renew-on-fail 的 shell 包装）", file=sys.stderr)
            return 2
        time.sleep(max(60, a.loop * 60))


if __name__ == "__main__":
    sys.exit(main())
