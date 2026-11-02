# 24 — Supabase数据导入状态核验（2026-11-02）

## 核验时间
2026-11-02；通过Supabase MCP执行只读SQL。上传可能持续进行，以下为核验时点，不代表之后不会变化。

## 原始数据
source_snapshot_id：toys_2026_11_02_33e5f029  
状态：imported_verified  
源文件SHA256：33e5f02961c2782cead58e6714266aab6cbddc31e74242f905d2a7ba218502d8

| 原始表 | 实际行数 | 预期行数 | 状态 |
|---|---:|---:|---|
| blue_v3 | 142 | 142 | 完成 |
| category | 1 | 1 | 完成 |
| dim_cluster | 165 | 165 | 完成 |
| fact_keyword_sku | 177,063 | 177,063 | 完成 |
| keyword_p7 | 9,979 | 9,979 | 完成 |
| keyword_score | 2,795 | 2,795 | 完成 |
| keyword_seerfar | 1,642 | 1,642 | 完成 |
| keyword_sku | 177,063 | 177,063 | 完成 |
| product_seerfar | 100 | 100 | 完成 |
| query_metrics_v2 | 1,642 | 1,642 | 完成 |
| sku_power | 66,352 | 66,352 | 完成 |
| sku_snapshot_v2 | 29,823 | 29,823 | 完成 |
| **合计** | **466,767** | **466,767** | **全部核验通过** |

## 计算结果表（核验时点）
| 分析表 | 当前行数 | 预期/目标 | 状态 |
|---|---:|---:|---|
| cluster_market_165 | 165 | 165 | 已上传 |
| keyword_market_1642 | 1,642 | 1,642 | 已上传 |
| cluster_sku_detail | 24,000 | 40,757 | 部分上传，仍在进行/待补齐 |
| keyword_sku_detail | 0 | 177,060 | 尚未上传 |
| market_scale_summary | 0 | 39 | 尚未上传 |

以上分析表使用run_id：market_scale_v2_2026_11_02_70d6db0a。其calculation_runs状态尚未标记完成；当前行数只是上传结果，不代表本轮已经由Supabase重新计算或完整验收。

## 项目上下文与提示词
- 已创建并启用OMI-SYSTEM-1.0，主文档为20-MASTER-SYSTEM-PROMPT.md。
- prompt_registry中active提示词数：1。
- project_context active keys：7。
- decision_log approved decisions：2。
- run_events已有2条架构/导入记录。
- 21/22/23号文档定义每轮资源、上下文和执行流程。

## 当前结论
1. 原始数据已全部上传并通过逐表行数核验。
2. 历史计算结果正在分批上传，当前不完整。
3. 不应因cluster_market和keyword_market已有完整行数，就宣布所有分析明细上传完成。
4. 正式计算仍应创建新的run_id，在Supabase按源数据重新计算、对账；已上传历史结果仅作为baseline。
5. 下一次运行先重新查询分析表行数，不能沿用本报告的实时状态。
