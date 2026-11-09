# 上游源码审计（2026-11-09）

## 证据与范围

- 仓库：`3338682145/ozon-seller-kit`；GitHub API `main` tree SHA `6604487a91fe6aad095614c34469b7e024544a6b`，`truncated=false`，共 89 个树节点。
- 审计方式：经已连接 GitHub 文件 API 阅读 `ozon_seller/api.py`、`ozon_buyer/api.py`、`collector.py`、`browser.py`、`detail.py`、`http.py`、`pool.py`、`pool_client.py`、`scripts/collect_seller_p6.py`、`collect_seller_p8.py`、`collect_buyer.py`，并核对文档及项目 SQL。运行容器无法解析 github.com，未能执行 `git clone`；仓库内 19.9 MB SQLite 二进制文件也未能直接读库；本次不声称完成本地全量/动态审计。
- 上游文件链接：`https://github.com/3338682145/ozon-seller-kit/tree/main`；在有网络的 CI/机器上按照 `docs/migration-plan.md` 补做全量静态审计和数据库 `PRAGMA` 核验。

## 关键发现（源码证据，而非 README 性能声明）

| 模块 | 已实现调用 / 行为 | 输出 | 生产风险 / 处理 |
|---|---|---|---|
| `ozon_seller/api.py` | `SellerClient.what_to_sell(skus,offset,limit,period)`：P6 POST；`explainer(keyword)`：P8 POST；`my_products(period_from,period_to,...)`：CJM POST；`cjm_table_headers()` GET | P6 `items[]`，P8 `{kw,n,headers,items}`，CJM `{skus,totalNumberOfItems,totalPagesCount}` | 同步 urllib + thread lock；`post` 自动重试和 HTTP 307 吸收 Set-Cookie。保留数据提取方式，改由新 Safe Transport 禁止重定向/挑战/凭证自动刷新。|
| `scripts/collect_seller_p6.py` | 榜单 offset 50；SKU 清单分块；线程池 | `data/p6-local.json` 数组 | `--chunk` 无硬检查，脚本内硬编码超时/间隔；失败可返回空集合但未区分完整性。|
| `scripts/collect_seller_p8.py` | 关键词单次 `itemsPerPage=108,pageNumber=1`，本地 checkpoint | JSONL，每行关键词含 headers/items；限流时 `{throttled:true}` | README/脚本实测是样本，不证明稳定许可；空包不能作为真实 0；任务迁入中心调度。|
| Seller P7 | 未发现仓库中的采集函数、端点或执行脚本；已有 P7 表和文档为历史数据 | `keyword_p7` 在旧报告中已存在 | 不能把有表等同已有接口；标记 `unimplemented`，只提供 Mock/授权导入通道。|
| `ozon_buyer/api.py` | BuyerClient `search` / `category` / `sku_detail` / `sku_reviews` / `other_offers` | 搜索 tiles；详情 PDP1/PDP2；评价、跟卖 | 依赖 curl_cffi、外部 cookie 缓存；原 `ensure_creds` 静默预热，不引入运行路径。|
| `ozon_buyer/collector.py` | `request_entrypoint_page`, `extract_skus_from_page`, `fetch_sku_reviews`, `fetch_sku_other_offers` | `sku_id,title,price,original_price,discount_pct,rating,reviews_count,stock_max,is_advert` 等 | 原有 `cdp_warmup` 提取挑战页 Cookie，不允许由新运行时调用。|
| `ozon_buyer/detail.py` | `parse_pdp1`, `parse_pdp2`, `parse_reviews`；商品属性/变体解析 | 产品、变体、卖家、评论；字段可能缺失 | 这些纯解析函数可重用；同步网络流程与 Cookie 自动预热须隔离。|
| `ozon_buyer/browser.py` | `tile_extract`, `offers_extract`, `pdp_extract`, `reviews_extract`；CDP 页面执行 | tile/offer/PDP/review 对象 | `BrowserSession.warm()` 通过 challenge、`fetch_action` 会执行站点动作；新 Runtime 不复用获取授权/动作步骤。|
| `ozon_buyer/http.py`、`pool*` | 纯 HTTP 及 Cookie 池、403 补池 | JSON 行 / 聚合 | 对 403 自动补池和 TLS 模拟可能构成访问限制绕过；新 Runtime **不导入这些模块**。|
| `scripts/*cookie*` | mint、renew、keepalive / CDP 自动获取 | 本地 Cookie 文件 | 凭证明文/自动轮换，必须隔离，不进入 Compose、Agent 或部署路径。|
| `project/ozon-market-intelligence/` | 多份方法论、旧 Supabase SQL、`scripts/rebuild_market_scale.py` | SQLite/Pandas 聚合、SQL 数据集 | 有价值的公式与语义可迁移；旧报告不是本次运行测试。|
| `data/toys-slim.db` | 大小 19,861,504 bytes（Git tree） | SQLite（旧报告五表） | 二进制无法本地读取；只记录旧报告信息，不能宣称亲自 `PRAGMA integrity_check`。|

