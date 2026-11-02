# 24 — Supabase数据导入状态核验（2026-11-02）

## 核验时间
2026-11-02；通过Supabase MCP只读SQL核验。用户仍在上传历史计算结果，分析表行数会继续变化；以下为最近一次核验快照。

## 原始数据：全部完成
snapshot_id：toys_2026_11_02_33e5f029  
状态：imported_verified  
源文件SHA256：33e5f02961c2782cead58e6714266aab6cbddc31e74242f905d2a7ba218502d8

| 原始表 | 实际行数 | 预期行数 |
|---|---:|---:|
| blue_v3 | 142 | 142 |
| category | 1 | 1 |
| dim_cluster | 165 | 165 |
| fact_keyword_sku | 177,063 | 177,063 |
| keyword_p7 | 9,979 | 9,979 |
| keyword_score | 2,795 | 2,795 |
| keyword_seerfar | 1,642 | 1,642 |
| keyword_sku | 177,063 | 177,063 |
| product_seerfar | 100 | 100 |
| query_metrics_v2 | 1,642 | 1,642 |
| sku_power | 66,352 | 66,352 |
| sku_snapshot_v2 | 29,823 | 29,823 |
| **合计** | **466,767** | **466,767** |

原始唯一键核验：
- sku_snapshot_v2：29,823行，29,823个不同SKU。
- keyword_sku：(keyword,sku) 177,063行，177,063个不同组合。
- fact_keyword_sku：(keyword,sku) 177,063行，177,063个不同组合。

## 历史分析结果：部分完成，上传仍在进行
关联run_id：market_scale_v2_2026_11_02_70d6db0a  
状态：partial_historical_analytics_import。

| 分析表 | 最近实际行数 | 目标行数 | 状态 |
|---|---:|---:|---|
| cluster_market_165 | 165 | 165 | 完成 |
| keyword_market_1642 | 1,642 | 1,642 | 完成 |
| cluster_sku_detail | 40,757 | 40,757 | 完成 |
| keyword_sku_detail | 12,000 | 177,060 | 上传中 |
| market_scale_summary | 0 | 39 | 未上传 |

以上为最近一次查询值，keyword_sku_detail可能继续增长。历史分析表的导入不等于在Supabase重新执行了计算；该run仍需独立校验来源、公式和完整性。

## 项目提示词与上下文
- OMI-SYSTEM-1.0已注册Supabase prompt_registry，active prompt数量1。
- project_context当前保存项目目标、执行环境、实体层级、V2决策、工具资源、恢复顺序和导入状态。
- 已建立decision_log、run_events、artifact_registry、human_labels等上下文/治理表。
- 20/21/22/23号文档分别定义系统提示词、每轮工具资源、上下文保存和标准运行流程。

## 当前结论
1. 原始数据已全部上传并逐表行数核验。
2. 两张市场汇总表和cluster_sku_detail已达到目标行数。
3. keyword_sku_detail仍在上传；market_scale_summary未上传。
4. 历史结果上传完成后，仍应创建新run_id，在Supabase基于raw表重新计算并对账；不能把历史导入当成新的生产计算。
5. 下一次运行必须重新查询行数，不沿用本报告的实时计数。
