# Buyer 库存 / 评论 源矩阵（Source-of-Truth Matrix）

> 依据：spec §9（冲突裁决）、§10.3（字段契约）、plan Task 1。
> 状态口径：`observed`（Kit 源码实测路径）/ `estimated`（基线待 12h 复核）/ `unknown`（本会话未取到真实响应）。
> 本会话在线被 antibot 阻断（见 `docs/benchmark/evidence/t0-cookie-supply-smoke.md`），**未取到任何真实库存/评论响应**；fixture 为按 Kit widget 结构构造的脱敏样本，provenance 已在文件内标注。

## 1. 库存源

| 项 | Kit 事实（observed） |
|---|---|
| 解析函数 | `ozon_buyer/collector.py:extract_skus_from_page`；`ozon_buyer/http.py:parse_tile` |
| 请求页型 | 搜索/类目页经 entrypoint-api：`GET /api/entrypoint-api.bx/page/json/v2?url=<path>`，返回 `widgetStates`，键含 `searchResultsV2*` / `tileGrid*` |
| SKU 路径 | `it.sku` 或 `it.action.link` 正则 `/product/...(\d{6,14})` |
| `stock_proxy_max_items` | `multiButton.ozonButton.addToCart.quantityButton.maxItems`，fallback `ozonButton.quantityButton` / `multiButton.quantityButton` / `mainState[type=quantityButton].maxItems` |
| `stock_text_remaining` | tile `mainState[type=textDS].text` 俄文 "N ед осталось" / "Осталось N шт."（Kit 现有 `http.py` 只认中文 "仅剩"，V2 合同层补俄文解析） |
| 封顶语义 | maxItems ≥ 2000 被平台夹到 2000；此时两字段并列保留、`is_capped=true`；**不得**合并成单字段、**不得**命名 `physical_stock` |
| 0 vs NULL | max_items=0 是真实观测（售罄）；字段缺失/widget 漂移是 NULL，两者不可混淆，不得把未观测写成 0 |

## 2. 评论源

| 项 | Kit 事实（observed） |
|---|---|
| 解析函数 | `ozon_buyer/detail.py:parse_reviews` |
| 请求页型 | `/product/{sku}/reviews/?reviewsVariantMode=2&sort=...&page=N` 经 entrypoint-api |
| 评分聚合 | widget `webReviewProductScore.totalScore` / `reviewsCount` |
| 列表 | widget `webListReviews`：`reviews[].content.score`、`uuid`、`author.firstName/lastName`、`publishedAt`、`usefulness.useful` |
| score 范围 | 存在时必须整数 1–5；越界隔离为 invalid，不计入 valid_count |
| review_id | 取 `uuid`；缺失即 NULL，**不得**用 author+comment 伪造去重键 |
| 正文/图片 | 默认不存；留存需单独授权（spec §10.1） |

## 3. 限速 / 预算证据

| 参数 | 值 | 口径 |
|---|---|---|
| 预热 | 4.0s / 9 条 cookie（含 abt_data） | 基线，**estimated**，本会话未复现 |
| 单 cookie 额度 | ~30 次后开始 403 | 基线，**estimated**，12h 实验重测 |
| 并发 | 20 并发 40 请求 10.7s 全成功 | 基线，**estimated** |
| HTTP 通道吞吐 | 4.6 页/秒 | 基线，**estimated** |
| 浏览器通道吞吐 | 2.3 页/秒，加并发不提速 | 基线，**estimated** |
| 403 冷却 | ~100s | 基线，**estimated** |
| 单页 SKU | 36（默认排序仅 8 tile） | 基线，**observed in code comments** |
| 内存 | PSS ≈500MB（RSS 不可用） | 基线，**estimated** |

> 这些数字在 12h 实验结束前一律标 `estimated`，不是许可上限。`ozon-crawler-local` 的限速/库存含义/端点一律不采信、不 fallback。

## 4. 冲突与裁决

| 冲突 | 裁决 |
|---|---|
| `stock_max` 是"物理库存"还是"可购上限代理" | 以 Kit `docs/field-dictionary.md` 为准：**购物车可购上限代理**，不是核实过的实物库存；不据此算销量差分 |
| 库存页型：SKU-only PDP 是否含列表页 stock | **禁止假设** `/product/{sku}/` PDP 含列表页 maxItems；库存粒度是「页面上下文 × 观测到的 SKU」 |
| 限速来源 | 仅 Kit 实测基线；不采用 crawler-local 常数 |
| 3xx 跳转 | 搜索页 302/307 是正常跳转（`page_changed=true`），跟随，**不计**拒绝 |
| 401/403/429/挑战 | 熔断**该票据**，从池里取下一枚；连续 3 枚被拒才停源；不换代理/账号、不对同一枚重试 |

## 5. 测试样本（fixture）

| 文件 | SHA256 | 轮廓 | provenance |
|---|---|---|---|
| `samples/benchmark/buyer_inventory_page.json` | `90c8187d9c99476d7504702859c6ac3bc20c594ee159c65b25dbfa973fb73b23` | ① 常规(maxItems≈文案一致) ② 爆款(maxItems=2000, 文案 3359) ③ 缺 maxItems 卡 | 本会话未取到真实封顶样本；按 Kit widget 结构构造，文件内 `_provenance` 已标注。待出口恢复后用获准脱敏 golden 替换 |
| `samples/benchmark/buyer_reviews_widget.json` | `6769155955e5dad9baf996532ec069a0c4fc393bed1beeef0748b2de60d5b31d` | 2 条有效 + 1 条 score=9 越界 | 同上，构造样本 |

> 「未取到真实封顶样本」如实记录：本会话 antibot 阻断，连常规页都未取到；封顶用例以真实 tile 结构 + 构造 maxItems=2000 数值表示，来源标注为构造，不冒充实测。

## 6. 二级参考

- `ozon-crawler-local/docs/api/C01-buyer-entrypoint-widget.md` —— **仅作 widget 命名二级参考**；其限速、库存含义、请求端点不进入任何在线参数。
