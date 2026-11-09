# 部署与验证手册（Mock first）

## 现实边界

本目录是 `ozon-seller-kit` 的**工程化 overlay**；保留上游 `ozon_seller/`、`ozon_buyer/` 和 `project/` 不变。由于本轮执行环境不能解析 `github.com`，本地尚未将工程 overlay 合并到完整原仓库，也不能打开其 19.9MB SQLite 本地二进制重做完整审计。源码审计来自已授权 GitHub API 的文本文件，详见 `source-audit.md`。不能以 Mock 测试替代 Docker/真实 Ozon/DSH/Crawlab 的生产验收。

## 本地零网络验收

```bash
python -m pytest -q
python scripts/demo_smoke.py
DATABASE_URL=sqlite:////tmp/ozon-migration-check.db alembic upgrade head
```

本地 demo 使用 sqlite 和内存队列/MinIO/事实存储；它验证结构、幂等、失败路径，不证明 PostgreSQL、Redis、MinIO、ClickHouse 性能和真实网络可靠性。

## Docker Compose 起步

```bash
# 需要能访问容器镜像仓库的 Docker Compose v2 环境。
bash scripts/bootstrap.sh
# 新终端：使用 .env 的 API_KEY 调用本机控制 API
curl -fsS -H "X-API-Key: $(grep '^API_KEY=' .env | cut -d= -f2-)" http://127.0.0.1:8000/api/v1/sources
curl -fsS -X POST -H "X-API-Key: $(grep '^API_KEY=' .env | cut -d= -f2-)" \
  -H 'Content-Type: application/json' http://127.0.0.1:8000/api/v1/jobs \
  -d '{"source_id":"mock","endpoint":"sample","kind":"keyword","payload":{"keyword":"антистресс"}}'
# 完成后凭返回的 id GET /api/v1/jobs/{id}，再查产品/关键词/Agent。
```

API OpenAPI 在 `http://127.0.0.1:8000/docs`；Grafana `http://127.0.0.1:3000`。在生产前修改示例凭证，配置只读 `VIEWER_KEY`，按租户隔离、最小授权、备份加密、监控告警接收人及数据库 TLS。Compose 中的 MinIO root/CH default 用户仅用于本机演示。

## Crawlab 与 DSH

- Crawlab 只管理批次/部署：`docker compose --profile crawlab up -d`。经许可后将 `scripts/crawlab_batch.py` 配置为 Crawlab Spider，传入 `--batch-id` 与 JSON 任务清单（从 Crawlab 批次 ID 获取），向 FastAPI 创建子任务；**不要同时让 Crawlab 抢 Redis Streams 的子任务**。
- DSH 连接内部 MCP 服务需通过受控 gateway、服务间身份校验与已知工具白名单。`collector.agents.mcp_server` 提供两个专业 Agent 的查询工具与**提案**；外部 DSH 真正的 Ticket/Session/Assignment 回调仍未完成环境对接。
- `mark_dead` 兼容路径仅 admin 可调用；真实凭证引用需 Vault KV2，且不能写明文业务表。Buyer 只允许离线获准快照；Seller P7 的线上采集缺口保持关闭。

## Helm

`helm/` 是应用层示例 chart，依赖集群已安装并配置的 PostgreSQL、Redis、ClickHouse、MinIO、监控与受限 Secret。部署前先创建 `ozon-collector-secrets`，明确密钥来源与权限，执行 `helm lint helm`、`helm template ...` 后再安装。示例 registry 位置为占位符，必须替换为经过签名扫描的自有镜像。

## 未验收项

Docker Engine/Helm/网络在当前运行环境不可用，因此未实际启动容器；PostgreSQL 与 ClickHouse 集成测试、Redis Lua 真限流、Vault 真实凭证获取、P0/P1 外部告警收件人测试、Crawlab 任务部署、DSH 实例联通、MinIO/ClickHouse 恢复演练和 Ozon 正式合法授权尚未验收。见 `docs/test-report.md`。
