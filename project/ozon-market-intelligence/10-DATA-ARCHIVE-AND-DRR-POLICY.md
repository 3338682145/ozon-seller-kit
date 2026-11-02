# 10 — 数据归档与DRR质量政策

## 本地归档与云端同步
- 原始数据按 data-snapshots/YYYY-MM-DD/ 本地归档，只读保存，不覆盖旧快照。
- 每份数据记录文件名、大小、SHA256、Drive File ID、修改时间和snapshot_id。
- 方法论、审计报告、数据契约、公式、代码、配置和RSI决策先本地保存，再同步到GitHub本项目目录。
- 大型SQLite/Parquet不提交GitHub；原始数据保留在Google Drive，分析副本保留本地。
- 每次云端同步后读回核验并记录commit SHA；失败时明确标记待同步。
- 清洗和派生数据写入新目录/新表，保留源快照指纹。

## 2026-11-02数据快照
- toys.db，128,512,000 bytes
- SHA256：33e5f02961c2782cead58e6714266aab6cbddc31e74242f905d2a7ba218502d8
- Drive File ID：1HdWipkSd0f8aw6Zsb_n6-UhnyX_fD_yD
- SQLite integrity_check：ok
- 旧版toys-slim.db另行保留；sku_weekly仅在旧版slim中，不得假定已并入新版。
- 详细审计见 [09-DATABASE-UPDATE-AUDIT-2026-11-02.md](09-DATABASE-UPDATE-AUDIT-2026-11-02.md)。

## DRR状态：SUSPECT / QUARANTINED
用户指出DRR字段可能存疑。从2026-11-02起，原始drr仅用于展示（带警告）、异常诊断和跨源核验；不作为硬筛选条件，不直接用于正式单点净利润、ROI或COGS上限。利润先展示不含广告的基础利润，并给DRR=0%、5%、10%、15%敏感性场景。drr=0语义同样未核实，不能自动认定为自然流量或未投放。保留raw_drr、source、snapshot_date和异常标记，不覆盖原值。

### 已观测分布
- 全库29,823 SKU；drr=0为15,471（51.9%）。
- drr>0为14,352；正值中位数8.64，P75=16.77，P90=29.11，P95=41.12，P99=96.90。
- drr>30为1,327；drr>100为137；最大10,431.14。
- 抗压玩具16,039 SKU中，drr>100有43，drr>30有566，drr=0有10,380。
- product_seerfar 100样本中94个SKU可跨源对照DRR，相关系数约0.9957；样本不足以验证字段定义或解除隔离。

### 解除隔离条件
1. 确认DRR定义、分子分母、归因口径和统计周期。
2. 确认百分数/比例单位以及0与NULL语义。
3. 与真实广告消耗和归因GMV做代表性样本对账。
4. 解释低销量样本及>100%的极端值。
5. 完成验证报告并经人工批准。

## 结单率
用户业务解释为结单率=成功结算率，1-结单率可作为未成功结算比例。需确认未结算是否全部是退货，还是包含拒收、取消、未取件、配送失败。未核验前使用non_settlement_rate_scenario，不直接称为真实return_rate。