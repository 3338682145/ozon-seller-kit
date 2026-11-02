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
- 旧版toys-slim.db另行留存；sku_weekly仅在旧版slim中，不得假定已并入新版。
- 字段口径与模型修订见 12-FIELD-DICTIONARY-VALIDATION-AND-MODEL-REVISION.md。

## DRR状态：SEMANTICS_CONFIRMED / VALUE_QC_REQUIRED
2026-11-02用户提供的Ego-Browser DOM原生悬停解释已确认：drr是推广费用与订购商品价值的比率，统计所有订单（含取消和退货），计算基准采用价格上限。因此DRR不再标记为“定义不明”。
但数值质量仍需控制：
- drr=0保留为0广告费用份额，不自动填充；使用daysWithTrafarets、P8推广状态辅助交叉验证。
- 极端值（>100%或数千%）标记异常，可能由GMV分母极小导致放大；不据此直接淘汰产品。
- 批量分析展示原始DRR、中位数、分位数和异常率。
- 单SKU投放成本优先查P8 promotionCpcRate、promotionCpoRate和推广状态；CPC是出价不是实际扣费。
- 正式利润最好以广告账单实际消耗对账；无账单时使用DRR敏感性场景，不伪装成精确净利。
- 保留raw_drr、source、snapshot_date、异常标记，不覆盖原值。

## 结单率与退货
nullableRedemptionRate的官方UI解释为未取消且未退回的订购商品百分比，即成功结单/妥投留存率，不是退货率。1-r表示未结单比例，可能混合取消、拒收、未取件、退货等原因；不能直接命名return_rate，也不能直接等同逆向物流成本。若拿到失败原因明细，应分别建模。
