# Ozon Market Intelligence

版本 v2.0｜首个验证类目：解压玩具｜核心经营实体：产品族｜预测周期：30/60/90天

## 当前执行入口
- [PROJECT-STATUS.md](PROJECT-STATUS.md) — 实际进度
- [DECISIONS.md](DECISIONS.md) — 已批准决策
- [HANDOFF.md](HANDOFF.md) — 新会话接手入口
- [20-MASTER-SYSTEM-PROMPT.md](20-MASTER-SYSTEM-PROMPT.md) — 系统提示词
- [21-RUNTIME-TOOLS-AND-RESOURCE-MANIFEST.md](21-RUNTIME-TOOLS-AND-RESOURCE-MANIFEST.md) — 每轮工具和资源
- [22-CONTEXT-PERSISTENCE-AND-HANDOFF.md](22-CONTEXT-PERSISTENCE-AND-HANDOFF.md) — 上下文存储与恢复
- [23-RUN-PLAYBOOK.md](23-RUN-PLAYBOOK.md) — 每轮执行步骤和SQL验收模板

## 正式运行环境
Supabase project_id：eohvguguegxbhszvssbd；PostgreSQL 17.6。
- ozon_raw：原始快照。
- ozon_analytics：run_id版本化计算结果。
- ozon_meta：快照、运行、上下文、决策、提示词、事件、工件和人工标签。
2026-11-02实查：原始12张表均已达到预期行数，合计466,767行；source_snapshot_id=toys_2026_11_02_33e5f029，状态imported_verified。分析表当前为空，下一步在Supabase重新计算。

## 项目目标
建立以Ozon市场交易与搜索数据为基础的产品级市场情报系统：识别真实大众需求，将同款SKU归并为产品族，计算市场规模、增速、竞争可进入性、单位经济与新品经营预期，并通过持续回测修正预测。

## 规范实体层级
Keyword → Demand Cluster → Product Family → SKU → Seller Offer。
- V1：165个搜索意图需求簇，冻结为基线。
- V2：40% Overlap Coefficient仅作候选召回；每词一个Primary，可有Secondary但不参与市场加总；未验收不覆盖V1。
- Product Family/L2a：必须有商品身份、变体、条码/型号、跟卖报价或人工确认等证据；相似向量仅用于召回。

## 数据口径
- P6 Gross订单含取消/退货；Net-est按nullableRedemptionRate估算，NULL不填补。
- P6 salesDynamics是GMV动态；P7 count_28d是独立搜索买家数。
- P8严格position 1–108；CR4是可观测SKU样本口径。
- DRR定义已确认，数值仍需QC；CPC/CPO是出价不是实际扣费。
- 跨需求簇总市场必须SKU全局去重。

## 其他核心文档
- [02 数据契约](02-DATA-CONTRACT.md)
- [03 指标与公式](03-METRICS-AND-FORMULAS.md)
- [12 字段字典核验](12-FIELD-DICTIONARY-VALIDATION-AND-MODEL-REVISION.md)
- [17 V2聚类实验验收方案](17-KEYWORD-CLUSTERING-V2-EXPERIMENT-AND-ACCEPTANCE.md)
- [18 Supabase数据导入记录](18-SUPABASE-RAW-DATA-IMPORT.md)
- [19 导入器与导入边界](19-SUPABASE-IMPORT-BLOCKER-AND-CLIENT-RUNNER.md)
