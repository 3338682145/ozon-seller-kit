"""卖家端（seller.ozon.ru）本地 HTTP 采集客户端。

设计依据（2026-10-30 实测，macOS / 卖家 5149811）：

  * cookie + UA 纯 HTTP 就能打通 seller.ozon.ru 分析接口，不需要浏览器常驻
  * 必须在 CDP 里取 cookie（__Secure-token / __Secure-product-user-id 是 HttpOnly）
  * UA 与 token 绑定，必须与签发它的浏览器一致，否则 307
  * explainer（p8）后端慢（串行 2-14s/词）且限流是"静默空包"：HTTP 200 + items=0
  * what_to_sell（p6）宽松得多：并发 5、500 SKU/4.7s 零空包

失败的三种形态要分开，否则会把限流当成"该词无数据"污染库：
  1. AuthExpired  —— 401/403/307 或返回 HTML 挑战页 → 重 mint cookie
  2. Throttled    —— HTTP 200 但对照词也空 → 停顿后补采
  3. NoData       —— HTTP 200、对照词有数、只有该词空 → 真实无数据
"""
from __future__ import annotations

import json
import random
import ssl
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

SSL_CTX = ssl.create_default_context()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """不自动跟随重定向。307 是 Ozon 前层反爬的 `__rr` 循环，
    必须手动接住下发的 __Secure-ETC 再重试，否则会无限转圈。"""

    def redirect_request(self, *args, **kwargs):  # noqa: D102
        return None


_opener = urllib.request.build_opener(_NoRedirect())

HOME = Path.home()
SELLER_DIR = HOME / ".config" / "ozon-seller"
COOKIE_FILE = SELLER_DIR / "cookie.txt"
UA_FILE = SELLER_DIR / "cookie.ua"
META_FILE = SELLER_DIR / "meta.json"

BASE = "https://seller.ozon.ru"
EXPLAINER = "/api/search-query-analytics/v2/external/explanation_by_id"
WHAT_TO_SELL = "/api/site/seller-analytics/what_to_sell/data/v3"
CJM_ANALYTICS = "/api/search-query-analytics/v1/cjm/get-seller-analytics"
CJM_HEADERS = "/api/search-query-analytics/v1/cjm/get-seller-analytics-table-headers"

# 判限流用的对照词：这两个词永远有数据
CONTROL_WORDS = ("сквиш", "антистресс")


class AuthExpired(RuntimeError):
    """cookie / UA / uuid 失效：需要重新 mint。"""


class Throttled(RuntimeError):
    """会话被限流：HTTP 200 但静默空包。"""


@dataclass
class Jar:
    cookie: str
    ua: str
    company_id: str
    uuid: Optional[str] = None
    cookie_names: List[str] = field(default_factory=list)
    minted_at: str = ""
    cookie_file: Optional[Path] = None

    def update_from_set_cookie(self, set_cookies) -> list:
        """吸收服务端下发的 Set-Cookie，返回被更新的 cookie 名列表。

        2026-11-02 实测：认证接口每次返回都可能带新的 `abt_data`（反爬令牌）。
        浏览器会接收，纯 HTTP 客户端如果忽略，就会拿着一份冻结的 abt_data，
        过一段时间被前层 nginx 判为异常 —— 表现是 307 + __rr 无限重定向。
        """
        changed = []
        jar = {}
        for part in self.cookie.split("; "):
            i = part.find("=")
            if i > 0:
                jar[part[:i]] = part[i + 1:]
        for raw in set_cookies or []:
            kv = raw.split(";")[0]
            if "=" not in kv:
                continue
            name, val = kv.split("=", 1)
            if jar.get(name) != val:
                jar[name] = val
                changed.append(name)
        if changed:
            self.cookie = "; ".join(f"{k}={v}" for k, v in jar.items())
            if self.cookie_file:
                try:
                    self.cookie_file.write_text(self.cookie, encoding="utf-8")
                    self.cookie_file.chmod(0o600)
                except OSError:
                    pass
        return changed

    @classmethod
    def load(cls, cookie_file: Path = COOKIE_FILE) -> "Jar":
        if not cookie_file.exists():
            raise AuthExpired(f"cookie 不存在: {cookie_file}（先跑 mint_seller_cookie.mjs）")
        cookie = cookie_file.read_text(encoding="utf-8").strip()
        ua_path = cookie_file.with_suffix(".ua")
        ua = ua_path.read_text(encoding="utf-8").strip() if ua_path.exists() else ""
        meta_path = cookie_file.parent / "meta.json"
        meta: Dict[str, Any] = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                meta = {}
        company_id = str(meta.get("company_id") or "")
        if not company_id:
            for part in cookie.split("; "):
                if part.startswith("sc_company_id="):
                    company_id = part.split("=", 1)[1]
                    break
        if not company_id:
            raise AuthExpired("cookie 里没有 sc_company_id，卖家端未登录")
        obj = cls(cookie=cookie, ua=ua, company_id=company_id, uuid=meta.get("uuid"),
                  cookie_names=meta.get("cookie_names") or [], minted_at=meta.get("minted_at", ""))
        obj.cookie_file = cookie_file
        return obj


