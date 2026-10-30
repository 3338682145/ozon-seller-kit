# 卖家端本地采集器（seller.ozon.ru）

cookie jar 驱动，**纯 Python HTTP，不需要浏览器常驻**。

原来 antistress 那套是每请求都走 ego-browser 的 `page.fetch()`，浏览器一关就停、单通道、10s/词。
这套把浏览器降级成「证书签发器」：偶尔 mint 一次 cookie，剩下的活全在 Python 里干。

---

## 一句话结论

**能。而且不需要"自动刷新 cookie"这种机制** —— 卖家端 token 寿命是 **1 年**（实测 TTL），
日常根本不刷；真正需要重 mint 的只有换店／注销／被风控踢。所以做得对的东西是
「探活 + 失效才 mint」，不是「定时刷新」。

而上一版笔记里记的「seller.ozon.ru 直连吃 403 fab_chlg」是**错的**，
当时缺的是 HttpOnly 的 `__Secure-token` 和挑战 cookie `abt_data`（`document.cookie` 读不到它们）。

---

## 实测矩阵（2026-10-30，店铺 <seller_id> / <store_name>）

| 接口 | 用途 | 纯 HTTP | 单请求延迟 | 并发上限 | 实测吞吐 |
|---|---|---|---|---|---|
| `explanation_by_id` | p8 搜索位 108 名 | ✅ 200 | 2-14s（后端慢） | **只能是 1** | 串行 8.9 词/分钟（并发反而更慢，见复盘） |
| `what_to_sell/data/v3` | p6 销量 enrich | ✅ 200 | 1.3-3s | 3-4 | **3,300 SKU/分钟**（并发4，实测 3,073 SKU/60s） |

## p6 的两个时间口径（`filter.period`）

**只有两个有效值，其他任何字符串都静默回退到 monthly，不报错。**

| 传值 | 实际口径 | 说明 |
|---|---|---|
| `"monthly"` | **28 天** | 默认 |
| `"weekly"` | **7 天** | 唯一另一个生效值 |
| `"daily"` / `"7d"` / `"28d"` / `"WEEKLY"` / `"quarterly"` … | ⚠ 全部退化成 28 天 | 200 正常返回，但你拿到的是月度数——**最坑的一种失败** |

同一 SKU 两个口径结论可以完全相反。实测 `3107016631`：

```
monthly: sold=218   gmv=845,494   salesDynamics=-15.4%   ← 28 天在跌
weekly : sold=74    gmv=258,241   salesDynamics=+52.8%   ← 最近 7 天在反弹
```

周销 ×4 折成 28 天 ≈ 296，比月销 218 高 36% → **月度还在跌但短期已反弹**，这是补货/加推的先行信号，单看月度会漏掉。

对比工具：`python3 scripts/compare_seller_periods.py --skus-file <清单>`

字段集两个口径完全一样（都是 67 个 key），差异只体现在数值上。

对比原 ego-browser 版：p8 约 6 词/分钟（10s/词），1642 词跑 4.5 小时。本地版同样条件约 2 小时，
而且**能多店铺并行**（每店一套 cookie，各自限流互不影响）。

## 限流实测复盘（2026-10-30 踩坑记录）

**症状**：180 个词采了 325 次请求才拿到 134 个（空包率 **58%**），第 2 轮 78 次请求又 40% 空包。

**对照实验**（同一天，同一会话，同一批已知有数据的词）：

| 方式 | 首发命中 | 空包率 | 净吞吐 |
|---|---|---|---|
| 串行，无间隔 | 20/20 | **0%** | 8.9 词/分钟 |
| 并发 4 | 20/20（10 个空包） | 50% | 44 词/分钟（虚） |
| 并发 3 + 停顿补采 | 10/20 | 50% | 12 词/分钟 |
| 并发 6 + 停顿补采 | 7/20 | 65% | 11.4 词/分钟 |
| **并发 2（填充任务实跑）** | — | **58%** | **9.8 词/分钟** |

**结论：并发 2 相比串行只快 10%（9.8 vs 8.9 词/分钟），代价是 189 次废票请求。
并发完全不提速，还把会话打进限流。**

推测机制：explainer 限的是**同时在飞的请求数**，不是单纯速率。串行时延迟 2-14s 都不会空；
并发一旦 ≥2，只要有重叠就立刻返回空包——且空包响应只要 0.2-0.9s（服务端主动甩掉，不组装数据）。
所以「并发 + 停顿重试」在效果上等于「用废票把窗口灌满，再等它恢复」。

