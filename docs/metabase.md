# Ozon Metabase 商品筛选及数据分析面板

## 目标与默认条件

- 商品筛选关键词：`антистресс`（俄语**包含**搜索，大小写不敏感）
- 最高价格：`500 RUB`（**PostgreSQL 商品主档当前挂牌价**，不是历史价格或真实成交价）
- 搜索排名：`1–30`（每个关键词**最新观测日期**，并非今天或全站准确排名）
- 排序：**已验证的关键词机会评分**从高到低，缺失评分排最后，同分按搜索位、价格和 SKU。
- 展示：商品结果、当前命中统计、关键词机会榜、ClickHouse 历史搜索位/价格趋势。

⚠️ `gold-analytics-v1` 的 `entry_score(max_slot30, new_top10_share)` 是**关键词级**而非 SKU 级。`products` / `keyword_product_relations` 无法验证“过去 60 天新品占 Top10 的比例”；所以默认 `keyword_opportunity_score = NULL`，缺失表示**待计算**，而不是 0 分。不能凭搜索排名/价格编造机会分。要显示真实机会评分，数据工程模块必须在独立的 `analytics.keyword_opportunity_inputs` 写入经过许可验证的 Seller ID、Top10 新品占比、证据引用以及 `verified_at`；所有输入对应排名同一观测日期。**不要使用旧 P8 keyword popularity 冒充真实销量**。

## 与现有系统的关系

- `Crawlab`：采集批次管理，可选服务 `localhost:8080`。
- `Grafana`：采集监控，可选服务 `localhost:3000`。
- **`Metabase`**：商品筛选与 BI，**`http://localhost:3001`**；不公开到公网。
- `PostgreSQL`：`products` + `keywords` + `keyword_product_relations`；独立 schema `analytics` 中创建 `v_product_keyword_filter`。
- `ClickHouse`：`default.fact_keyword_sku_daily` 和 `fact_price_history`，通过只读、受控列的 `analytics` 视图展示历史；**不在 Metabase 内跨数据库 JOIN**。
- Metabase 的**应用元数据库**单独建在同一 PG 实例的 `metabase_app` 数据库，登录用户独立；不可与业务表混用。

## A. 一次性部署（从仓库根目录运行）

前提：Docker Engine + Compose，先合并前序 collector PR，并且原有 `.env` 已配置可运行。**该方案沿用 24.8 ClickHouse、16 PostgreSQL，Metabase 固定镜像 `v0.64.1`。**

```bash
cp .env.metabase.example .env.metabase
# 编辑 .env.metabase：替换所有 CHANGE_ME，至少 3 个不重复强密码。
# 用安全随机工具生成 MB_ENCRYPTION_SECRET_KEY，例如 openssl rand -hex 32
# 先启动已有 API 以完成 Alembic migrations（本命令包含其依赖）
docker compose --env-file .env --env-file .env.metabase \
  -f docker-compose.yml -f docker-compose.metabase.yml \
  --profile analytics up -d metabase
```

上述启动会创建：业务 PG 只读分析视图及只读账户、隔离的 Metabase 应用数据库、ClickHouse 只读历史视图与只读账户、Metabase Web 服务。重复执行不会重新初始化业务表，也不往商品表写数据。

> **权限**：Metabase Reader 仅有 `GRANT SELECT` 到 `analytics.v_product_keyword_filter` 和 ClickHouse 两张指定视图；无访问 Cookie/Agent 决策/日志/明文原始 JSON 的权限。PostgreSQL 还设置了 `default_transaction_read_only` 与 SQL 超时。Metabase 管理员仍能管理它自己的应用配置，因此生产要单独设置用户、团队与集合权限、TLS 和 VPN。禁止把 `POSTGRES_PASSWORD`、`CLICKHOUSE_PASSWORD` 等写进 Dashboard SQL。

## B. 初始化 Dashboard（一次管理员操作，其后可重复运行）

1. 浏览器打开 `http://localhost:3001`，完成 Metabase 初始管理员设置（不是 Ozon 账号）。
2. 在 Metabase 管理后台创建一个有权限管理数据源/仪表盘的 API Key；暂时放入当前终端的环境变量（**不要写 Git**）。
3. 在仓库目录执行：

```bash
# 查看即将创建的分析卡片与默认筛选（离线校验，不需要凭证）
python scripts/metabase/bootstrap_dashboard.py --dry-run

# 将配置导入当前终端（前提是 .env 与 .env.metabase 是合法 shell 变量语法）
set -a
. ./.env
. ./.env.metabase
set +a
export METABASE_URL=http://localhost:3001
export METABASE_API_KEY='<从管理后台复制的 API Key>'
python scripts/metabase/bootstrap_dashboard.py
unset METABASE_API_KEY
```

