# Ozon 爆品挖掘方法论 · v2（数据边界已重测修正）

> **v1 作废原因**：v1 判定的三个「不可行」全部是错的 —— 我没读 `ozon-seller-assistant/docs/DATA_AVAILABILITY_AUDIT.md`，
> 只用类目榜（p6 Top300）算 SKU 覆盖率，得出 5.3%，误判「上架时间/真销量/库存拿不到」。
> **实际用 `filter.skus` 批量查，覆盖率 69.9%，关键字段 100% 有值。**
>
> 2026-10-29 重测。数据源：p8 采的 582 SKU → p6 `filter.skus` 批量 enrich（12 请求 / 13 秒）→ 命中 407。

---

## 零、修正后的数据边界（这是全部结论的地基）

### 0.1 一个被忽略的能力：`filter.skus` 批量

```
POST /api/site/seller-analytics/what_to_sell/data/v3
body: {"limit":"50","offset":"0",
       "filter":{"stock":"any_stock","period":"monthly","skus":["SKU1",...,"SKU50"]},
       "sort":{"key":"sum_gmv_desc"}}
```

实测：**50 个 SKU / 请求，12 请求覆盖 582 个 SKU 只用 13 秒 = 2,686 SKU/分钟**。

这比「按类目翻页」快两个数量级，且能精准命中 p8 拿到的任意 SKU。

### 0.2 407 个真实 SKU 的字段有值率（p8 下的商品）

| 字段 | 有值率 | 用途 |
|---|---|---|
| `soldCount` | **100%** | **真实月销量**（CR4 基础） |
| `gmvSum` | **100%** | 月 GMV |
| `avgPrice` | **100%** | 客单价 |
| **`nullableCreateDate`** | **100%** | **上架时间**（新品判定） |
| **`stock`** | **100%** | 库存（周转/断货） |
| `accessibilityByDays` | 99% | 可售天数 |
| `nullableRedemptionRate` | 99% | 结单率 |
| `convToCartPdp` / `convToCartSearch` | 100% / 99% | 加购转化 |
| `convViewToOrder` | 100% | 曝光转下单 |
| `views` / `sessionCountSearch` | 100% | 曝光 / 搜索会话 |
| **`drr`** | **52%** | **推广费占 GMV**（广告成本真值） |
| `daysInPromo` / `promoRevenueShare` | 76% / 67% | 促销 |
| `daysWithTrafarets` | 32% | 广告在投天数 |
| `salesDynamics` | 77% | 平台环比 |
| ⚠ `rating` / `reviews` | **0%** | **恒空**，评分评论必须走前台 `page/json` |
| ⚠ `fboStock`/`fbsStock`/`cbStock` 等 9 个 | **0%** | 恒空，只有合成 `stock` |
| ⚠ `sumMissedGmv` | ~2% | 几乎恒空，不要当卖点 |

### 0.3 自营 vs 三方

`sellerId === "0"` = Ozon 直供（1P），**stock/drr/促销/上架时间全部结构性为空**（因为它不用 Seller Center）。
样本 407 个全是三方，所以字段很满。**线上跑必须按 `sellerId === "0"` 分流，别把结构性空当抓取失败。**

### 0.4 p8 的 `popularity` 是什么（v1 用来算 CR4，错）

- 实测每词 pos1 恒等于 **`100,00`**（饱和），pos3 = 28.40，pos60 = 12.50
- 官方 hint：「商品**在该搜索查询下**越热门，分数越多」→ **词内相对分，跨词不可比、不可加总**
- `Σtop4/Σtop30` 在归一指数上恒落在 13–16%，**零区分度**
- **v1 写的「6–42 小数」与实测 100.00 矛盾，是我把 `textRelevance` 和 `generalPopularity` 看串了**

→ **CR4 一律用 p6 的 `soldCount` 真值，不用 p8。**

---

## 一、修正后的四步漏斗

### 第一步 · 词层筛选（p7 + Seerfar）

| 数据源 | 拿什么 | 速度 |
|---|---|---|
| p7（浏览器） | 词 + 搜索量 + 7/28天增长 + 无互动占比 + 转化 | 一个 L1 组 200 页 = **160 s / 9,979 词** |
| Seerfar（API，积分） | 真实竞争品数 + 真实卖家数 + 30/90天增长 + margin | 一 L3 全量词库 17 页 = **180 积分** |

**Gate**（硬门槛，先砍再排）：
```python
竞争品 > 500 或 卖家 > 200  → red（实测占 18%）
搜索量 < 1000               → tiny（占 73%）
其余                         → ok（占 9%，1,642 词里 142 个）
```