**三个叠加原因**：

1. **并发 > 1**（主因）。空包请求同样计入配额，重试反而延长限流。
2. **累计量**。整个会话 75 分钟内打了约 700 次请求（含并发实验、探活、p6 批量），
   是渐进恶化的：实验 A 20/20 → 实验 B 掉一半 → 实验 C 全空。
3. **双接口同一会话**。p6 `what_to_sell` 批量 111 次请求 / 60 秒（并发 4，约 1.9 req/s）
   直接吐出 **5 个 401/403** —— 这是硬信号，说明 p6 与 p8 共用同一份配额。

**已改**：
- `collect_seller_p8.py` 默认 `--concurrency 1 --min-delay 1.2`，并加首发哨兵：
  前 10 词空包 ≥40% 自动降级串行。
- `collect_seller_p6.py` 默认 `--concurrency 3`，连续 3 次 401/403 立即停止。

**下次按这个跑**：p8 串行 1.2s 间隔（≈40 词/分钟上限，实测 8.9），
p6 每批 50 个 × 并发 3，两批之间停 2s；两个接口不要同时打。

## 限流形态（关键，别搞错）

p8 撞限流的表现是**静默空包**，不是报错：

```
HTTP 200  ← 依然 200
body      ← {"status":"COMPLETED","items":[]}
延迟      ← 反而变快（1.5s → 230ms，因为不组装数据）
```

唯一可靠信号是 `items.length == 0`。所以必须用**对照词**（`сквиш` / `антистресс`，永远有数据）区分：

| 现象 | 判定 | 输出行 |
|---|---|---|
| 对照词有数，该词空 | 真实无数据 | `{"n":0,"no_data":true}` |
| 对照词也空 | 会话被限流 | `{"n":0,"throttled":true}` ← **不是 no_data** |
| 401/403/307 或返回 HTML | cookie / uuid 失效 | 不写行，退出码 2 |
| 连接异常 | 网络 | 不写行 |

`throttled` 和 `no_data` 必须分开写：混在一起会让下游把限流误判成「该词无数据」污染库
（老管线在这上面把覆盖率从 19% 拉到 61% 才纠回来）。采集器断点续跑只认 `n>0`，
所以 `throttled` 行下次会被自动重试，实测 3/3 补回。

实测「并发 6 首发 → 命中率掉到 35% → 停顿 30s 串行补 → 补回 13/13」，
所以采集器做成**两段式**：先并发抢，空包攒起来统一停顿，再验对照词 → 串行补。
还有第三段：本轮补不回来的写 `throttled`，改次跑自动续。

## cookie 寿命（为什么要"自动刷新"其实几乎不用）

| cookie | 域 | TTL | 说明 |
|---|---|---|---|
| `__Secure-token` | `.seller.ozon.ru` | **8760h（1年）** | 登录态主令牌，HttpOnly |
| `__Secure-product-user-id` | `.seller.ozon.ru` | 8760h | HttpOnly |
| `abt_data` | `.ozon.ru` | ~8760h | 反爬挑战凭据，HttpOnly，**必须带** |
| `sc_company_id` | `.seller.ozon.ru` | session | 店铺 ID，关浏览器就没 |
| `guest` | `.ozon.ru` | 9.5h | 匿名标识 |

`document.cookie` 拿不到 HttpOnly 的，所以 mint 必须走 CDP `Network.getAllCookies`。
UA 与 token 绑定，`cookie.ua` sidecar 必须跟着 cookie 一起用，否则 307。

---

## 文件

| 文件 | 作用 |
|---|---|
| `ozon_seller/api.py` | `SellerClient` / `Jar` / `Pacer`；失败三分类；空包判定 |
| `scripts/mint_seller_cookie.mjs` | ego-browser 签发 cookie jar + uuid（约 25s） |
| `scripts/check_seller_cookie.py` | 探活，退出码 0可用/2失效/3限流/4网络 |
| `scripts/refresh_seller_cookie.sh` | 探活 → 失效才 mint → 复验 |
| `scripts/collect_seller_p8.py` | p8 搜索位采集，输出与 `p8-items.jsonl` 同构 |
| `scripts/collect_seller_p6.py` | p6 销量采集，榜单翻页 / SKU 清单两种模式 |

