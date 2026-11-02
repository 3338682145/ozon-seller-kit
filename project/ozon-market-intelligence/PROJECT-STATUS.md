# 项目进度

更新时间：2026-11-02。当前执行决策见 [DECISIONS.md](DECISIONS.md)，交接入口见 [HANDOFF.md](HANDOFF.md)。

## 本轮 Supabase 执行结果

| 项目 | 状态 | 证据/边界 |
|---|---|---|
| Supabase SQL连接 | 已验证 | PostgreSQL 17.6 |
| 隔离schema | 已创建 | ozon_raw / ozon_analytics / ozon_meta |
| 表结构 | 已创建 | 12张原始表 + 5张分析表 + 2张元数据表，共19张 |
| schema权限 | 已核验 | anon/authenticated均无三个schema的USAGE权限 |
| RLS | 待纵深加固 | 19张表RLS disabled；当前schema不可由anon/authenticated访问，尚未开放Data API |
| 原始数据上传 | 待完成 | Supabase表已存在但行数为0；没有把“建表”冒充“上传” |
| 计算结果上传 | 待完成 | 分析表已存在但行数为0 |
| Supabase正式重算 | 待完成 | 需先导入原始数据和历史计算基线 |

## 源数据迁移包

导入说明：[18-SUPABASE-RAW-DATA-IMPORT.md](18-SUPABASE-RAW-DATA-IMPORT.md)

- 原始toys.db：SHA256 `33e5f02961c2782cead58e6714266aab6cbddc31e74242f905d2a7ba218502d8`，12张表，466,767行。
- 计算SQLite：SHA256 `70d6db0a5133c6c484db18453015937b273f1a51d95530274949330dc4033ecc`。
- 原始预期行数：blue_v3 142；category 1；dim_cluster 165；fact_keyword_sku 177,063；keyword_p7 9,979；keyword_score 2,795；keyword_seerfar 1,642；keyword_sku 177,063；product_seerfar 100；query_metrics_v2 1,642；sku_power 66,352；sku_snapshot_v2 29,823。
- 派生预期行数：cluster_market_165 165；keyword_market_1642 1,642；cluster_sku_detail 40,757；keyword_sku_detail 177,060；market_scale_summary 39。
- 导入包：`ozon-supabase-full-import-kit-2026-11-02.zip`（本地归档；GitHub不保存大型数据库）。

## 既有成果：历史状态，不是Supabase重算结果

仓库历史报告记录：165个V1需求簇、48,898个SKU实体、1,642关键词的Gross/Net-est及双口径CR4历史计算，和V2实验设计。本轮尚未在Supabase重新计算；导入后需以同一源SHA、同一P8 position 1–108过滤规则进行对账。

## 仍待完成

1. 用户在本机运行导入包的dry-run及正式COPY导入。
2. Supabase逐表行数、唯一键、NULL和关联率对账。
3. 在Supabase重算165簇/1,642关键词Gross/Net-est与双口径CR4。
4. V2倒排索引候选对、人工标注、Precision/Recall验收。
5. L2a同款SKU与跟卖offer关系。
6. Entry生产流水线、利润ROI及30–90天预测回测。

## 安全边界

本轮安全顾问提示19张新表RLS disabled。SQL已核验anon/authenticated对三个新schema均无USAGE权限，因此目前不会通过这些角色访问；仍建议在应用接入前启用RLS并按真实访问模型创建策略。没有自动启用RLS或添加策略，避免误锁预期访问。未修改public现有业务表。