脚本将自动添加两个只读数据库、一个中文集合、5 个问题和一个 Dashboard；默认参数为 `антистресс / 500 / 30`，3 个筛选器对 5 张卡片同时生效。再次运行会匹配同名对象并更新卡片，保留用户手动添加的其它 Dashboard 卡片。**务必检查 UI 中每张卡片的筛选器连接已正确显示**；Metabase API 细节可能随版本更新。首次没有数据时，图表空白是正常的。

### 视图与卡片清单

| 数据源 | 只读视图 | 用途 |
|---|---|---|
| PostgreSQL | `analytics.v_product_keyword_filter` | 最近一次关键词 SERP × SKU、主档价格、已验证机会分 |
| ClickHouse | `analytics.v_serp_observations` | 关键词历史 SERP 搜索位、广告位、挂牌价 |
| ClickHouse | `analytics.v_price_history` | 独立 SKU 历史挂牌价，供后续深挖（此次 Dashboard 未直接用） |

5 个 Dashboard 卡片：**商品机会筛选表**、**当前结果概览**、**关键词机会评分**、**每日关键词搜索位覆盖**、**每日搜索位挂牌价格**。SQL 在 `sql/metabase/cards/`，都是只读 SELECT；任何计算结果应保留 `dataset_version/algorithm_version`。价格趋势来自历史 SERP 对应观测价格，**不是**所有商品的完整成交历史。

## C. 机会评分计算输入（仅 ETL/管理员写入）

`analytics.keyword_opportunity_inputs` 包含 `keyword_id`、`as_of_date`、`max_slot30`、`new_top10_share`、`observed_top10_count`、`source`、`dataset_version`、`evidence_ref`、`verified`、`verified_at`。

仅在确认 seller_id、Top10 上架日期、新品定义以及授权来源之后由受控 ETL 写入 `verified=true`。算法（与仓库 `collector/pipeline/analytics.py::entry_score` 一致）：

```text
KeywordOpportunityScore = 100 × [0.60 × (1 − min(max_slot30/10, 1))
                              + 0.40 × min(new_top10_share/0.40, 1)]
```

在最新关键词排名观测日期与评分的 `as_of_date` **精确相同**时才关联；没有可核验的数据就不计算。`new_top10_share` 是 0–1 的比率；不得把 NULL 当 0。该结果**不能理解为单个 SKU 的盈利性或真实销售机会**。未来如需 SKU 评分，需要另建商品级算法、版本、验收用例，不能沿用关键词评分名称。

## D. 日常使用（不需要 SQL）

进入 Metabase → `Ozon 商品分析（只读）` → `Ozon · 商品筛选与关键词机会（演示配置）`：调整顶部的关键词、最高价格和排名前 N，点击应用，按关键词机会分和排名查看结果；可以从卡片菜单导出 CSV/XLSX。这里只做 BI 查询和简单计算，采集和历史重算仍走原有 FastAPI / Gold pipeline。

## E. 安全、限制与验收

- 不要为分析师提供业务数据库管理员凭证；不要允许 Metabase 上传/写入业务库。对于租户隔离和 PII 要求，需要另行建立授权范围与行级权限，本 PR 不宣称已具备多租户隔离。
- ClickHouse `ReplacingMergeTree` 的 `FINAL` 读取保证多次批量导入的替换语义，但历史大表可能慢；生产应按真实数据规模增加物化分析层，并压测后决定保留周期。
- PostgreSQL 中 latest 关键词观测日期取 MAX(observed_date)，同一日期不同来源冲突时按 `source/position/id` 确定性选择；这是展示优先规则，不代表来源可靠性排序。
- 默认不导入 Mock 记录，也不会访问 Ozon 前台；需要在授权可留存的数据进入原有采集系统后才有真实结果。
- 目前已完成：Python 静态/逻辑测试、初始化脚本离线演练、SQL 与上游 ORM 字段核对。**本交付运行环境没有 Docker/PG/CH/Metabase 容器**，真实数据库初始化、驱动兼容、权限拒绝测试、Dashboard 参数映射的线上联调仍待部署验证。
- 生产验证命令：`docker compose ... config`、`docker compose ... up -d metabase`、独立只读账号执行 SELECT 成功 / INSERT 和读取 raw 表失败、Metabase `/api/health`、5 张卡片过滤联动与可视化效果。

参考：<https://www.metabase.com/docs/latest/installation-and-operation/running-metabase-on-docker>、<https://www.metabase.com/learn/metabase-basics/administration/administration-and-operation/metabase-api>、<https://www.metabase.com/docs/latest/databases/connections/clickhouse>。

## 回滚

可删除本 Dashboard 与两个 Metabase 数据源连接、关闭 Metabase 容器，独立的应用数据库和卷保留用于恢复（不要直接删除生产数据）。如需清除本新增的分析视图或评分输入表，请走 DBA 审批，不执行自动 DROP。`docker compose` 关闭容器不会改动原商品主档与历史事实表。
