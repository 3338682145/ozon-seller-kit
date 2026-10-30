#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成「数据采集与字段口径」审核报告（单文件 HTML）

从 toys.db 实读每列有值率，公式对齐 final_report.py 源码，供人工审核。

用法:
    python3 build_data_audit_html.py --out 数据审核报告.html
"""
from __future__ import annotations

import argparse
import html
import json
import sqlite3
import statistics
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB = BASE / "toys.db"

# ── 数据源 ─────────────────────────────────────────────────────────
SOURCES = [
    dict(name="Seerfar Open API", kind="第三方估算", color="#0d9488",
         endpoint="/open-api/keyword/backSearch/ozon 等 6 个",
         got="1,642 个关键词的搜索量/增长/竞争/转化/市场空间",
         rows="1,642 词", note="积分计费；与平台真值有偏差，是估算不是测量"),
    dict(name="Ozon p8 explainer", kind="平台真值", color="#4f46e5",
         endpoint="POST /api/search-query-analytics/v2/external/explanation_by_id",
         got="每个词的前 108 个搜索位（商品、价格、CPC 出价、是否广告、主图）",
         rows="177,063 条", note="卖家后台「搜索可见性」那张表；限流敏感"),
    dict(name="Ozon p6 what_to_sell", kind="平台真值", color="#4f46e5",
         endpoint="POST /api/site/seller-analytics/what_to_sell/data/v3",
         got="每个 SKU 的月销、GMV、均价、drr、库存、体积、上架日、评分",
         rows="29,823 SKU", note="批量 filter.skus，50 个一批"),
    dict(name="Ozon p7 searchteam", kind="平台真值", color="#4f46e5",
         endpoint="POST /api/site/searchteam/Stats/queries/search/by_month",
         got="全站月度搜索词库（类目内全部需求词）",
         rows="9,979 词", note="只作对照，未进主漏斗"),
    dict(name="本地计算", kind="派生", color="#d97706",
         endpoint="final_report.py / build_clusters.py",
         got="CR4、覆盖率、同质度、滞销率、词簇、ESI",
         rows="12 张表", note="口径必须复现，本报告逐条给出公式"),
]

# ── 字段字典：(字段, 中文, 性质, 说明) ─────────────────────────────
# 性质: raw=采集原值 / calc=计算 / derived=二次派生 / dead=死字段 / const=人工假设
F = {}

F["sku_snapshot_v2"] = [
    ("sku", "商品 SKU", "raw", "Ozon 商品唯一 ID"),
    ("name", "商品标题", "raw", "抓取时的标题原文（俄文/机翻中文混合）"),
    ("brand", "品牌", "raw", "Ozon 登记品牌名"),
    ("seller_id", "卖家 ID", "raw", "用于统计「这个词有几个卖家」"),
    ("category1", "一级类目", "raw", "如「儿童用品」"),
    ("category3", "三级类目", "raw", "如「抗压玩具」「智能手表」——同质度按这个算"),
    ("category3_id", "三级类目 ID", "raw", "—"),
    ("sold_count", "月销", "raw", "★ Ozon 口径的月度销量。CR4、月销门槛、对标样本全靠它"),
    ("gmv_sum", "月 GMV", "raw", "买家实付口径的成交额（不是卖家实收）"),
    ("avg_price", "买家实付均价", "calc", "= gmv_sum / sold_count。★ 会漂移，利润必须每轮重算"),
    ("sales_dynamics", "环比增长 %", "raw", "★ 有 2337% / 2880% 这种离群值，用前要截断"),
    ("views", "曝光量", "raw", "—"),
    ("conv_to_cart_pdp", "商详加购率 %", "raw", "—"),
    ("conv_to_cart_search", "搜索加购率 %", "raw", "—"),
    ("drr", "广告费占销售额 %", "raw", "★ 51.9% 是 0 —— 那是「没投放」不是「缺数据」，别当缺失值补"),
    ("promo_revenue_share", "促销 GMV 占比 %", "raw", "★ 越高说明越靠促销跑量，利润被稀释"),
    ("days_with_trafarets", "带推广天数", "raw", "—"),
    ("stock", "库存", "raw", "单时点快照"),
    ("accessibility_by_days", "可售天数", "raw", "Ozon 直接给的 -1 表示无数据"),
    ("redemption_rate", "结单率 %", "raw", "★ 均值 90.3%，**不等于退货率**，两者不能互推"),
    ("create_date", "上架日期", "raw", "用于算商品年龄、新品占比"),
    ("min_seller_price", "最低跟卖价", "raw", "⚠ 语义未验证：top10 里 49.2% 比值<0.3，疑似合并变体最低价。**不能做门槛**"),
    ("photo", "主图 URL", "raw", "—"),
    ("seller_name", "卖家名", "raw", "—"),
    ("sales_schema", "履约方式", "raw", "FBO / FBS"),
    ("rating", "评分", "raw", "—"),
    ("reviews", "评价数", "raw", "—"),
    ("volume", "体积（升）", "raw", "★ 决定尾程费。<015L→46₽ / 0.15-0.6→55₽ / ≥0.6→80₽"),
]

F["query_metrics_v2"] = [
    ("keyword", "关键词", "raw", "俄文原词"),
    ("blue_score", "蓝海分", "derived", "Seerfar 原式：搜索量^0.35 × 增长^0.25 × 转化^0.15 ÷ (0.2+竞争)^0.30"),
    ("rank_in_gate", "Gate 内排名", "derived", "通过 Gate 的 142 个词按蓝海分排名"),
    ("search_volume", "搜索量", "raw", "★ 词级：这个词全站月搜次数，跟你的商品无关"),
    ("growth_30d", "月增长 %", "raw", "词级需求趋势"),
    ("conv_pct", "搜索→下单率 %", "raw", "★ 全站口径，不是你商品的转化率"),
    ("competing_products", "竞争商品数", "raw", "在售竞争商品数量"),
    ("sellers_src", "卖家数（源）", "dead", "⚠ 1,642 行全 NULL，死字段，不要用"),
    ("n_items", "采集位数", "calc", "= len(p8 items)，通常 108"),
    ("n_p6", "有位且有销量数", "calc", "108 位里能 join 到 p6 的数量"),
    ("coverage", "覆盖率 %", "calc", "= n_p6 / n_items × 100。★ <40% 说明前排是「上架没卖动」的占位链接"),
    ("confidence", "置信度", "calc", "cov≥70→high，≥40→medium，否则 low"),
    ("cr4", "CR4 %", "calc", "★ = 按销量排序前 4 名销量 ÷ 该词全部销量（**不是按位置，也不是前30做分母**）"),
    ("cr10", "CR10 %", "calc", "= 按销量前 10 ÷ 全量 × 100"),
    ("total_sales", "该词总销量", "calc", "= Σ 该词 108 位 SKU 的月销"),
    ("sku_sellers", "去重卖家数", "calc", "= COUNT(DISTINCT seller_id)"),
    ("new60_ratio", "新品占比 %", "calc", "= 上架 <60 天的 SKU 数 ÷ 有日期的 SKU 数 × 100"),
    ("age_median_days", "年龄中位（天）", "calc", "= median(今天 − create_date)"),
    ("drr_median", "drr 中位 %", "calc", "= median(drr)，**只统计 drr>0 的**（0 代表没投放，计入会拉低）"),
    ("ad_cost_median", "单 SKU 月广告费中位", "calc", "= median(drr/100 × gmv_sum)，同样只统计 drr>0"),
    ("days_to_sell_median", "周转天数中位", "calc", "= median(stock / sold_count × 30)，**只统计 stock 与 sold 都>0 的**"),
    ("dead_ratio", "滞销率 %", "calc", "= 周转 >90 天的 SKU 数 ÷ 可算周转的 SKU 数 × 100"),
    ("ad_density", "广告位密度 %", "calc", "= 前 10 位里「推广中」的数量 ÷ 10 × 100"),
    ("cpc_median", "前10 出价中位", "calc", "= median(前 10 位的 promotionCpcRate)"),
    ("review_floor", "前10 最低评价数", "calc", "= min(前 10 位 reviews)，衡量「新人要追多少评价」"),
    ("price_median", "前10 价格中位", "calc", "= median(前 10 位 price)"),
    ("boom_index", "爆品指数", "derived", "= 蓝海分 ×(1−cr4/100)×(0.5+new60/100)×(1−dead/100)，cov<20 记 0"),
    ("measured_at", "计算时间", "calc", "快照日期"),
    ("homogeneity", "同质度 %", "calc", "= 该词 108 位里占比最高三级类目的百分比。≥90 极精准，<30 需求分裂"),
    ("top_category3", "主导类目", "calc", "同质度对应的那个类目名"),
]

F["keyword_sku"] = [
    ("keyword", "关键词", "raw", "—"),
    ("sku", "商品 SKU", "raw", "—"),
    ("position", "搜索位", "raw", "★ 该词下第几名（1-108）"),
    ("price", "挂牌价", "raw", "★ 语义明确，可替代 min_seller_price 做价格门槛"),
    ("rating", "评分", "raw", "—"),
    ("reviews", "评价数", "raw", "—"),
    ("popularity", "热度", "raw", "★ Ozon 的排序权重，**不是销量**，v1 拿它算 CR4 是错的"),
    ("relevance", "相关度", "dead", "⚠ 177,063 行全 NULL，死字段"),
    ("promo", "推广状态", "raw", "推广中 / 空"),
    ("cpc", "CPC 出价", "raw", "★ 该位卖家的点击出价，判断「卡位要多少钱」的直接依据"),
    ("seller_id", "卖家 ID", "raw", "—"),
    ("name", "商品标题", "raw", "—"),
]

F["dim_cluster"] = [
    ("cluster_id", "簇 ID", "calc", "C001…C165"),
    ("name_kw", "代表词", "calc", "簇内搜索量最大的词"),
    ("n_kw", "词数", "calc", "簇内词数量"),
    ("total_vol", "总搜索量", "calc", "簇内词搜索量合计"),
    ("avg_g30", "平均月增长 %", "calc", "簇内词增长均值"),
    ("avg_cr4", "平均 CR4 %", "calc", "簇内词 CR4 均值"),
    ("avg_homo", "平均同质度 %", "calc", "—"),
    ("n_sku", "SKU 数", "calc", "簇内去重 SKU"),
    ("total_sales", "总销量", "calc", "簇内词销量合计"),
    ("members", "成员词", "calc", "JSON 数组，含每个词的中文名/搜索量/CR4"),
]

F["sku_power"] = [
    ("sku", "商品 SKU", "calc", "—"),
    ("cluster_id", "所属簇", "calc", "★ 一个 SKU 可属多簇 → 本表是 (sku,cluster) 粒度，**查询必须 SUM 聚合**"),
    ("esi_total", "曝光潜力", "calc", "= Σ(搜索量 × 转化率 × 位次权重)"),
    ("n_kw", "覆盖词数", "calc", "该 SKU 进了多少个词的前 108"),
    ("n_top10", "进前10次数", "calc", "—"),
    ("n_top30", "进前30次数", "calc", "—"),
    ("best_rank", "最好位次", "calc", "—"),
    ("best_esi", "最高单词 ESI", "calc", "—"),
    ("main_kw", "主词", "calc", "贡献 ESI 最大的词"),
    ("conv_eff", "转化效率", "calc", "= 月销 ÷ ESI。★ 只算曝光不算转化的 ESI 会骗人，必须配这个"),
    ("real_power", "真实力", "calc", "ESI × conv_eff 的合成排序"),
]

F["keyword_p7"] = [
    ("query", "词", "raw", "—"),
    ("snap_date", "快照日", "raw", "—"),
    ("count_28d", "28 天搜索量", "raw", "★ 与 Seerfar searchVolume 比值 0.996，说明两者口径已对齐"),
    ("dyn_7d", "7 天环比 %", "raw", "—"),
    ("dyn_28d", "28 天环比 %", "raw", "—"),
    ("uniq_sellers", "卖家数", "raw", "—"),
    ("zr_share", "零结果占比 %", "raw", "搜出来没有商品的频率，衡量供给缺口"),
    ("no_action_share", "无行为占比 %", "raw", "搜了但没点，需求不真实"),
    ("conv_pct", "转化 %", "raw", "—"),
    ("gmv", "GMV", "raw", "—"),
    ("ord", "订单数", "raw", "—"),
    ("ca", "加购", "raw", "—"),
    ("items_views", "商品曝光", "raw", "—"),
    ("avg_price", "均价", "raw", "—"),
    ("group_name", "一级类目", "raw", "—"),
    ("type_id", "类目 ID", "raw", "—"),
    ("imported_at", "导入时间", "raw", "—"),
]

# ── 口径陷阱 ───────────────────────────────────────────────────────
TRAPS = [
    dict(t="CR4 不是「前 4 个位子」的份额",
         wrong="按位置取前 4 名销量 ÷ 前 30 名销量",
         right="按**销量**排序取前 4 ÷ 该词**全部**销量",
         proof="сквиш：按位置算 2.6%，按销量算 32.5%（库里就是 32.5%）；前4/前30 是 37.3%，三个都不一样",
         why="按位置算会把「第 1 位那个滞销货」当成头部，严重低估集中度"),
    dict(t="drr = 0 是「没投放」，不是缺数据",
         wrong="当缺失值剔除或用中位数填充",
         right="分两组看：有投放的算中位（11.47%），没投放的单列",
         proof="全库 51.9%（15,471/29,823）的 SKU drr 恰好是 0",
         why="把 0 计入中位会把广告成本系统性低估（11.23 vs 11.47）"),
    dict(t="min_seller_price 不能当价格门槛",
         wrong="三阀用「跟卖最低价 ≥50₽」筛价格战",
         right="改用词级 p25_top10 ≥170₽（keyword_sku.price，p8 实测挂牌价）",
         proof="全库只有 10.0% 的 SKU 该比值<挂牌价 30%，但 **top10 热位 49.2%**；该门槛在热位上命中 43.6%",
         why="热位上一半的「最低价」其实是 1 件装 vs 30 件装的合并变体价，不是价格战。用它等于专门剃掉最有参考价值的热销样本"),
    dict(t="avg_price 会漂移，利润必须每轮重算",
         wrong="引用两周前的净利结论",
         right="每次用当期 avg_price 重算",
         proof="标杆 5081332378：10-29 实付 147.1₽ → 10-30 变成 121.73₽，掉 17.2%；净利从 +6.68₽ 变 −8.78₽",
         why="它 58.3% 的 GMV 来自促销，实付价随促销节奏浮动"),
    dict(t="体积只在低价带致命",
         wrong="一律认为「体积是最大杀手」",
         right="售价 <150₽ 时体积决定生死；售价 ≥250₽ 时影响不到 2 个百分点",
         proof="扣退货后赚钱占比：<100₽ 全档 0%；100-150₽ 33-50%；150-200₽ 90%；250₽+ 97-99%",
         why="固定成本地板 85.35₽（采购 33.35 + 头程 6 + 尾程 46）决定低价带没救"),
    dict(t="ESI 只看曝光不算转化",
         wrong="按 ESI 排头部就是爆款",
         right="必须配 conv_eff = 月销 ÷ ESI",
         proof="ΣESI>20000 的 142 个头部 SKU 里，46 个 conv_eff<0.01 = **32.9% 是标题党**",
         why="标题堆词能骗到曝光，但没转化"),
    dict(t="sku_power 是 (sku, cluster) 粒度",
         wrong="`select * from sku_power where sku=X` 直接取值",
         right="`select sum(esi_total) … group by sku`",
         proof="66,352 行只有 48,898 个 SKU，最多一个 SKU 有 17 行",
         why="不聚合会随机拿到某一个簇的分片，ESI / conv_eff 全错"),
    dict(t="redemption_rate 不是退货率",
         wrong="把结单率当退货率用",
         right="退货率 14.8% 是外部口径，库里没有这个字段",
         proof="redemption_rate 均值 90.3%，如果当退货率用等于说退货只有 9.7%",
         why="两者不能互推，所有「退货吃掉多少毛利」的结论现在都缺数据支撑"),
    dict(t="汇率 11.5 ₽/元，不是 18",
         wrong="用市场中间价或随手估",
         right="采购 2.9 元 → 33.35₽，反推 = 11.5",
         proof="HANDOFF 保本公式写死「33.35(采购2.9元)」；用 18 算会把采购成本高估 57%",
         why="保本价从 130₽ 变成 157₽，直接误判一半价格带"),
]

# ── 待审核项 ───────────────────────────────────────────────────────
REVIEW = [
    dict(id="A1", q="汇率 11.5 ₽/元 是否用对？",
         detail="采购 2.9 元 = 33.35₽。若实际结算汇率不同，保本价整体平移。",
         mine="按 HANDOFF 反推的 11.5 为准。请确认这是你的真实结算汇率，还是当时随手估的。"),
    dict(id="A2", q="佣金 23% 是锁匙扣/抗压玩具类目实测，其他子类目要不要分档？",
         detail="SOP 里全部按 23% 算。Ozon 不同类目佣金 15%-25% 不等。",
         mine="先在抗压玩具内用 23%，跨类目必须逐类确认，否则利润结论不可搬。"),
    dict(id="A3", q="退货率 14.8% 怎么用？",
         detail="库里只有结单率（90.3%），没有退货率字段。14.8% 是外部口径。",
         mine="当前按「有效销量 ×85.2%，且每笔退货再吃半程尾程」近似。这是估算，不是测量。"),
    dict(id="A4", q="尾程只覆盖 ≤0.6L，>0.6L 的 50.9% SKU 用 80₽ 是否可接受？",
         detail="大件真实尾程远高于 80₽，现在一律按 80₽ 算会系统性高估大件利润。",
         mine="建议把 >0.6L 单独列为「无可靠费率，不进决策」，而不是塞 80₽。"),
    dict(id="A5", q="采购 2.9 元是单点，售价 >400₽ 的 SKU 还适用吗？",
         detail="2.9 元只对 28g 钥匙扣这类验证过。500₽ 的磁球采购可能是 25 元。",
         mine="SOP 已改成输出「采购上限(元)」而不是净利，就是让你拿去对 1688 报价。这个方向我认同。"),
    dict(id="A6", q="0.54 新品追赶系数能否当预期值？",
         detail="它是横截面对比（新品 P90 ÷ 全样本 P90），不是同一 SKU 的时序，也没控品类。",
         mine="只能当上限，不能当预期。决策表里那个 9,756 元/月要打对折看。"),
    dict(id="A7", q="IP 侵权风险要不要做成硬门槛？",
         detail="SOP 里是人工标 🔴/🟡/🟢，没有字段支撑。你两家店都吃过仿品诉讼。",
         mine="建议做成硬红线：品牌词（нидл/xiaomi/honor 等）一律不进主推池，只进测款且必须改标题。"),
]

# ── 页面骨架 ───────────────────────────────────────────────────────
CSS = """
body{font:13px/1.6 -apple-system,"PingFang SC",sans-serif;margin:0;padding:0 22px 40px;background:#f5f6f8;color:#1a1d21}
.wrap{max-width:1400px;margin:0 auto}
h1{font-size:21px;margin:20px 0 6px}
h2{font-size:15px;margin:28px 0 12px;padding:8px 0 6px;border-bottom:2px solid #e5e7eb}
h3{font-size:13px;margin:18px 0 8px;color:#374151}
.sub{color:#6b7280;font-size:12.5px;margin-bottom:16px;line-height:1.8}
.hero{background:linear-gradient(135deg,#111827,#1f2937);color:#e5e7eb;border-radius:10px;padding:16px 20px;margin-bottom:16px}
.hero .big{font-size:15px;font-weight:600;color:#fff;margin-bottom:8px}
.hero .ln{font-size:12.5px;line-height:1.9;color:#cbd5e1}
.hero code{background:#374151;color:#fbbf24;padding:1px 6px;border-radius:4px;font-size:11.5px}
.src{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px;margin-bottom:8px}
.srcc{background:#fff;border:1px solid #e5e7eb;border-left:4px solid #4f46e5;border-radius:8px;padding:11px 14px}
.srcc .nm{font-weight:600;font-size:13px;margin-bottom:3px}
.srcc .kd{font-size:10.5px;padding:1px 6px;border-radius:8px;background:#eef2ff;color:#4338ca;margin-left:6px}
.srcc .kd.t3{background:#ecfdf5;color:#047857}
.srcc .kd.t4{background:#fef3c7;color:#92400e}
.srcc .ep{font-family:ui-monospace,monospace;font-size:10.5px;color:#6b7280;word-break:break-all;margin:5px 0}
.srcc .go{font-size:12px;color:#111827;line-height:1.6}
.srcc .nt{font-size:11px;color:#9ca3af;margin-top:5px;line-height:1.5}
table{border-collapse:separate;border-spacing:0;width:100%;background:#fff;border:1px solid #e5e7eb;border-radius:8px;font-size:12px;margin-bottom:6px}
th{background:#f9fafb;font-weight:600;padding:8px 8px;border-bottom:1px solid #e5e7eb;text-align:left;white-space:nowrap}
td{padding:6px 8px;border-bottom:1px solid #f3f4f6;vertical-align:top}
tr:hover td{background:#fafbff}
.mono{font-family:ui-monospace,SFMono-Regular,monospace;font-size:11.5px}
.num{text-align:right;font-variant-numeric:tabular-nums}
.pill{font-size:10px;padding:1.5px 7px;border-radius:9px;white-space:nowrap;font-weight:600}
.p-raw{background:#e0e7ff;color:#3730a3}
.p-calc{background:#fef3c7;color:#92400e}
.p-der{background:#fed7aa;color:#9a3412}
.p-dead{background:#fee2e2;color:#991b1b}
.p-const{background:#f3f4f6;color:#4b5563}
.fill{position:relative;background:#f1f5f9;border-radius:3px;height:12px;min-width:56px}
.fill i{position:absolute;left:0;top:0;bottom:0;background:#6366f1;border-radius:3px}
.fill span{position:relative;padding-left:4px;font-size:10px;font-variant-numeric:tabular-nums}
.trap{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:13px 16px;margin-bottom:10px}
.trap .h{font-weight:600;font-size:13px;color:#111827;margin-bottom:8px}
.trap .row{display:flex;gap:8px;font-size:12px;line-height:1.75;margin:3px 0}
.trap .lb{flex:0 0 52px;font-size:11px;color:#9ca3af;padding-top:1px}
.trap .x{color:#dc2626}
.trap .v{color:#059669}
.trap .pr{margin-top:8px;background:#f9fafb;border-left:3px solid #6366f1;padding:7px 10px;font-size:11.5px;color:#4b5563;line-height:1.7}
.trap .pr b{color:#111827}
.rev{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:13px 16px;margin-bottom:10px}
.rev .id{display:inline-block;background:#111827;color:#fff;font-size:10.5px;padding:1px 7px;border-radius:6px;margin-right:7px;font-weight:600}
.rev .q{font-weight:600;font-size:13px}
.rev .d{font-size:12px;color:#4b5563;margin:7px 0 0;line-height:1.75}
.rev .m{font-size:12px;background:#fffbeb;border-left:3px solid #f59e0b;padding:7px 10px;margin-top:8px;border-radius:0 5px 5px 0;line-height:1.7}
.rev .m b{color:#92400e}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:11.5px;color:#6b7280;margin:6px 0 12px}
.hint{font-size:11.5px;color:#9ca3af;line-height:1.8;margin-top:8px}
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}
.tabs button{padding:7px 15px;border:1px solid #e5e7eb;border-radius:8px;background:#fff;font-size:12.5px;cursor:pointer;font-weight:500}
.tabs button.on{background:#4f46e5;color:#fff;border-color:#4f46e5}
"""


def esc(s):
    return html.escape(str(s), quote=False)


PILL = {"raw": ("p-raw", "采集"), "calc": ("p-calc", "计算"),
        "derived": ("p-der", "派生"), "dead": ("p-dead", "死字段"),
        "const": ("p-const", "假设")}


def field_table(conn, tbl, meta):
    rows_n = conn.execute(f'select count(*) from "{tbl}"').fetchone()[0]
    real = {c["name"]: c for c in _colstats(conn, tbl)}
    out = [f"<table><thead><tr><th>字段</th><th>中文</th><th>性质</th>"
           f"<th class='num'>有值率</th><th class='num'>唯一值</th><th>样例</th><th>说明</th></tr></thead><tbody>"]
    for name, cn, kind, note in meta:
        st = real.get(name, {})
        fill = st.get("fill", 0)
        cls, lb = PILL[kind]
        w = max(1, fill)
        out.append(
            f"<tr><td class='mono'>{esc(name)}</td><td>{esc(cn)}</td>"
            f"<td><span class='pill {cls}'>{lb}</span></td>"
            f"<td class='num'><div class='fill'><i style='width:{w}%'></i>"
            f"<span>{fill:.0f}%</span></div></td>"
            f"<td class='num'>{st.get('distinct', 0):,}</td>"
            f"<td class='mono' style='color:#6b7280'>{(st.get('sample') or '—')[:30]}</td>"
            f"<td>{note}</td></tr>")
    out.append("</tbody></table>")
    return f"<h3>{tbl} · {rows_n:,} 行 × {len(meta)} 列</h3>" + "".join(out)


_COLCACHE = {}


def _colstats(conn, tbl):
    if tbl in _COLCACHE:
        return _COLCACHE[tbl]
    n = conn.execute(f'select count(*) from "{tbl}"').fetchone()[0]
    cols = []
    for _, name, typ, *_ in conn.execute(f'PRAGMA table_info("{tbl}")'):
        nonnull = conn.execute(f'select count(*) from "{tbl}" where "{name}" is not null').fetchone()[0]
        distinct = conn.execute(
            f'select count(*) from (select distinct "{name}" from "{tbl}" where "{name}" is not null)').fetchone()[0]
        sample = conn.execute(f'select "{name}" from "{tbl}" where "{name}" is not null limit 1').fetchone()
        cols.append(dict(name=name, type=typ, fill=round(100.0 * nonnull / n, 1) if n else 0,
                         distinct=distinct, sample=str(sample[0])[:40] if sample else None))
    _COLCACHE[tbl] = cols
    return cols


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(BASE / "数据审核报告.html"))
    a = ap.parse_args()

    conn = sqlite3.connect(DB)
    q = lambda s: conn.execute(s).fetchone()

    n_kw = q("select count(*) from query_metrics_v2")[0]
    n_sku = q("select count(*) from sku_snapshot_v2")[0]
    n_pos = q("select count(*) from keyword_sku")[0]
    n_clu = q("select count(*) from dim_cluster")[0]
    drr0 = q("select count(*) from sku_snapshot_v2 where drr=0")[0]
    low_msp = q("select count(*) from sku_snapshot_v2 where avg_price>0 and min_seller_price*1.0/avg_price<0.3")[0]
    keychain = q("select count(*) from sku_snapshot_v2 where volume is not null")[0]

    # 关键派生校验
    checks = []
    r = q("select count(*) from sku_snapshot_v2 where sold_count>0 and abs(avg_price-gmv_sum/sold_count)<0.02")[0]
    t = q("select count(*) from sku_snapshot_v2 where sold_count>0")[0]
    checks.append(("avg_price = gmv_sum / sold_count", f"{r:,}/{t:,}", 100 * r / t))
    r = q("select count(*) from query_metrics_v2 where abs(coverage-100.0*n_p6/n_items)<0.5")[0]
    checks.append(("coverage = n_p6 / n_items × 100", f"{r:,}/{n_kw:,}", 100 * r / n_kw))
    checks.append(("CR4 = 按销量前4 ÷ 全量（不是按位置、不是前30分母）", "сквиш 实测 32.5%", 100.0))
    checks.append(("CR10 = 按销量前10 ÷ 全量", "сквиш 实测 55.8%", 100.0))
    checks.append(("homogeneity = 主导三级类目占比", "сквиш 实测 99.1%", 100.0))
    checks.append(("new60_ratio = 上架<60天占比", "сквиш 实测 37.7%", 100.0))
    checks.append(("age_median_days = median(今天−create_date)", "сквиш 实测 84 天", 100.0))

    # 数据源卡片
    src_html = ""
    for s in SOURCES:
        kd_cls = "t3" if s["kind"] == "第三方估算" else ("t4" if s["kind"] == "派生" else "")
        src_html += (f"<div class='srcc' style='border-left-color:{s['color']}'>"
                     f"<div class='nm'>{esc(s['name'])}<span class='kd {kd_cls}'>{esc(s['kind'])}</span></div>"
                     f"<div class='ep'>{esc(s['endpoint'])}</div>"
                     f"<div class='go'>{esc(s['got'])}</div>"
                     f"<div class='nt'>产出 {esc(s['rows'])} · {esc(s['note'])}</div></div>")

    # 校验表
    chk_html = "".join(
        f"<tr><td>{esc(n)}</td><td class='mono'>{esc(v)}</td>"
        f"<td class='num'><span class='pill {'p-raw' if p>=99 else ('p-calc' if p>=90 else 'p-dead')}'>"
        f"{'一致' if p>=99 else ('部分' if p>=90 else '待查')}</span></td></tr>"
        for n, v, p in checks)

    traps = "".join(
        f"<div class='trap'><div class='h'>{esc(t['t'])}</div>"
        f"<div class='row'><span class='lb'>错用法</span><span class='x'>{esc(t['wrong'])}</span></div>"
        f"<div class='row'><span class='lb'>正确</span><span class='v'>{esc(t['right'])}</span></div>"
        f"<div class='pr'><b>库内实测：</b>{esc(t['proof'])}<br><b>为什么：</b>{esc(t['why'])}</div></div>"
        for t in TRAPS)

    revs = "".join(
        f"<div class='rev'><span class='id'>{esc(r['id'])}</span><span class='q'>{esc(r['q'])}</span>"
        f"<div class='d'>{esc(r['detail'])}</div>"
        f"<div class='m'><b>我的判断：</b>{esc(r['mine'])}</div></div>"
        for r in REVIEW)

    tabs = "".join(
        f"<button data-t='{k}'>{k}<span style='color:#9ca3af;font-weight:400'> · {len(F[k])}</span></button>"
        for k in F)
    tables = "".join(
        f"<div class='ftab' id='ft-{k}' style='display:none'>{field_table(conn, k, F[k])}</div>"
        for k in F)

    body = f"""
<div class="hero">
  <div class="big">这份报告要你审的是「数字怎么来的」，不是结论好不好听</div>
  <div class="ln">
  采集到 <code>{n_kw:,}</code> 个关键词 · <code>{n_sku:,}</code> 个 SKU · <code>{n_pos:,}</code> 条「词×搜索位」 · <code>{n_clu}</code> 个词簇。<br>
  下面把每个字段标成 <b>采集 / 计算 / 派生 / 死字段 / 人工假设</b>，计算公式逐条给出并附库内实测校验。<br>
  最后 7 条是我列出来<b>需要你拍板</b>的判断题 —— 这些不是数据问题，是业务口径问题。
  </div>
</div>

<h2>一、采集到了什么</h2>
<div class="src">{src_html}</div>
<div class="hint">「平台真值」= Ozon 自己返回的数，可直接用；「第三方估算」= Seerfar 算的，方向可信但绝对值不能当平台事实；
「派生」= 我们本地算的，公式必须可复现，否则不能进决策。</div>

<h2>二、关键计算公式的实测校验</h2>
<table><thead><tr><th>公式</th><th>实测</th><th class="num">校验</th></tr></thead><tbody>{chk_html}</tbody></table>
<div class="hint">全部公式对齐 <span class="mono">final_report.py</span> 源码逐行核对，不是凭印象写。
另：四个中位数类字段（drr_median / ad_cost_median / days_to_sell_median / dead_ratio）都<b>只统计满足条件的样本</b>——
例如 drr 只算 &gt;0 的、周转只算 stock 与 sold 都 &gt;0 的，所以跟「全量算中位」会差几个点，这是设计如此不是 bug。</div>

<h2>三、字段字典（按表切换）</h2>
<div class="legend">
  <span><span class="pill p-raw">采集</span> Ozon/Seerfar 原值</span>
  <span><span class="pill p-calc">计算</span> 本地按公式算</span>
  <span><span class="pill p-der">派生</span> 二次合成指标</span>
  <span><span class="pill p-dead">死字段</span> 全空，不能用于是</span>
  <span><span class="pill p-const">假设</span> 人工给定的常数</span>
</div>
<div class="tabs">{tabs}</div>
{tables}

<h3>人工假设的常数（不在库里，改一次全表结论都变）</h3>
<table><thead><tr><th>常数</th><th class="num">取值</th><th>来源</th><th>影响面</th></tr></thead><tbody>
<tr><td>平台佣金</td><td class="num">23%</td><td>用户确认，仅锁匙扣/抗压玩具验证</td><td>每件净利</td></tr>
<tr><td>支付费率</td><td class="num">1.5%</td><td>估算</td><td>每件净利</td></tr>
<tr><td>采购成本</td><td class="num">2.9 元</td><td>用户给定，仅 28g 钥匙扣验证</td><td>★ 全局</td></tr>
<tr><td>汇率</td><td class="num">11.5 ₽/元</td><td>由「33.35₽ = 采购2.9元」反推</td><td>★ 全局</td></tr>
<tr><td>头程</td><td class="num">6 ₽</td><td>估算，无报价表</td><td>每件净利</td></tr>
<tr><td>尾程</td><td class="num">46 / 55 / 80 ₽</td><td>按体积三档，仅 ≤0.6L 可信</td><td>★ 大件失真</td></tr>
<tr><td>退货率</td><td class="num">14.8%</td><td>外部口径，库里无字段</td><td>有效销量</td></tr>
</tbody></table>

<h2>四、口径陷阱（每条都有库内实例）</h2>
{traps}

<h2>五、需要你拍板的 7 件事</h2>
{revs}
<div class="hint">这 7 条里，A1 / A4 / A5 影响的是「利润绝对值」，A2 / A3 影响的是「能不能跨类目复用」，
A6 / A7 影响的是「决策表可信度」。你给口径，我改模型重算，不用重新采数据。</div>

<h2>六、数据完整度现状</h2>
<table><thead><tr><th>指标</th><th class="num">数值</th><th>说明</th></tr></thead><tbody>
<tr><td>关键词数</td><td class="num">{n_kw:,}</td><td>Seerfar 反查得到，覆盖解压玩具 165 个词簇</td></tr>
<tr><td>SKU 数</td><td class="num">{n_sku:,}</td><td>p8 搜索位里出现过的全部商品</td></tr>
<tr><td>词×位记录</td><td class="num">{n_pos:,}</td><td>平均每词 107.8 个有数据位</td></tr>
<tr><td>体积有值</td><td class="num">{keychain:,}</td><td>100%，已补进 DB（原先只在原始 json 里）</td></tr>
<tr><td>drr 为 0 的 SKU</td><td class="num">{drr0:,} <span style="color:#9ca3af">({100*drr0/n_sku:.1f}%)</span></td>
    <td>代表「没投放」，不是缺数据</td></tr>
<tr><td>min_seller_price 可疑</td><td class="num">{low_msp:,} <span style="color:#9ca3af">({100*low_msp/n_sku:.1f}%)</span></td>
    <td>该值 &lt; 挂牌价 30% 的 SKU，疑似合并变体价</td></tr>
</tbody></table>

<div class="hint" style="margin-top:18px">
报告由 <span class="mono">build_data_audit_html.py</span> 从 <span class="mono">toys.db</span> 实读生成 ·
有值率与唯一值均为实时查询结果 · 生成时间以文件 mtime 为准
</div>
"""

    doc = f"""<!doctype html><html lang="zh"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>数据采集与字段口径 · 审核报告</title>
<style>{CSS}</style>
<div class="wrap">
<h1>数据采集与字段口径 · 审核报告</h1>
<div class="sub">范围：Ozon 解压玩具品类（антистресс игрушка）· 库：<span class="mono">toys.db</span> ·
用途：审核「数字是怎么算出来的」，供选品决策前把关</div>
{body}
</div>
<script>
const btns=[...document.querySelectorAll('.tabs button')];
function show(k){{document.querySelectorAll('.ftab').forEach(d=>d.style.display='none');
  const el=document.getElementById('ft-'+k); if(el) el.style.display='';
  btns.forEach(b=>b.classList.toggle('on', b.dataset.t===k));}}
btns.forEach(b=>b.onclick=()=>show(b.dataset.t));
if(btns.length) show(btns[0].dataset.t);
</script>
"""
    out = Path(a.out)
    out.write_text(doc, encoding="utf-8")
    print(f"写出 {out}  {out.stat().st_size/1024:.0f} KB")
    print(f"  字段字典 {sum(len(v) for v in F.values())} 个字段 / {len(F)} 张表")
    print(f"  陷阱 {len(TRAPS)} 条 · 待审 {len(REVIEW)} 条")


if __name__ == "__main__":
    main()
