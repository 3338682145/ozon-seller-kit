# 已识别的采集端点与输入契约

| source_id | 方法 / endpoint | 输入与授权 | 分页 | 实现证据 / 现状 |
|---|---|---|---|---|
| seller_p6 | POST `seller.ozon.ru/api/site/seller-analytics/what_to_sell/data/v3` | `filter.stock=any_stock`、`period=weekly/monthly`、`skus?`、`offset`、`limit`、GMV 排序；已授权店铺会话 | offset+limit，原脚本 50/页 | `ozon_seller/api.py:251-264`；已有实现 |
| seller_p8 | POST `seller.ozon.ru/api/search-query-analytics/v2/external/explanation_by_id` | `sellerId`、`query`、`uuid`、`skus`、`sortOption`、`itemsPerPage=108`、`pageNumber=1`、scope；Seller 会话 | 源码只请求第一页；不能假设其它页有效 | `ozon_seller/api.py:228-248`；已有实现 |
| seller_cjm | POST `seller.ozon.ru/api/search-query-analytics/v1/cjm/get-seller-analytics` | `seller_id`、时间范围、排序、filters、page_number、items_per_page | 原函数请求 0 页并返回 `totalPagesCount`，全量循环未实现 | `ozon_seller/api.py:267-298` |
| seller_cjm_headers | GET `seller.ozon.ru/api/search-query-analytics/v1/cjm/get-seller-analytics-table-headers?seller_id=...` | Seller 会话 | 无 | `ozon_seller/api.py:300-316` |
| seller_p7 | **未识别在线端点** | 历史 P7 SQL/数据不等于 API 实现 | 未知 | 标为未实现，仅允许 Mock 或经授权的文件导入 |
| buyer_search | GET `www.ozon.ru/api/entrypoint-api.bx/page/json/v2?url=/search/?page=N&text=...` | keyword、page、经许可会话 | 原代码按 page；有的 Widget 提供 `nextPage` 游标，不能混用 | `ozon_buyer/api.py:64-78`；新在线默认禁用 |
| buyer_category | 同入口 `url=/category/.../?page=N` | category_path、page | page 或 Widget 指示的游标 | `ozon_buyer/api.py:79-94` |
| buyer_detail | 同入口 `url=/product/{sku}/`，含 PDP2 | sku、include_pdp2、with_offers | 无 | `ozon_buyer/api.py:95-148`；支持离线解析 |
| buyer_reviews | 同入口 `url=/product/{sku}/reviews/?reviewsVariantMode=2&sort=...&page=N` | SKU、页数、排序 | page N | `ozon_buyer/collector.py:387-463` |
| buyer_offers | 同入口 `url=/modal/otherOffersFromSellers?product_id={sku}&sort=price` | SKU、sort | 尚未确认全量 Offers 的翻页行为 | `ozon_buyer/api.py:158-236` |

说明：Seller 网页内部端点**不是官方开放 Seller API**；在线启用前需独立核验账号、许可、留存及速率。新 Runtime 不依赖 Cookie 池、挑战绕过或多身份轮换；403、挑战页及权限失效立即暂停相关源。