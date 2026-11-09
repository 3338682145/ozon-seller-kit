# 执行验收记录（2026-11-09，Mock 限域）

## 已运行的验证

| 方式 | 结果 | 可信边界 |
|---|---|---|
| `python -m pytest -q` | 本轮 41 项测试，详见最终日志 | SQLite + MemoryBroker + Memory MinIO/ClickHouse；无真实服务 |
| `python scripts/demo_smoke.py` | `completed`；3 Product、2 Keyword、1 个原始对象、2 个 Gold keyword fact | Mock 数据，不代表授权 Ozon 前台通道 |
| `DATABASE_URL=sqlite... alembic upgrade head` | 已执行成功，校验 latest revision、worker lease 列 | 仅 SQLite migration smoke，非 PostgreSQL |
| Compose YAML 静态解析 | 服务映射/YAML 通过 | Docker Engine 未安装，不能等同 compose up |
| 程序化 FastAPI OpenAPI 路由核对 | 15/15 要求路由存在 | 认证与请求测试覆盖 Mock，非真实部署 |

## 注入的主要故障场景

- 重复消费：只有一个任务获得有效 lease，另一个重复投递不 ACK 到期的 PEL；结束后确认单次 `completed`。
- Worker 崩溃：租约未过期不能被抢占或误 ACK；租约过期后认领同一任务并继续。
- MinIO 故障：Bronze 不成功，作业进入有限重试，不能标完成。
- ClickHouse 故障：PG Silver 事务回滚，作业进入重试；恢复后同一任务成功。
- 凭证被吊销、HTTP 403/HTML Challenge：源封禁；不可使用 `resume_source` 绕过。
- 只读 API key 不能提交/取消任务，管理员可审批受控操作。
- 俄语变体、价格清洗、空值语义、离线 Gold 正确性、稀疏/旧快照不能擦除商品主档。

## 目前不可声称完成的验收

真实 Ozon 采集、合规代理核验、Crawlab Spider 实际部署、DSH 外部生命周期回调、真实 Vault、Prometheus→Alertmanager 收件人演练、Redis 原生 LUA/XAUTOCLAIM、高并发 PostgreSQL `FOR UPDATE`/锁性能、ClickHouse 跨分区去重、MinIO 异地备份与恢复和全链路持续压测都未执行。实际部署前必须在拥有合法授权、Docker/Helm 和告警渠道的环境逐项演练。

## 性能基线原则

仅记录 Mock/Silver 本地处理时间，不拿上游 README 中“SKU/s”等数字作为生产基准。生产吞吐上限由已验证的 data source 许可、固定速率、真实网络/数据库指标决定，不能自动调高。
