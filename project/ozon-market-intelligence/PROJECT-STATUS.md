# 项目进度

更新时间：2026-11-02。当前执行决策见 [DECISIONS.md](DECISIONS.md)，交接入口见 [HANDOFF.md](HANDOFF.md)。

## 本轮 Supabase 执行结果

| 项目 | 状态 | 证据/边界 |
|---|---|---|
| Supabase SQL连接 | 已验证 | PostgreSQL 17.6 |
| 隔离schema | 已创建 | ozon_raw / ozon_analytics / ozon_meta |
| 表结构 | 已创建 | 12张原始表 + 5张分析表 + 2张元数据表，共19张 |
| 快照/运行元数据 | 已登记 | snapshot_id和run_id状态均为pending_client_upload |
| schema权限 | 已核验 | anon/authenticated均无三个schema的USAGE权限 |
| 导入器修正 | 已完成 | 修复COPY helper未定义sql变量；py_compile及dry-run通过 |
| 原始数据上传 | 待完成 | Supabase原始表目前仍为0行 |
| 计算结果上传 | 待完成 | Supabase分析表目前仍为0行 |
| Supabase正式重算 | 待完成 | 连接和dry-run不等于数据迁移或重算 |

## 数据源与修正版导入包
- 导入架构/验收说明：[18-SUPABASE-RAW-DATA-IMPORT.md](18-SUPABASE-RAW-DATA-IMPORT.md)
- 直接导入阻塞说明：[19-SUPABASE-IMPORT-BLOCKER-AND-CLIENT-RUNNER.md](19-SUPABASE-IMPORT-BLOCKER-AND-CLIENT-RUNNER.md)
- 原始toys.db SHA256：`33e5f02961c2782cead58e6714266aab6cbddc31e74242f905d2a7ba218502d8`，12张表，466,767行。
- 派生计算SQLite SHA256：`70d6db0a5133c6c484db18453015937b273f1a51d95530274949330dc4033ecc`。
- 修正版导入包SHA256：`efacb91682cf7ead88de5eca59bf77a37f6fcc0ca83ae59ae9ac79e039e3e7a9`。
- 修正版导入器SHA256：`1ce79c9667bd47084e885490d0f9170f0239dc9815482aa5f041d1df35c2fb30`。
- Dry-run预期：原始12表共466,767行；派生4张明细表共219,624 rows（另market_scale_summary 39项，总计219,663条分析记录）。

## 仍待完成
1. 通过能够访问Supabase的客户端执行COPY导入；当前会话没有本地到Postgres的文件传输通道。
2. Supabase逐表行数、唯一键、NULL和关联率对账。
3. 在Supabase重算165簇/1,642关键词Gross/Net-est与双口径CR4。
4. V2倒排索引候选对、人工标注、Precision/Recall验收。
5. L2a同款SKU与跟卖offer关系。
6. Entry生产流水线、利润ROI及30–90天预测回测。

## 安全边界
19张新表RLS disabled。SQL已核验anon/authenticated对三个新schema均无USAGE权限；应用接入前仍建议启用RLS并按访问模型创建策略。本轮未自动启用RLS或添加策略，未修改public现有业务表。
