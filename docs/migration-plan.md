# 工程化改造计划（按阶段、先 Mock）

**原则**：保留上游 Seller/Buyer 已验证的纯解析逻辑；新的 `collector/` 作为工程化叠加层；不将旧 CDP 获取反爬 Cookie、挑战处理、Cookie 池或自动续签迁入 Runtime。真实源默认禁用，凭证/速率需要独立授权。

1. **审计源码**：当前 PR 交付 `source-audit.md`、`endpoint-inventory.md`、`field-dictionary.md`、`data-gaps.md` 和本计划；在可克隆环境补做原始 SQLite 的只读校验，标注源码、历史报告和测试三类证据。
2. **数据库**：PG 主档与作业/审批模型交给 Alembic；ClickHouse 按日期分区、TTL 和幂等事实表；MinIO 4 个 bucket；建立 schema 版本、快照 hash、备份与恢复验证。
3. **Adapter**：统一 `prepare/fetch/parse/validate/report_error`；P6/P8/CJM 只在授权后使用安全 Transport；P7 标未实现；Buyer 先只读取许可离线样本；源级错误政策隔离。
4. **调度**：Crawlab 管 batch、Redis Streams 管子任务，PostgreSQL Outbox 保证投递；用优先级、幂等键、checkpoint、租约和 `XAUTOCLAIM` 恢复；有限重试与 DLQ。
5. **流水线**：Bronze 保留合法原始数据→Silver Polars/PyArrow 正规化→PG 关系/主档→ClickHouse Gold；真实观测、平台统计、估算分开存储并版本化重算。
6. **Agent 与 API**：FastAPI OpenAPI、认证/RBAC、统一错误与分页；Collector Ops / Database Ops 先只读；高风险 DDL/删除/恢复/授权变更通过 Policy Engine 和人工审批，记录决策生命周期。
7. **部署与测试**：先 Mock pytest + 样本 E2E，再真实 Docker Compose 的 PG/Redis/ClickHouse/MinIO 集成与 Worker 崩溃恢复；最后 Crawlab/DSH 联调、授权真实源的低速验收。
8. **性能优化**：只以有权限数据、实际压测和许可限额调整速率；不得套用 README 的实验吞吐结论。

## 安全 / 恢复规则

3xx、401/403、挑战、凭证失效立即封禁对应源并告警；不自动刷新挑战令牌、不轮换身份/代理。存储不可用时保留消费任务并停止下游 ACK，写入恢复后以幂等键安全重放；每次恢复有重试预算和人工升级路径。

## 本 PR 与未完成事项

本 PR **仅包含第一阶段审计及改造计划**，不声称已经在 GitHub 主分支合入完整 Runtime。其余工程文件分批 PR 推送，真正的 Docker Compose / DSH / Crawlab / Ozon 生产验证仍需具备网络、授权、密钥和运行环境。