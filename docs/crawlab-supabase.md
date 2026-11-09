# Crawlab + Supabase + ClickHouse + MinIO 部署（Mock-first）

## 这套部署实际做什么

```text
Crawlab Web 8080 ──(批准的批次清单 / 执行时间)──> FastAPI 8000
   │                                     │
   └── MongoDB（仅 Crawlab 内部数据）      └── Supabase / collector_core
                                                   │
                                      PG Outbox 发布子任务
                                                   │
                                      Redis Streams / Worker
                                                   │
                                      Bronze 原始记录→MinIO
                                                   │
                                      Silver 校验/去重→Supabase
                                                   │
                                      Gold 历史事实→ClickHouse
```

- **只有 Crawlab** 配置定时采集批次；原生 Freshness Scheduler 在本部署中关闭。Redis Streams 不是第二个批次定时器，只是批内的 at-least-once 工作队列。
- **只有 Supabase PostgreSQL** 持有采集任务和商品、关键词等业务主档。**不**启动第二个本地 PostgreSQL。**MongoDB 不存 SKU、Cookie、原始 JSON 或计算结果**。
- MinIO 保存已获留存许可的原始快照；ClickHouse 保存历史事实，二者不由 Crawlab 直接写入。
- `collector_core` 是新建的**私有 schema**，不会覆盖仓库已有的 `ozon_raw`、`ozon_analytics`、`public` 或旧 SQLite 结构。原数据库字段/计算规则不直接沿用，需在 Bronze/Silver 验证来源和口径。
- 默认只开放合法 Mock 来源。Seller、Buyer 的真实采集源必须先确认授权/存储许可/频率并启用策略；403、挑战、许可失效时禁止绕过。

## 1. 在 Supabase 创建独立的私有 Schema

在 Supabase Dashboard → SQL Editor，执行 [001_private_schema.sql](../sql/supabase/001_private_schema.sql)。此脚本只新增 `collector_core` schema 并关闭对 `anon`/`authenticated` 的访问，**不会改动原业务数据**。

然后在 Supabase 的 SQL Editor 建立一个专用于 Collector 的普通数据库角色（密码请使用随机长密码，不要写入代码仓库）：

```sql
CREATE ROLE collector_runtime LOGIN PASSWORD '请替换为强随机密码';
```

生产系统不要用 `postgres`、`service_role` 或 `anon` 作为运行时数据库角色。这个角色只在迁移完成后获授 `collector_core` 的 DML 权限，不授予 schema CREATE 权限。控制面本身通过 FastAPI API Key 进行读写鉴权。

## 2. 配置外部连接（需要一次性配置）

```bash
cp .env.crawlab-supabase.example .env.crawlab-supabase
```

在 Supabase Dashboard → **Connect → Session pooler** 复制真实连接字符串，不要根据地区猜测主机名；IPv4-only 服务器建议 Session pooler 的 5432 端口。运行时 URL 以 `postgresql+psycopg://collector_runtime.PROJECT_REF:...` 开头（把 `PROJECT_REF`、host、password 换成真实值），并带上 `?sslmode=require`（生产建议 `verify-full`）。Compose 设置 `COLLECTOR_PG_SCHEMA=collector_core`，在每个数据库连接建立时执行 `SET SESSION search_path TO collector_core, public` 并在 API 启动时核验。**不依赖 Pooler 的 URL `options` 参数**，且必须使用 Session 模式而不是 Transaction 模式。

这里使用 SQLAlchemy 兼容的 URL，密码中的 `@ : / & ? #` 等特殊字符必须 URL 编码。生产建议使用 Supabase 根证书及 `sslmode=verify-full`；不要把 URL 放在网页或 Crawlab 的任务参数里。仅 `api`、`worker`、`publisher` 容器获得运行时 URL。

**迁移管理员连接**：临时在 `SUPABASE_MIGRATION_DATABASE_URL` 填入从 Supabase Connect 复制的受信任管理员 URL，并加上同样的 TLS 参数（schema 在 Alembic 连接回调设置）。这个变量**只**注入 `db-migrate` one-shot 服务，绝不注入 Crawlab 或 Worker。部署后从 env 移除其值并妥善轮换。

