# 04 — 数据核验与验收清单

## A. 文件完整性
- [ ] 获取原始toys-slim.db；记录文件大小、SHA256、来源URL、Git commit SHA。
- [ ] SQLite PRAGMA integrity_check返回ok；只读打开原始库。
- [ ] 导出sqlite_master表/索引清单和每表COUNT(*)。
- [ ] 对照README：关键词1,642、SKU29,823、搜索位177,063、词簇165；差异逐项解释。
- [ ] 记录每张表的snapshot_date、数据生成日期和统计窗口。

## B. 字段质量
- [ ] 核对sold_count、gmv_sum、avg_price空值率、负数、零值和极端值。
- [ ] 检查avg_price与gmv_sum/sold_count偏差，列出异常SKU。
- [ ] drr=0与NULL分别统计，不能混淆。
- [ ] volume单位确认是L；重量、尺寸单位确认。
- [ ] 百分比确认是0–1还是0–100，统一转换。
- [ ] create_date可解析率、未来日期、年龄负值。
- [ ] SKU ID统一TEXT，检查重复、空ID和科学计数法损坏。
- [ ] p8 position范围、重复position、重复SKU、缺失seller_id。
- [ ] p7 query+month+snapshot唯一性和时间窗口一致性。
- [ ] 所有派生指标能从原始表复算。

## C. 业务口径核验
- [ ] redemption_rate的分子、分母、统计cohort、失败原因构成。
- [ ] p6 monthly是否固定28天，weekly是否固定7天。
- [ ] P7 dyn_7d/dyn_28d定义及基准周期。
- [ ] p7 no_action_share与zero_result_share定义、单位和空值含义。
- [ ] GMV是否含取消、退货、未结算订单。
- [ ] DRR定义是否广告花费/成交GMV，是否与其他费用重复。
- [ ] Ozon佣金按真实三级类目/履约方式确认。
- [ ] 运费表有效日期、计费重、抛重除数、偏远附加费和燃油附加费确认。
- [ ] 1688报价规格、MOQ、含税/未税、国内运费、报价有效期确认。

## D. 产品族归并验收
- [ ] 先人工标注至少200组SKU pair，覆盖同款、变体、套装、近似品、完全不同品。
- [ ] exact归并Precision目标>=98%；达不到先调整规则，不批量自动合并。
- [ ] close/broad单独抽样验收，不能把相似品误称同款。
- [ ] 每个family能反查全部SKU、原始标题、图片、类目、归并证据。
- [ ] 跨关键词重复SKU去重后，产品族销量与SKU明细求和一致。
- [ ] 多件装/套装按pack_count规范化，不能把1件装和多件装价格直接混算。

## E. 计算验收
- [ ] max_slot30按seller_id聚合不同SKU，缺失seller单独报告。
- [ ] new_top10只用有效上架日期；快照日作为年龄计算基准。
- [ ] CR4按销量排序而非position/popularity，分母明确。
- [ ] Coverage输出n_p6/n_p8和join原因。
- [ ] 产品族MarketUnits/GMV用去重SKU汇总；exact/close/broad分开。
- [ ] ROI、利润率、采购上限用手工案例逐项复算。
- [ ] p6无历史快照时不生成产品销量增速。
- [ ] 预测结果保存输入快照、模型版本和预测日期。

## F. 发布门槛
只有A–E中阻断项全部通过，才发布正式市场排名。未通过的字段必须降级为观察指标或显示“未知”，不能用默认值伪造精度。每份报告输出数据质量等级：A高、B中、C低，并说明扣分原因。