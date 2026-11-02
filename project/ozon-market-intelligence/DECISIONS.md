# 项目决策记录

## ADR-2026-11-02-01：Supabase作为正式计算环境
状态：已批准。
- 项目：eohvguguegxbhszvssbd。
- 后续正式数据计算、聚类实验、结果存储和对账均在Supabase执行。
- GitHub 3338682145/ozon-seller-kit保存系统提示词、SQL、公式、进度、决策、验收和handoff。
- Google Drive保留原始文件；本地/沙箱只用于文件检查、导入准备和结果展示，不可冒充正式计算环境。

## ADR-2026-11-02-02：原始数据导入验收
状态：已验证。
- toys.db SHA256：33e5f02961c2782cead58e6714266aab6cbddc31e74242f905d2a7ba218502d8。
- Supabase ozon_raw 12张表合计466,767行，逐表与预期行数完全一致。
- source_snapshot_id=toys_2026_11_02_33e5f029，状态imported_verified。
- 分析表仍为空；下一步应在Supabase重算，不把本地旧结果当作Supabase正式结果。

## ADR-2026-11-02-03：系统提示词和运行资源
状态：已批准。
- 系统提示词版本OMI-SYSTEM-1.0，主档GitHub 20-MASTER-SYSTEM-PROMPT.md，副本登记Supabase ozon_meta.prompt_registry。
- 每次运行资源清单见21-RUNTIME-TOOLS-AND-RESOURCE-MANIFEST.md。
- 标准运行流程见23-RUN-PLAYBOOK.md。

## ADR-2026-11-02-04：上下文持久化
状态：已批准。
- GitHub保存人类可读项目状态、决策、规则、公式、提示词和handoff。
- Supabase保存机器可读快照、运行、计算结果、项目上下文、决策、提示词、事件、工件和人工标签。
- Google Drive保存原始文件和交付归档。
- 聊天记录、模型隐式记忆和沙箱临时文件均不作为项目事实库。
- 每轮新会话按22号文档恢复上下文；每轮结束更新GitHub HANDOFF并写Supabase运行事件。

## ADR-2026-11-02-05：实体和聚类规则
- Keyword → Demand Cluster → Product Family → SKU → Seller Offer。
- V1 165需求簇冻结；V2目标为同一搜索意图市场。
- 40%为共有SKU数/较小SKU集合数，只作候选召回。
- 每词一个Primary，允许多个Secondary；Secondary不参与市场加总。
- L2a精准同款/变体/跟卖必须有商品身份或报价证据，不能靠关键词簇或向量相似度单独确认。

## ADR-2026-11-02-06：数据与计算口径
P6 Gross包含取消退货；Net-est按nullableRedemptionRate估算；NULL不填补；P6 salesDynamics是GMV动态；P7 count_28d是独立搜索买家数；P8 position 1–108；CR4是可观测SKU样本；DRR语义已确认但极端值继续QC。RSI不能未经批准修改生产规则或执行采购/投放。
