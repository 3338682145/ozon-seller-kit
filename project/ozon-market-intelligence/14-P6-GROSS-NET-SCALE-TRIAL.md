# 14 — P6毛订单与估算妥投净规模试算（2026-11-02）

## 口径
P6 soldCount与gmvSum为28天毛订单口径，包含取消和退货。nullableRedemptionRate是未取消且未退回的订单商品百分比。
- gross_units = soldCount
- r = nullableRedemptionRate / 100
- net_units_est = soldCount × r
- avg_price = gmvSum / soldCount
- net_gmv_est = net_units_est × avg_price

净口径是估算妥投件数/GMV，不是Ozon直接返回的最终结算数据。未结单订单与妥投订单的价格结构若不同，会产生估算误差。126个redemption_rate缺失SKU未纳入净估算，不能默认填0或100%。

## 结果
| 范围 | SKU数 | Gross units | Net units estimate | Gross GMV RUB | Net GMV estimate RUB |
|---|---:|---:|---:|---:|---:|
| 全部p6 SKU样本 | 29,823 | 3,332,338 | 2,964,160 | 1,318,910,734 | 1,140,330,863 |
| category3=抗压玩具 | 16,039 | 1,117,485 | 995,674 | 248,221,059 | 220,841,423 |

以上为当前P6可观测SKU样本，不宣称Ozon全站完整市场。GMV_net_est = net_units_est × avg_price。

## 后续应用
1. 产品族/簇规模同时输出gross与net_est。
2. CR4分别按gross和net_est销量重新排序Top4后计算。
3. 缺失redemption_rate的SKU单列coverage和上下界敏感性。
4. 净估算指标需在产品族exact/close映射准确后重新汇总，避免SKU跨簇重复。
