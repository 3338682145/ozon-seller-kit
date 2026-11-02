# Ozon Market Intelligence

版本 v1.7｜首个验证类目：解压玩具｜核心单位：产品族｜预测周期：30–90天

## 项目目标
建立以Ozon市场交易与搜索数据为基础的产品级市场情报系统：识别真实大众需求，将同款SKU归并为产品族，计算市场规模、增速、竞争可进入性、单位经济与新品经营预期，并通过持续回测修正预测。

**决策顺序：需求真实性 → 产品族市场规模 → 可打入性 → 单位经济/ROI → 30–90天预测 → 实际结果回测。**

## 文档地图
1. [01 Goal与执行Plan](01-GOAL-AND-PLAN.md)
2. [02 数据字典与数据契约](02-DATA-CONTRACT.md)
3. [03 指标与计算公式](03-METRICS-AND-FORMULAS.md)
4. [04 数据核验与验收清单](04-VALIDATION-CHECKLIST.md)
5. [05 技术架构与数据流水线](05-TECHNICAL-ARCHITECTURE.md)
6. [06 RSI递归自我改进机制](06-RSI-SELF-IMPROVEMENT.md)
7. [07 里程碑与交付物](07-ROADMAP-AND-DELIVERABLES.md)
8. [08 SQLite初审报告](08-DATABASE-AUDIT-2026-11-02.md)
9. [09 完整版数据库更新审计](09-DATABASE-UPDATE-AUDIT-2026-11-02.md)
10. [10 数据归档与DRR质量政策](10-DATA-ARCHIVE-AND-DRR-POLICY.md)
11. [11 第二层需求簇与第三层SKU实体构建报告](11-LAYER-2-3-BUILD-REPORT.md)
12. [12 字段字典核验与模型口径修订](12-FIELD-DICTIONARY-VALIDATION-AND-MODEL-REVISION.md)
13. [13 项目进度与计算计划](13-PROGRESS-GAPS-AND-CALCULATION-PLAN.md)
14. [14 P6毛订单与估算妥投净规模试算](14-P6-GROSS-NET-SCALE-TRIAL.md)
15. [15 165需求簇与1,642关键词Gross/Net规模及双口径CR4](15-MARKET-SCALE-165-1642-2026-11-02.md)
16. [16 关键词需求簇规则优化提案 v2](16-KEYWORD-CLUSTERING-OPTIMIZATION.md)
17. [17 Keyword Clustering V2离线实验与验收方案](17-KEYWORD-CLUSTERING-V2-EXPERIMENT-AND-ACCEPTANCE.md)
18. [重算脚本](scripts/rebuild_market_scale.py)

## 当前状态
- [x] L1：165个关键词需求簇
- [x] L2：簇内SKU去重市场聚合
- [x] L3：48,898个SKU实体及关键词/簇关联
- [x] 165簇与1,642关键词Gross/Net-est及双口径CR4重算
- [x] V2关键词聚类实验规则与验收方案已制定
- [ ] V2候选关键词对计算、人工标注与Precision/Recall验收
- [ ] L2a：Exact/Variant/Close产品族和跟卖报价关系
- [ ] 全量Entry生产流水线
- [ ] 利润ROI及30–90天预测回测

## 当前市场模型边界
- P6为28天毛下单口径，含取消/退货；Net-est按nullableRedemptionRate估算，不是最终结算账。
- P8严格限制position 1–108；CR4仅代表可观测搜索位SKU样本。
- 关键词/簇之间SKU重叠，跨簇总市场必须全局SKU去重。
- 165簇之外仍有大量未归类P6 SKU，需独立保留Unclustered市场池。
- DRR定义已确认，但极端值需要质量控制；单品实际广告费优先广告账单核对。
- P7 count_28d为独立搜索买家数；跨关键词不可直接相加为独立消费者数。

## 关键词簇V2冻结原则
- 40% = 两关键词共有SKU数 / 较小SKU集合数（Overlap Coefficient），仅作为候选生成条件。
- 目标为相同搜索意图/需求市场，不等于同款产品族。
- 每个关键词一个Primary Cluster；允许Secondary关联，但不参与市场加总。
- V1现有165簇保留为baseline；V2簇数不强制为165。
- 加入Jaccard、Top30重合、排名加权、SKU IDF、语义/类目约束及Medoid/Complete-Linkage防链式合并。
- 先完成300对人工标注、Precision/Recall和簇纯度验收，未达标不覆盖V1。

## 云端归档
市场规模计算包已存Google Drive，见项目历史同步记录。方法论、计算脚本与审计报告保存在本目录。