class SellerClient:
    """线程安全的卖家端客户端（每次请求独立连接，不共享状态）。"""

    def __init__(self, jar: Optional[Jar] = None, timeout: int = 60,
                 cookie_file: Path = COOKIE_FILE) -> None:
        self.jar = jar or Jar.load(cookie_file)
        self.timeout = timeout
        self._lock = threading.Lock()
        self.stats = {"req": 0, "ok": 0, "empty": 0, "err": 0, "auth": 0}

    # ── 底层 ────────────────────────────────────────────────────────
    def _headers(self, app_name: str, page_type: str, referer: str) -> Dict[str, str]:
        return {
            "user-agent": self.jar.ua,
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-Hans,zh;q=0.9,ru;q=0.8",
            "content-type": "application/json",
            "origin": BASE,
            "referer": f"{BASE}{referer}",
            "x-o3-app-name": app_name,
            "x-o3-page-type": page_type,
            "x-o3-language": "zh-Hans",
            "x-o3-company-id": self.jar.company_id,
            "x-o3-timezone": "Asia/Shanghai",
            "cookie": self.jar.cookie,
        }

    def _absorb(self, headers) -> None:
        """接住服务端下发的 cookie（abt_data / __Secure-ETC 会周期性轮换）"""
        try:
            sc = headers.get_all("Set-Cookie") or []
        except AttributeError:
            return
        if not sc:
            return
        changed = self.jar.update_from_set_cookie(sc)
        if changed:
            with self._lock:
                self.stats.setdefault("cookie_updates", 0)
                self.stats["cookie_updates"] += len(changed)

    def post(self, path: str, body: Dict[str, Any], *, app_name: str,
             page_type: str, referer: str, retries: int = 2) -> Dict[str, Any]:
        url = BASE + path
        headers = self._headers(app_name, page_type, referer)
        method = "POST" if body is not None else "GET"
        payload = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        last: Optional[Exception] = None

        for attempt in range(retries + 1):
            req = urllib.request.Request(url, data=payload, headers=headers, method=method)
            with self._lock:
                self.stats["req"] += 1
            try:
                with _opener.open(req, timeout=self.timeout) as r:
                    raw = r.read()
                    self._absorb(r.headers)
            except urllib.error.HTTPError as exc:
                self._absorb(exc.headers)          # 307 会带新的 __Secure-ETC
                raw = exc.read()[:400]
                if exc.code in (301, 302, 307, 308) and attempt < 2:
                    # 前层反爬重定向：接住下发 cookie 后重试，跳出 __rr 循环
                    time.sleep(0.4 * (attempt + 1))
                    continue
                if exc.code in (401, 403, 307):
                    with self._lock:
                        self.stats["auth"] += 1
                    raise AuthExpired(f"HTTP {exc.code} @ {path}: {raw[:120]!r}") from exc
                last = exc
                time.sleep(1.5 * (attempt + 1))
                continue
            except Exception as exc:  # noqa: BLE001
                last = exc
                time.sleep(1.5 * (attempt + 1))
                continue

            # 挑战页/登录页都是 HTML，JSON 解析失败即视为验签失效
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                snippet = raw[:200].decode("utf-8", "replace")
                if "<html" in snippet.lower() or "Antibot" in snippet or "challenge" in snippet.lower():
                    with self._lock:
                        self.stats["auth"] += 1
                    raise AuthExpired(f"返回 HTML 挑战页 @ {path}: {snippet[:100]}") from None
                with self._lock:
                    self.stats["err"] += 1
                last = RuntimeError(f"非 JSON 响应 @ {path}")
                time.sleep(1.5 * (attempt + 1))

        raise RuntimeError(f"请求失败 {path}: {last}") from last

    # ── 高层：p8 搜索位 ─────────────────────────────────────────────
    def explainer(self, keyword: str) -> Dict[str, Any]:
        """返回 {kw, n, headers, items}，与 p8-items.jsonl 行同构。"""
        if not self.jar.uuid:
            raise AuthExpired("meta.json 缺 uuid，重新 mint 一次")
        body = {
            "sellerId": self.jar.company_id,
            "query": keyword,
            "uuid": self.jar.uuid,
            "skus": [],
            "sortOption": {"headerKey": "position", "direction": "SortDirectionAscending"},
            "itemsPerPage": "108",
            "pageNumber": "1",
            "onlyCurSellerItems": False,
            "applicationScope": "SCOPE_BIG_OZON",
        }
        j = self.post(EXPLAINER, body, app_name="seller-ui", page_type="analytics-search",
                      referer="/app/analytics-search/search-results/explainer")
        items = j.get("items") or []
        with self._lock:
            self.stats["ok" if items else "empty"] += 1
        return {"kw": keyword, "n": len(items), "headers": j.get("headers"), "items": items}

    # ── 高层：p6 销量 ──────────────────────────────────────────────
    def what_to_sell(self, skus: Optional[List[str]] = None, offset: int = 0,
                     limit: int = 50, period: str = "monthly") -> List[Dict[str, Any]]:
        """不带 filter.skus 时按 GMV 榜翻页；带 skus 时按 SKU 批量查。"""
        flt: Dict[str, Any] = {"stock": "any_stock", "period": period}
        if skus:
            flt["skus"] = [str(s) for s in skus]
        body = {"limit": str(limit), "offset": str(offset), "filter": flt,
                "sort": {"key": "sum_gmv_desc"}}
        j = self.post(WHAT_TO_SELL, body, app_name="seller-ui", page_type="analytics_platform",
                      referer="/app/analytics/what-to-sell/ozon-bestsellers")
        items = j.get("items") or []
        with self._lock:
            self.stats["ok" if items else "empty"] += 1
        return items

    # ── 高层：cjm 我的商品（搜索链路）────────────────────────────────
    def my_products(self, period_from: str, period_to: str,
                    sort_by: str = "METRICS_TYPE_UNIQUE_VIEW_USERS",
                    sort_direction: str = "DESCENDING", per_page: int = 500,
                    search: str = "", categories: Optional[List[str]] = None) -> Dict[str, Any]:
        """「搜索可见性 → 我的商品」表：本店每个 SKU 在搜索链路上的表现。

        参数坑：body 键必须是 `seller_id`（蛇形），写 sellerId/companyId 一律 403
        `Failed to get body company ID`。

        指标全是本地化字符串（"372 152" / "7,52%" / "22 026 ₽"），自己要 parse。
        sort_by 取值见 `cjm_table_headers()` 里的 metricType。

        返回 {skus: [...], totalNumberOfItems, totalPagesCount}
        """
        body = {
            "seller_id": self.jar.company_id,
            "period_from": period_from,
            "period_to": period_to,
            "count_total_items": True,
            "page_number": "0",
            "items_per_page": str(per_page),
            "sort_by": sort_by,
            "sort_direction": sort_direction,
            "filters": {"categories": categories or [], "search": search},
        }
        j = self.post(CJM_ANALYTICS, body, app_name="seller-ui",
                      page_type="search_query_analytics",
                      referer="/app/analytics-search/search-results/my-products")
        items = j.get("skus") or []
        with self._lock:
            self.stats["ok" if items else "empty"] += 1
        return j

    def cjm_table_headers(self) -> List[Dict[str, Any]]:
        """列定义（含 metricType / 中文表头 / 提示文案），用来把指标 key 映射成人话。"""
        url = f"{BASE}{CJM_HEADERS}?seller_id={self.jar.company_id}"
        req = urllib.request.Request(url, headers={
            "user-agent": self.jar.ua,
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-Hans,zh;q=0.9,ru;q=0.8",
            "origin": BASE,
            "referer": f"{BASE}/app/analytics-search/search-results/my-products",
            "x-o3-app-name": "seller-ui",
            "x-o3-page-type": "search_query_analytics",
            "x-o3-language": "zh-Hans",
            "x-o3-company-id": self.jar.company_id,
            "cookie": self.jar.cookie,
        }, method="GET")
        with urllib.request.urlopen(req, timeout=self.timeout, context=SSL_CTX) as r:
            return (json.loads(r.read()) or {}).get("headers") or []

    # ── 探活 ──────────────────────────────────────────────────────
    def probe(self) -> Dict[str, Any]:
        """真打一次对照词，返回鉴权/限流结论。"""
        out: Dict[str, Any] = {"company_id": self.jar.company_id,
                               "uuid": (self.jar.uuid or "")[:8] + "…" if self.jar.uuid else None,
                               "minted_at": self.jar.minted_at, "ok": False}
        t0 = time.time()
        try:
            r = self.explainer(CONTROL_WORDS[0])
        except AuthExpired as exc:
            out.update(error="auth", detail=str(exc)[:160])
            return out
        except Exception as exc:  # noqa: BLE001
            out.update(error="network", detail=str(exc)[:160])
            return out
        out["latency_ms"] = int((time.time() - t0) * 1000)
        out["control_items"] = r["n"]
        if r["n"] > 0:
            out["ok"] = True
        else:
            out.update(error="throttled", detail="对照词空包：会话被限流，不是 cookie 失效")
        return out


# ── 令牌桶 + 空包判定 ───────────────────────────────────────────────
class Pacer:
    """并发闸 + 空包积压。空包集中后统一停顿补采，比逐条重试有效（实测 13/13 补回）。"""

    def __init__(self, concurrency: int = 3, pause_s: float = 28.0) -> None:
        self.sem = threading.Semaphore(max(1, concurrency))
        self.pause_s = pause_s

    def __enter__(self) -> "Pacer":
        self.sem.acquire()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.sem.release()

    def pause(self, jitter: float = 4.0) -> None:
        time.sleep(self.pause_s + random.uniform(0, jitter))