> Supabase 官方连接建议：长期运行的后端优先 Direct（IPv6 或 IPv4 addon）或 Session pooler（IPv4），需要加密连接。见 [Supabase Connect](https://supabase.com/docs/guides/database/connecting-to-postgres)。

## 3. 初始化数据库并授权（只执行一次）

**先**运行 Alembic。它在 `collector_core` 会话内把 `products`、`keywords`、`collection_jobs`、`job_events` 等表建在新私有 schema：

```bash
docker compose --env-file .env.crawlab-supabase \
  -f docker-compose.crawlab-supabase.yml --profile bootstrap \
  run --rm db-migrate
```

**再**在 Supabase SQL Editor 执行 [020_runtime_grants.sql](../sql/supabase/020_runtime_grants.sql)，将这些表的 SELECT/INSERT/UPDATE/DELETE 授予 `collector_runtime` 角色。每次未来增加新表后要复核表授权。

安全检查（Supabase SQL Editor）：

```sql
SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'collector_core';
SELECT has_schema_privilege('anon', 'collector_core', 'USAGE') AS anon_access,
       has_schema_privilege('authenticated', 'collector_core', 'USAGE') AS authenticated_access;
-- 两个 access 必须都是 false
SELECT COUNT(*) FROM collector_core.products;
```

不把 `collector_core` 加入 Supabase Data API 的 exposed schemas，不授予浏览器账号直接的表写入权限。Metabase 以后可以通过单独只读角色或专门 VIEW 使用数据。

## 4. 启动独立的 Crawlab + Runtime

```bash
docker compose --env-file .env.crawlab-supabase \
  -f docker-compose.crawlab-supabase.yml up -d --build \
  redis clickhouse minio minio-init api publisher worker crawlab
```

可使用 `--scale worker=2` 扩大 Worker 数量（不需要第二个调度器）。

- Crawlab：<http://127.0.0.1:8080>（首次创建管理账号）
- FastAPI OpenAPI：<http://127.0.0.1:8000/docs>
- MinIO、Redis、ClickHouse、MongoDB 没有公网端口；Crawlab 容器不能直连数据存储网段。

在 Crawlab 创建 Python 爬虫任务，命令设置为：

```bash
python3 /opt/ozon/bridge.py /opt/ozon/approved_batch.json --wait --max-wait 600
```

Crawlab 定时器管理这条**批次**命令，而不是管理每个 SKU 的重试。脚本使用纯 Python 标准库，只向 `POST /api/v1/jobs` 发送清单（附带幂等键），可选通过 `GET /api/v1/batches/{batch_id}` 等待完成。它不会存储采集结果到 MongoDB。

**注意**：默认清单是两条 `mock` 测试任务。要换成真数据源，必须先在 Supabase 的 `data_sources/collection_policies` 里完成授权、限额验证；不得修改脚本绕过该门禁。首次部署需在目标 Crawlab 镜像中确认 Python3 可用和命令目录可访问。

## 5. 结果查询与故障定位

Crawlab 任务日志只记录 `{batch_id, submitted, job_ids}` 与**可选**的批次状态，不记录请求 Cookie 或 SKU 原始载荷。

```text
GET /api/v1/batches/{batch_id}
  total, completed, failed, pending, by_status, status
GET /api/v1/jobs/{job_id}
  status, attempts, raw_object_key, raw_sha256
GET /api/v1/products
GET /api/v1/keywords
```

- Crawlab 显示“提交成功”只表示 FastAPI 已接受任务；**不是采集完成**。打开 `--wait` 可让其在有界期限内显示结果，否则在 FastAPI 查询批次状态。
- 存储故障时 Worker 不 ACK，Redis Streams 的 `XAUTOCLAIM` 可认领超时消息；失败预算耗尽写 DLQ。业务任务状态以 Supabase PostgreSQL 为准。
- Silver 校验后主档进入 Supabase；Gold 事实写 ClickHouse；原始响应只在符合许可时存 MinIO。任何字段（尤其 `stock_max`、销量、排名、变体）不能未经核验直接推断真实销量或库存。

## 6. 已验证和未验证的范围

本次代码提供：独立 Compose、Schema/权限 SQL、批次桥接 CLI、批次状态 API、Mock 测试、TLS 和私有 schema 校验。**尚未在真实 Docker、Supabase 项目、ClickHouse/MinIO 容器或 Crawlab UI 上联调**。上线前必须按顺序完成：Supabase 连接与权限检查、Compose `config`、Mock E2E、Worker 崩溃恢复、数据回写核对、备份恢复、真实授权与限流核验。原仓库的 README 性能数字不作为实际生产指标。