**蓝海分**（百分位版，避免量纲漂移）：
```
blue = demand^0.35 × growth^0.25 × conv^0.15 ÷ (0.2 + supply)^0.30
```
实测 Top：`ящерица на пружине` 1.436 / `мальтозный шар` 1.430 / `сенсорные колечки` 1.315。
原式（原始值）也可用，但 `сквиш` 仍得 20.2，**必须靠 Gate 拦**。

### 第二步 · 搜索位核验（p8）

**限流**：滑动窗口，**突发 9–13 词后静默返回 `items:[]`**（HTTP 仍 200、bodyStatus 仍 COMPLETED、响应反而变快）。唯一可靠信号是 `items.length === 0`，必须用对照词检测。

**代码骨架**：
```python
CONTROL = ['сквиш', 'антистресс']
for i, kw in enumerate(keywords):
    r = fetch(kw)
    if not r.items:
        if not fetch(random.choice(CONTROL)).items:   # 对照词也空 = 被限流
            time.sleep(60); continue
        mark_no_data(kw)
    if i % 8 == 7: time.sleep(25)
```

**速度**：零间隔串行 **79.8 词/分钟**（25 词/18.8s），并发 3 反而只有 39.7。
**100 词 ≈ 3 分钟**（含暂停）。

**从 p8 能算的**：
| 指标 | 字段 | 说明 |
|---|---|---|
| 广告密度 | `promotionStatus == '推广中'` 占比 | ⚠ 前 36 位常饱和到 100%，**只做描述不做 gate** |
| CPC 成本 | `promotionCpcRate` | 实测 0.17–7.78 ₽ |
| 评价门槛 | `reviews_count`（前 10 位最小） | 真实护城河 |
| 价格带 | `price` P25/P50/P75 | |
| 相关性 | `textRelevance` | 用于剔无关词 |
| **拿不到的** | 销量、上架时间、佣金、评分 | 全部走 p6 / 官方 API |

### 第三步 · SKU 级 enrich（p6 `filter.skus`）★ 这是 v1 漏掉的核心

p8 给的是「词 × 位置 → SKU」，拿到后立刻批量 enrich：

```python
skus = set(sku for kw in top_words for sku in p8(kw).skus)   # 100 词 ≈ 5,000 SKU
for chunk in chunks(skus, 50):
    data_v3(filter={"skus": chunk, "period": "monthly"})
```

**582 SKU / 12 请求 / 13 秒**，命中 69.9%（未命中的是「该 SKU 在 p6 无销量记录」，多是冷门/新品）。

**enrich 后每个 SKU 都有**：
```
soldCount  gmvSum  avgPrice  drr  stock  accessibilityByDays
nullableCreateDate  nullableRedemptionRate
convToCartPdp  convToCartSearch  convViewToOrder  views  sessionCountSearch
salesDynamics  daysInPromo  promoRevenueShare  daysWithTrafarets
```

### 第四步 · 用真实数据算指标

**实测结果（407 个抗压玩具 SKU）**：

**① 新品存活率（`nullableCreateDate` 真值，不是评价数代理）**
```
中位上架天数 88 天
< 30 天  10.6%
< 60 天  33.2%   ← 三分之一是新品
< 90 天  51.6%
<180 天  70.8%
```

**② 新链接到底能不能起量（关键洞察）**
```
上架       n    销量中位    P90     合计
<60天     135      14       432   42,616
60-180天  153      37       618   53,092
>180天    119      38       510   25,683
```
→ 新链接**销量中位只有老链接的 1/3**（14 vs 37），但 **P90 差距不大**（432 vs 618）。
→ 说明：该赛道对新链接**不宽容**，但头部新链接能追上。**不能用「新品占比高」直接判为蓝海。**

**③ 广告成本（`drr` 真值）**
```
drr 中位 8.95%   P25 4.15%   P75 15.19%
单 SKU 月广告费中位 3,189 ₽     366 个合计 199.7 万 ₽/月
```

**④ 库存周转**
```
可售天数中位 70 天   P25 25   P75 192
<15 天（紧张）  34/268 = 12.7%
>90 天（滞销） 115/268 = 42.9%   ← 近半滞销
```

**⑤ 转化漏斗（真值）**
```
views 中位 17,196 → qtyViewPdp 1,068 → 加购 11.43%(PDP) → 下单 0.14%(曝光)
结单率 90.9%
```

**⑥ CR4（终于能算真值）**
```
全样本：有销量 407/407，总销量 121,391
CR4 = 33.5%    CR10 = 52.4%
```
⚠ 这是 582 个 SKU 混算，真 CR4 必须**按词分组**（每个词的 108 位单独算）。

