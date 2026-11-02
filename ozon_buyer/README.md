# Ozon 买家端前台采集模块 (`ozon_buyer`)

> **定位**：Ozon 买家端前台 (`www.ozon.ru`) 纯 Python 高并发采集器。
> **凭据机制**：免登录，利用轻量 CDP 自动过挑战预热匿名 Cookie（或直接读本地浏览器），结合 `curl_cffi` 伪装 Chrome 124 TLS/JA3 指纹直打。
> **架构设计**：**独立原生集成，无需嵌套 Git (No Submodule)**，与卖家后台采集模块 (`ozon_seller`) 保持风控物理隔离。

---

## 一、 核心采集能力与端点

| 能力维度 | 底层端点 / 协议 | 核心产出字段 |
|---|---|---|
| **商品搜索 / 类目** | `GET /api/entrypoint-api.bx/page/json/v2?url=/search/...` | 商品标题、现价/原价/折扣、**`stock_max` 真实可用物理库存 (100%覆盖)**、**`advertLite` 搜索广告位标记**、动态分页游标 |
| **SKU 详情与规格** | `GET /product/<sku>/` (P1) + `pdpPage2column&page=2` (P2) | 价格三件套（Ozon卡价/普通价/原价）、**变体全家桶矩阵 (`webAspects`)**、全量属性表 (`webCharacteristics`)、长图文富文本 HTML (`webDescription`)、当前在售店铺与单量徽标 |
| **买家评价与排雷** | `GET /product/<sku>/reviews/?reviewsVariantMode=2&sort=score_asc` | **真翻页无重叠**；`score_asc` 直接置顶 1 星差评；评价星级 (1~5)、主评文案、结构化优缺点 (`positive`/`negative`)、买家实拍图集、点赞数 |
| **同款跟卖商全景** | `GET /modal/otherOffersFromSellers?product_id=<sku>&sort=price` | 提取 110+ 家跟卖商名录：**企业法定主体全称、ОГРН / ОГРНИП 注册号、注册国家与城市**、跟卖到底报价、承诺配送时效 |
| **大促抢购库存** | `PDP -> bigPromoPDP` | 大促剩余件数 (`stockNumber` 如 `"172 шт."`) 与已售百分比 (`percentage` 如 `81%`) |

---

## 二、 架构原则：为什么不需要嵌套 Git？

1. **零依赖与解耦**：
   - 避免使用 Git Submodule 或二级子仓，防止检出时的 detached HEAD、版本脱节和 CI/CD 权限配置阻碍。
   - 所有 Python 代码平铺纳入 `ozon-seller-kit` 的 `ozon_buyer/` 包中，原生受主仓 Git 统一版本管理。
2. **风控完全隔离**：
   - `ozon_seller` 绑死真实店铺 Cookie (`company_id: 5149811`)，严禁高并发；
   - `ozon_buyer` 使用匿名会话，最高可开 24 线程并发冲击 100~200 SKU/s。哪怕买家端 Cookie 触发 403 频控，8 秒重开一个即可，**绝对不会连带影响卖家端店铺安全**。
3. **数据数仓融合**：
   - 采集层解耦，中间分析层通过 `sku` 作为统一主键做 `LEFT JOIN`，把买家前台的 `stock_max`（真实物理库存）与卖家后台的 `soldCount`（真实月销）、`drr`（广告费率）融合成一张决策宽表。

---

## 三、 Python 编程调用方式

```python
from ozon_buyer import BuyerClient

# 1. 初始化客户端（自动探测本机 Chrome/Edge 及 Clash/Verge 代理端口）
client = BuyerClient()

# 2. 搜索关键词（抓取 2 页，返回包含 stock_max 真实库存的商品列表）
items = client.search(keyword="сквиш лапка", pages=2)
for it in items[:5]:
    print(f"SKU: {it['sku_id']} | 标题: {it['title'][:30]} | 价格: {it['price']} | 物理库存: {it['stock_max']}")

# 3. 单个 SKU 详情画像（抓取变体全家桶、价格、属性与富文本）
detail = client.sku_detail("5527434733")
print("Ozon 卡价:", detail.get("card_price"))
print("变体数量:", len(detail.get("variants", [])))
print("属性参数:", detail.get("characteristics", [])[:3])

# 4. 买家评价采集（按差评排序，排查产品质量缺陷）
reviews = client.sku_reviews("5081332378", pages=2, sort="score_asc")
for r in reviews["reviews"]:
    print(f"[{r['score']}星] 买家: {r['author']} | 差评反馈: {r['negative'] or r['comment']}")

# 5. 同款跟卖商工商资质拆解
sellers = client.other_offers("5527434733")
for s in sellers[:5]:
    print(f"店铺: {s['seller_name']} | 公司: {s['company_name']} | 注册号(ОГРН): {s['reg_number']} | 报价: {s['price']}")
```

---

## 四、 命令行 (CLI) 快速执行

```bash
# 1. 关键词搜索 + 抓取 2 页 + 提取店铺与库存 + 1 星差评排雷
python3 scripts/collect_buyer.py --keyword "пеньюар кружевной" --pages 2 --threads 8 --reviews 1 --sort score_asc --out data/buyer_search.json

# 2. 针对指定 SKU 清单批量核查物理库存与差评
python3 scripts/collect_buyer.py --sku 5081332378 --sku 5527434733 --reviews 2 --sort score_asc --out data/sku_audit.json

# 3. 按文件批量查 SKU（每行一个）
python3 scripts/collect_buyer.py --file data/skus.txt --threads 8 --out data/batch_result.json
```
