# 上游源码审计（2026-11-09）

## 范围与证据

- 目标仓库：`3338682145/ozon-seller-kit`；审计基线 `main@6604487a91fe6aad095614c34469b7e024544a6b`。
- 通过 GitHub 文件接口检查了 `ozon_seller/`、`ozon_buyer/`、`scripts/`、`docs/`、`project/ozon-market-intelligence/` 的文件清单、关键函数、请求构造、分页与失败路径；核对 `data/toys-slim.db` 的 Git 文件元数据和既有审计报告。
- 本次环境无法解析 github.com 以运行本地 clone；未直接运行旧 SQLite 的 PRAGMA，也没有合法的实时 Ozon 授权会话。源码静态证据、历史报告与当次测试结果须明确区分。

## 按模块核对

| 位置 | 源码已实现内容 | 分页 / 输出 | 风险与复用边界 |
|---|---|---|---|
| `ozon_seller/api.py` | `what_to_sell` P6、`explainer` P8、`my_products` CJM、`cjm_table_headers` | P6 offset/limit，P8 固定 pageNumber=1，CJM 返回 totalPagesCount；JSON | 同步 urllib；旧 `post` 有重定向、Set-Cookie 吸收及重试，新的采集 Transport 不复用该行为 |
| `scripts/collect_seller_p6.py` | 榜单翻页与 SKU 清单分块，线程池 | 默认 50/页；JSON 数组 | 失败存在空结果歧义；频率要交给源策略 |
| `scripts/collect_seller_p8.py` | 关键词逐次调用，空包探测与本地 checkpoint | 每词最多 108 项，JSONL | 旧空包、限流标记不可当作真实无数据 |
| Seller P7 | 未在当前仓库发现独立调用函数或脚本 | 历史 P7 数据表/SQL | **未实现**，禁止虚构接口 |
| `ozon_buyer/api.py` | search、category、sku_detail、sku_reviews、other_offers | 搜索/类目页数、PDP1/PDP2、评论与跟卖 | 原入口可能触发自动 Cookie 预热，不能纳入新 Runtime |
| `ozon_buyer/collector.py` | search tile、seller info、reviews/offers 解析 | `sku_id`、title、price、rating、reviews_count、stock_max、is_advert 等 | 旧 CDP 预热/导出 Cookie 必须隔离 |
| `ozon_buyer/detail.py`、`browser.py` | PDP1/PDP2、变体、评价、offer、tile 的纯解析函数 | Widget JSON / 派生结构 | 只复用纯解析；禁用旧 BrowserSession 挑战处理与站点写操作 |
| `ozon_buyer/http.py`、`pool.py`、`pool_client.py` | 并发 HTTP、Cookie 池与 403 补池 | JSON | 不进入新采集执行路径 |
| `ozon_buyer/image.py` | 以图搜图及上传 | 商品图片搜索 | 另列缺口，未确认授权不启用 |
| `ozon_buyer/cookie_reader.py`、`scripts/*cookie*` | 本地浏览器 Cookie 读取、自动续签、保活 | 本地凭证文件 | 新 Credential Service 不采集或保存反爬令牌 |
| `scripts/build_data_audit_html.py`、`project/.../scripts/rebuild_market_scale.py` | SQLite 读取、历史报表与计算 | HTML、旧数据集 | 公式需验证后独立迁移，不能把历史输出当本次结果 |

## 现有限流、错误与并发行为

`SellerClient.post` 默认 `retries=2`；对部分 3xx 吸收 `Set-Cookie` 后重试，对 401/403/HTML 挑战抛出授权错误。新 Runtime 对 3xx、401、403、挑战页及凭证吊销一律中止当前源，不自动换代理/身份或刷新挑战令牌。P6 脚本默认 3 线程，P8 默认 1 线程及 1.2 秒最小间隔；Buyer 旧代码有更高并发。这些只是源码/历史配置，**不代表许可上限或生产吞吐**。

Seller 使用登录 Cookie、公司 ID、部分端点要求 uuid；Buyer 旧流程包含本地缓存、浏览器预热及 TLS 模拟。新的授权凭证必须在任务隔离的 Secret Service 中取得，日志和业务库不得保存明文。

## SQLite 资产与可核验程度

Git tree 存在 `data/toys-slim.db`（19,861,504 bytes）。上游 2026-11-02 审计报告列出 `kw_metrics` 1,642、`kw_positions` 177,063、`sku` 29,823、`clusters` 165、`sku_weekly` 4,350 行；其 `integrity_check=ok` 属**历史报告转述**，本次未直接复核。入库迁移前必须只读执行 `PRAGMA integrity_check`、`table_info`、键唯一性及快照关联对账。

**独立 TEST Agent Round 1 补充证据**：机器 B [Issue #2](https://github.com/3338682145/ozon-seller-kit/issues/2) 报告已在只读环境执行 `PRAGMA integrity_check=ok`、逐表 COUNT 与上述五表行数一致；这是机器 B 的执行反馈，机器 A 并未重复运行原始 SQLite，`table_info`、唯一性、关联及权限仍需分别验收。

**公开分发风险**：该仓库目前为 public，`data/toys-slim.db` 已被 Git 跟踪，包含 SKU、卖家与市场统计数据；对其公开分发的授权尚未确认。禁止把文件存在于仓库等同于可合法再分发；应先核验权利与必要脱敏，再经所有者决定是否改为私有、移除跟踪文件及清理历史。修改 `.gitignore` 无法撤回既有历史，此 PR 不执行破坏性删除。对应 `GAP-015`。

## 历史 README 与解析代码冲突（需弃用旧断言）

`README.md` 与 `ozon_buyer/README.md` 把 `stock_max` / 购物车 `maxItems` 宣称为“100%真实物理库存”；**此断言没有库存实盘或仓储对账证据，不能作为数据契约**。以 `field-dictionary.md` 中“最多可购数代理值 ≠ 真实物理库存”为准。

此外，`ozon_buyer/collector.py` 将 `trackingInfo.click.custom.advertLite` 通过 `bool(...)` 转换：旧解析会把缺失和 `false` 混淆；新 Adapter 必须保留 nullable 语义，不可直接复制此行为。

## 未验证边界

没有对 README 的性能数字作生产结论。尚未执行合法真实 Ozon 请求、全仓动态执行、真实 Docker 中间件/生产恢复演练。需在授权和许可范围明确后逐项验收。