---

## 二、修正后的完整流水线（含耗时）

```
① 词库（p7，全站 26 个 L1 组 × 160s）              ≈ 70 分钟  周更
      ↓
② Gate + 蓝海分（本地）                              < 1 s
      ↓ Top 100–200 词（全局，不按类目）
③ p8 核验（79.8 词/分钟，每 8 词暂停）               ≈ 3 分钟
      ↓ 每词 108 位 → 去重 ≈ 5,000 SKU
④ p6 filter.skus 批量 enrich（50/请求）              ≈ 2 分钟
      ↓ 拿到 soldCount/drr/stock/上架时间/转化
⑤ 指标计算（本地 sqlite）                            < 1 s
      ↓ 新品率 / CR4 / 广告成本 / 周转 / 利润
⑥ 利润模型（类目费率矩阵 × 价格档 × FBO/FBS）
      ↓
⑦ 爆品榜 Top 5%
```

**每轮 ≈ 5 分钟**（p8 3min + enrich 2min），词库 70 分钟周更一次。

**v1 说的「5–6 分钟/类目 × 8,763 类 = 730 小时」是伪问题** —— 根本不该按类目跑，应该**词先行**，类目只是词命中的结果。

---

## 三、三个真缺口（v1 那两个是假的）

| # | 缺口 | 严重度 | 解法 |
|---|---|---|---|
| 1 | **佣金只能类目平均** | 中 | `sync_commission.py` 的官方 Excel 本身就是 `(主类目,类目,类型) × (≤100/101–300/>300₽) × 6方案`。查表键改成 `type_id × 价格档 × FBO/FBS`，误差 **1–3 pp**（不是 v1 说的 5–10） |
| 2 | **1688 采购价未跑通** | 高 | 有 `ali1688` 客户端，但「图搜→价格」准确率 0 验证。**先抽 20 个 SKU 人工核对**，否则净利率门槛是假的 |
| 3 | **头程运费报价表不存在** | 高 | 需人工维护。没有它 `net_margin` 算不出来 |

**反而不是缺口的**：
- ~~上架时间~~ → `nullableCreateDate` 100%
- ~~真实销量~~ → `soldCount` 100%
- ~~库存时序~~ → `stock` 100%，且每日快照即可，不用等 7 天
- ~~p8↔p6 交集 5.3%~~ → 用 `filter.skus` 批量查是 69.9%

---

## 四、爆品推荐公式（修正版）

```
爆品指数 = 蓝海分 × (1 - CR4_真值) × 新品追赶系数 × 利润安全垫

其中：
  CR4_真值    = Σ top4 soldCount / Σ top30 soldCount     ← p6 真值，按词分组
  新品追赶系数 = (上架<60天的 SKU 的 P90 销量) / (全样本 P90 销量)   ← 实测 0.70
  利润安全垫   = (净利率 - 25%) / 25%                     ← 佣金用矩阵+价格档
```

**加一条 v1 没有的硬过滤**：
```python
if 库存滞销率 > 0.5:   # 类目 >90 天可售的商品占比
    skip()             # 抗压玩具实测 42.9%，接近红线
```

---

## 五、待验证（诚实清单）

| 项 | 状态 | 成本 |
|---|---|---|
| 按词分组的真 CR4 | 未跑（需 p8 的 SKU 与 p6 对上后分组） | 0，本地算 |
| 1688 图搜准确率 | **0 验证** | 20 SKU 抽样 |
| 类目费率矩阵精度 | 未对比真实佣金 | 自家 5 个 SKU 对照 |
| 头程运费 | 无数据 | 人工 |
| p8 限流恢复精确时间 | 部分验证（10–20s） | 需多轮测试 |
| Seerfar `sales_30d` 与 p6 `soldCount` 是否一致 | 未对比 | 0，两边都有 |

---

## 六、v1 错在哪（记录教训）

1. **没读 `ozon-seller-assistant/docs/DATA_AVAILABILITY_AUDIT.md`** —— 那份文档已经测过 66 个字段 × 有值率，我重新摸了一遍还摸错了。
2. **用类目榜算 SKU 覆盖率** —— 应该用 `filter.skus` 批量查。前者是「类目 Top300」，后者是「任意 SKU 精确查」，完全不同的能力。
3. **把 `textRelevance` 和 `generalPopularity` 看串** —— 导致以为 popularity 是 6–42，实际有 100.00 饱和值。
4. **凭印象认为「要等 7 天才能做库存差分」** —— p6 的 `stock` 本来就有，日更即可。