产物落在 `~/.config/ozon-seller/`：`cookie.txt` / `cookie.ua` / `meta.json`（含 company_id、uuid）。

## 用法

```bash
cd ~/work/ozon-agent

# 0. 签发（一台有 ego-browser + 卖家已登录的机器，约 25s）
ego-browser nodejs <<'X'
await import('file:///Users/a1234/work/ozon-agent/scripts/mint_seller_cookie.mjs');
X

# 1. 探活
python3 scripts/check_seller_cookie.py

# 2. p8：词表 → 搜索位
python3 scripts/collect_seller_p8.py --words-file data/words.txt --out data/p8-local.jsonl
python3 scripts/collect_seller_p8.py --words "сквиш,антистресс,мялка" --concurrency 3

# 3. p6：SKU 清单 → 销量（chunk 50 一批）
python3 scripts/collect_seller_p6.py --skus-file /tmp/skus100.txt --concurrency 5
python3 scripts/collect_seller_p6.py --top 2000        # 或按 GMV 榜取前 N

# 4. 失效时刷新
bash scripts/refresh_seller_cookie.sh            # 只在真失效时 mint
bash scripts/refresh_seller_cookie.sh --force    # 强制重签
```

## 与 antistress 管线的对接

输出格式是**故意对齐**老管线产物的，下游不用改：

```
p8  → {"kw": ..., "n": 108, "headers": [...], "items": [...]}   == p8-items.jsonl 行
p6  → 66 字段（历史 67 个，只少 eventsCount）                    == p6-enriched-final2.json 元素
```

实测对账（2026-10-30）：
- p6 清单模式 100/100 命中，`rating` / `volume` / `category3` 100% 一致；
  `soldCount` 54% 一致、`avgPrice` 45% 一致 —— 差额是 12 小时真实漂移（如 sold 14→15），不是解析错误。
- p8 结构与 headers 100% 一致；同一店铺下 `мялка` / `нидл антистресс` 三次调用前 10 位完全稳定，
  热词 `сквиш` 有 1-2 位抖动 —— 源站本身的波动，不是采集器问题。

## 多店铺并行

每店铺独立目录 + 独立限流，互不干扰：

```bash
python3 scripts/mint_seller_cookie.mjs   # 在浏览器切到目标店铺后重跑，或
cp -r ~/.config/ozon-seller ~/.config/ozon-seller-ozon2   # 存下不同店铺的 jar
```

`SellerClient(cookie_file=Path.home()/'.config/ozon-seller-ozon2/cookie.txt')` 指定即可。

## 额外打通：searchteam 月度词库（原来以为只能页内 fetch）

旧笔记记的「searchteam 在 api 域 nginx 404，直连吃 403 fab_chlg，只能页内 fetch」**也不成立**。
带正确 cookie jar 直接打：

```
POST /api/site/searchteam/Stats/queries/search/by_month
{"month":"2026-09-01T00:00:00.000Z","limit":10,"offset":0}
→ 200，返回 1,046,842 次搜索的「сумка женская」等真实词表
```

这就是 `keyword_p7`（9,979 词）的源，现在也能纯 HTTP 采。注意 `limit` 必须是 0-50（超了报
`limit must be between 0 and 50`，不是 403）。

仍未打通：`/api/search-query-analytics/v1/cjm/get-seller-analytics` → 403
`Failed to get body company ID`，body 里塞 `sellerId`/`companyId` 都不行，需要从真实页面请求中截一次 body 形状。

---

## cjm `get-seller-analytics` 是什么（已打通）

**页面**：分析 → 搜索可见性 → **我的商品**（`/app/analytics-search/search-results/my-products`）

**含义**：CJM = Customer Journey Map。它回答的是「在所选时段里，**本店每个 SKU** 在搜索这条链路上走到哪一步了」——搜过 → 看到 → 点卡片 → 下单 → 成交额。

与 `explainer` 的区别：

| | explainer (p8) | cjm (my-products) |
|---|---|---|
| 粒度 | 某个**搜索词**下的 108 个位置 | 本店**每个 SKU** 的整体表现 |
| 面向 | 竞品 + 自己 | **只自己** |
| 用途 | 看某个词的市场格局 | 看自己商品流量卡在哪一步 |

