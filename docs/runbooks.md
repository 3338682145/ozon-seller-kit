# 可审计故障 Runbook（版本 v1）

## 共同规则

1. 当 HTTP 301/302/307/308、401/403、HTML Challenge、429 或 Vault 凭证吊销发生时，**立即停用受影响 source**，不得换代理、切 Cookie、自动 mint、重试挑战或通过另一个账号继续。
2. 若 MinIO 或 ClickHouse 写入失败，作业不得变成 `completed`；执行有限退避重试，观察 `retry_wait`，恢复后检查原始对象校验和与数据行数。Redis 已投递但未 ACK 的消息由 XAUTOCLAIM 和 PG 租约接管。
3. P0/P1：值班负责人核对 P0/P1 告警的真实投递链路，人工批准所有恢复/授权/DDL/删除操作。**当前示例 Alertmanager receiver 不含任何外部目标**，部署上线前必须配置邮箱/合规 webhook，并进行可验证的演练。
4. 所有恢复均应记录 Ticket、Session、Decision、Assignment、Report、受影响 `job_id`、时间窗口、事件去重键、根因证据、执行人、结果与回归验证；不得在报告中泄漏 Cookie、JWT、请求头或完整原始响应。

## api-unavailable

- 等级 P1；看 API /healthz、Prometheus `up{job="ozon-api"}`、PostgreSQL readiness 和容器退出码。
- 若数据库不可用，禁止立即重启成风暴；检查资源/连接限制，验证 DB 可连通后再恢复消费。
- 恢复验证：`GET /healthz`、只读 `GET /api/v1/database/health`、任务创建和模拟任务完成。

## worker-not-consuming

- 等级 P1；看 `ozon_live_workers`、PG `worker_heartbeats`、Redis XINFO GROUPS/XPENDING、Outbox unpublished 和 `collection_jobs.lease_expires_at`。
- 修复前核对 policy 与凭证状态，禁止以提高请求速率作为默认修复动作。
- 恢复验证：在模拟数据源创建唯一任务；消费者组 ACK，PG 仅一次 `completed` 事件，Bronze SHA256 与 Silver/Gold 行数匹配。

## source-permission-lost

- 等级 P2；立即封禁源，并停止同源未完成任务。凭证失效走管理员重新授权和许可限额确认，不自动浏览器刷新/挑战求解。
- 恢复需要新的授权材料记录、人工审批及健康验证。不能使用 `resume_source` 绕过身份或访问限制。

## storage-failure

- 等级 P1；停止下游结果公布，确认 MinIO bucket、ClickHouse 可读写及 PostgreSQL 稳定性。
- 按原始 SHA256 和 dataset_version 离线重算；ClickHouse ReplacingMergeTree 是**最终一致性**，需要 `FINAL` 或确定性版本查询核验。
- 数据损坏/重大数据丢失升级 P0，进入人工隔离恢复流程，先在 staging 恢复并对账。

## critical-incident

- P0：凭证泄漏、数据损坏、重大数据丢失；P1：核心采集或 DB 不可用。立即联系值班人员，冻结高风险变更，记录证据和时间线。
- 固定执行预算：同类自动重试至多 `collection_policies.retry_budget`，不得无终止循环；未知故障由人/受控 Agent 给出建议，不执行任意生产 SQL/Shell。
- `scripts/pg-backup.sh` 只备份 PostgreSQL；ClickHouse 和 MinIO 需在生产设施单独配置备份、异地校验和恢复演练，不能用 PG 备份代替全量恢复。
