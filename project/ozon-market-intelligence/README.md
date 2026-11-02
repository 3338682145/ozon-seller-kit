# Ozon Market Intelligence

版本 v1.8｜首个验证类目：解压玩具｜核心单位：产品族｜预测周期：30–90天

## 当前执行入口
用户已指定：后续正式数据计算全部在Supabase执行；GitHub记录进度、决策、公式、SQL和handoff。
- [PROJECT-STATUS.md](PROJECT-STATUS.md)
- [DECISIONS.md](DECISIONS.md)
- [HANDOFF.md](HANDOFF.md)
- [18-SUPABASE-RAW-DATA-IMPORT.md](18-SUPABASE-RAW-DATA-IMPORT.md)
- [19-SUPABASE-IMPORT-BLOCKER-AND-CLIENT-RUNNER.md](19-SUPABASE-IMPORT-BLOCKER-AND-CLIENT-RUNNER.md)

目标Supabase project_id：`eohvguguegxbhszvssbd`。PostgreSQL 17.6。已创建ozon_raw、ozon_analytics、ozon_meta三个隔离schema及19张空表。**原始与派生数据仍待客户端COPY导入，不能标为迁移完成。**

## 项目目标
建立以Ozon市场交易与搜索数据为基础的产品级市场情报系统：识别真实大众需求，将同款SKU归并为产品族，计算市场规模、增速、竞争可进入性、单位经济与新品经营预期，并通过持续回测修正预测。

## 业务口径
- P6为28天毛下单口径，含取消/退货；Net-est按nullableRedemptionRate估算，不是最终结算账。
- P8严格限制position 1–108；CR4仅代表可观测搜索位SKU样本。
- 关键词/簇之间SKU重叠，跨簇总市场必须全局SKU去重。
- DRR定义已确认，但极端值需质量控制；单品实际广告费优先广告账单核对。
- V1 165簇保留；V2聚类目标为相同搜索意图市场；L2a同款/跟卖关系独立建设。

## 数据层与实验状态
- [x] L1：165个关键词需求簇
- [x] L2：簇内SKU去重市场聚合（历史计算结果）
- [x] L3：48,898个SKU实体及关键词/簇关联（历史计算结果）
- [x] V2关键词聚类实验规则与验收方案
- [x] Supabase隔离schema及19张表创建
- [ ] toys.db与计算结果SQLite导入Supabase
- [ ] Supabase行数、唯一键、市场指标对账
- [ ] V2候选关键词对计算、人工标注与Precision/Recall验收
- [ ] L2a Exact/Variant/Close产品族和跟卖报价关系
- [ ] 全量Entry、利润ROI及30–90天预测回测

## 导入包
本地归档：`ozon-supabase-full-import-kit-2026-11-02.zip`。含原始toys.db、派生计算SQLite、COPY导入脚本和manifest。通过本机Direct/Session Pooler执行；凭据不得提交GitHub。详见18号文档。

## 其他文档
- [02 数据契约](02-DATA-CONTRACT.md)
- [03 指标与公式](03-METRICS-AND-FORMULAS.md)
- [11 L2/L3构建报告](11-LAYER-2-3-BUILD-REPORT.md)
- [12 字段字典核验](12-FIELD-DICTIONARY-VALIDATION-AND-MODEL-REVISION.md)
- [15 市场规模历史计算](15-MARKET-SCALE-165-1642-2026-11-02.md)
- [17 V2聚类实验验收方案](17-KEYWORD-CLUSTERING-V2-EXPERIMENT-AND-ACCEPTANCE.md)