**请求**（body 键必须是蛇形 `seller_id`，写 `sellerId`/`companyId` 一律 403 `Failed to get body company ID`）：

```json
POST /api/search-query-analytics/v1/cjm/get-seller-analytics
{"seller_id":"<seller_id>",
 "period_from":"2026-09-30T16:00:00.000Z","period_to":"2026-10-28T15:59:59.999Z",
 "count_total_items":true,"page_number":"0","items_per_page":"500",
 "sort_by":"METRICS_TYPE_UNIQUE_VIEW_USERS","sort_direction":"DESCENDING",
 "filters":{"categories":[],"search":""}}
```

**返回** `{skus[], totalNumberOfItems, totalPagesCount}`，每个 SKU 这些字段：

| 字段 | 中文表头 | 含义 |
|---|---|---|
| `uniqueSearchUsers` | 多少位买家曾搜索 | 查询结果含该商品的去重用户数（不管看没看到） |
| `uniqueViewUsers` | 多少位买家已看到 | 实际曝光的去重用户数 |
| `searchPosition` | 搜索结果中的位置 | 平均展示排名（不含筛选/排序/推荐货架） |
| `queryCtrInteract` | 搜索到卡片的转化率 | 卡片访问量 ÷ 搜索展示量 |
| `queryCtrOrder` | 搜索到订单的转化率 | 订单量 ÷ 搜索展示量 |
| `uniqueOrdersCount` | 订购商品件数 | 含取消/退货 |
| `gmv` | 订购金额 | 按搜索查询统计 |
| `visibility` | 搜索可见性 | 70% + 高/中/低 |
| `sku` / `name` / `article` / `pictureUrl` / `sellStatus` / `gmvCurrency` / `badges` | — | 商品基础信息 |

每个指标都是 `{value, delta, deltaColor, unit}`：**value 是本地化字符串**（`"372 152"` / `"7,52%"` / `"22 026 ₽"`），随 `x-o3-language` 变，必须 parse。`delta` 是与上一周期的变化幅度。

列定义可以拉：`GET /api/search-query-analytics/v1/cjm/get-seller-analytics-table-headers?seller_id=<id>` → 8 列带 `metricType` 和提示文案。

```python
from ozon_seller import SellerClient
c = SellerClient()
rows = c.my_products("2026-09-30T16:00:00.000Z", "2026-10-28T15:59:59.999Z")["skus"]
```

实测：店铺 <seller_id> 返回 31 个 SKU，1,974ms。

---

## 注意事项

1. **p6 有域名级封禁史**：历史上 945 请求 / 7 分钟后整域 403，冷却 30-60 分钟。采集器内置
   「连续 20 批空包 → 暂停 120s」哨兵，别把并发调到 10+。
2. **`uuid` 是搜索会话级的**：失效后所有 p8 空包，重 mint 会同时换新 uuid。
3. **别用 `document.cookie` 抄 cookie**：HttpOnly 全丢，抄出来的 jar 必然 403。

---

## 手动导入浏览器导出的 cookie（不依赖 ego）

可以直接用 Cookie 导出 JSON，但**必须包含 `abt_data`**，否则一律 `403 fab_chlg`（跳 challenge.html）。

实测对照：
| jar 内容 | 结果 |
|---|---|
| 只要登录态（`__Secure-token` / `sc_company_id` / `__Secure-access-token` …） | **403** `{"incidentId":"fab_chlg_...","challengeURL":".../challenge.html"}` |
| 补上 `abt_data`（928-990 字符） | **200** |

要点：
- `abt_data` 是反爬令牌，跟 **IP + UA** 绑定，**不跟账号绑定** → 同机同 UA 下可跨会话复用
- 很多导出插件默认跳过 HttpOnly，导出时必须勾上，否则拿不到 `abt_data` / `__Secure-token`
- `sc_company_id` 决定操作哪个店铺，请求头 `x-o3-company-id` 必须跟它一致
- p8 的 `uuid` 是搜索会话令牌，**可跨店铺复用**（实测旧 uuid 换店铺后仍返回 108 条）；缺 uuid 会 400 `Location: value is required`

导入后自检：
```bash
python3 scripts/check_seller_cookie.py     # 0=可用 2=鉴权失效 3=限流 4=网络
```
4. **UA 必须成对**：`cookie.ua` 丢了就用默认 UA，会 307。