## 既有并发/重试/授权

- Seller `post()` 默认 `retries=2`，代码对 301/302/307/308 重试并吸收 Set-Cookie；401/403/307 抛 `AuthExpired`，HTML 挑战页检测后抛 `AuthExpired`。新执行路径必须将任何 3xx/401/403/挑战直接封禁当前源，**零重试**。
- P6 脚本默认 3 线程；P8 脚本默认 1 线程并带 1.2 秒延迟、28 秒空包等待；Buyer 旧脚本有高并发、Cookie 池甚至 403 补池。这些数字只是仓库配置/历史试验，**不是许可速率或生产基准**。
- Seller 通过 `Jar.load` 加载本地 cookie.txt + meta.json/UA，`x-o3-company-id` 与 P8 uuid 等是店铺授权约束；新 CredentialResolver 只读 Secret，不写库或日志。
- Buyer 旧模块用 CDP、浏览器或 cache 提取 cookie；新工作流不能用其动态凭证获取步骤。Buyer 真采集默认关闭，允许输入经许可的页面原始快照以验证解析路径。

## 旧 SQLite 证据及待复核项

仓库 `project/ozon-market-intelligence/08-DATABASE-AUDIT-2026-11-02.md` 报告五表：`kw_metrics=1,642`、`kw_positions=177,063`、`sku=29,823`、`clusters=165`、`sku_weekly=4,350`；该报告声称历史 `PRAGMA integrity_check=ok`。这些数字是**上游报告转述，非本次二进制数据库验证**。字段缺口详见 `docs/data-gaps.md`。禁止把上游的 N SKU/s 作为验收性能结论。

## 本轮完成边界

本交付是**可叠加到上游代码的工程化 overlay**（保留上游文件）；可在网络恢复后 `git am` 逐阶段应用。Mock E2E 用本交付测试验证；未经有权真实数据与基础设施启动，不标记线上 Ozon、Crawlab 或 DSH 服务已验收。

## 补充代码审阅（同一 GitHub API commit/tree）

本轮又读取 `ozon_buyer/env.py`、`image.py`、`cookie_reader.py`，`scripts/check_seller_cookie.py`、`auto_renew_probe.py`、`keepalive_seller_cookie.py`、`mint_seller_cookie.mjs`、`auto_renew_seller_cookie.sh`、`refresh_seller_cookie.sh`、`build_data_audit_html.py`、`compare_seller_periods.py` 以及 `project/ozon-market-intelligence/scripts/rebuild_market_scale.py`，并扫描导出的 Python/JS 函数、HTTP 入口、Cookie/SQLite 依赖。进一步发现：

- `ozon_buyer/image.py` 实现独立的以图搜图通道，依赖上传和 Cookie 自动预热；它未在一期八个 Adapter 名单内，新增 `buyer_image` 缺口，**不得直接挂到合规 Runtime**。
- `ozon_buyer/cookie_reader.py` 通过 `browser_cookie3` 访问本地浏览器 Cookie 数据库并抽取凭证；新 Credential Service 不沿用这种导出与缓存行为。
- `ozon_buyer/env.py` 检测用户环境中的代理和浏览器路径；新 HTTPX Transport 使用 `trust_env=False`，不从环境变量隐式加载用于 Ozon 前台访问的代理。
- `scripts/auto_renew_probe.py`、`keepalive_seller_cookie.py`、`mint_seller_cookie.mjs` 依赖对 Seller token/HttpOnly Cookie 的读取、持续保活或本地输出；在新 Runtime 中不加载、不迁移凭证续签路径。
- `scripts/build_data_audit_html.py` 使用 `sqlite3.connect(DB)` 读取旧资产；`project/.../rebuild_market_scale.py` 以 SQLite 只读 URI 做聚合，这些计算需要逐个核对语义后迁入可重算 SQL/Polars，不应直接声称已迁移全部算法。
- 仓库还含若干安装/启动 shell 和旧 SQL 模板；它们不代表可用于生产的限额或授权。完整原仓动态执行、二进制 SQLite 逐表 `PRAGMA` 及网络服务验收仍待完成。

**与新实现的技术边界**：新增 `collector/` 代码不会导入上述 Cookie 抽取/自动续签模块。严格执行 Seller 许可/授权门槛，保留 Buyer 纯解析代码的可复用接口，仅支持获准的离线快照；不通过中国/香港代理绕过 403、挑战或访问限制。
