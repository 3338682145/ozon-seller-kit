-- Product-level rows with latest keyword SERP observation. Opportunity score is
-- VERIFIED KEYWORD-LEVEL (same for all related SKUs), never a SKU score.
SELECT
  keyword AS keyword,
  sku,
  product_title,
  price_rub,
  search_position,
  CASE WHEN is_advert IS TRUE THEN '广告'
       WHEN is_advert IS FALSE THEN '自然'
       ELSE '未知' END AS slot_type,
  keyword_opportunity_score AS keyword_opportunity_score,
  opportunity_status,
  rank_observed_date,
  rank_source,
  price_observed_at,
  score_as_of_date,
  score_source,
  score_algorithm_version
FROM analytics.v_product_keyword_filter
WHERE keyword_normalized ILIKE '%' || {{keyword}} || '%'
  AND price_rub <= {{max_price}}
  AND search_position <= {{rank_max}}
ORDER BY keyword_opportunity_score DESC NULLS LAST,
         search_position ASC, price_rub ASC, sku ASC
LIMIT 500;
