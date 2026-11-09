-- Important: score is grouped at the keyword level, not per SKU.
SELECT
  keyword,
  COUNT(DISTINCT sku) AS observed_skus,
  COUNT(*) FILTER (WHERE is_advert IS TRUE) AS observed_ad_slots,
  ROUND(AVG(price_rub), 2) AS avg_price_rub,
  MAX(keyword_opportunity_score) AS keyword_opportunity_score,
  MAX(score_as_of_date) AS score_as_of_date,
  MAX(opportunity_status) AS opportunity_status
FROM analytics.v_product_keyword_filter
WHERE keyword_normalized ILIKE '%' || {{keyword}} || '%'
  AND price_rub <= {{max_price}}
  AND search_position <= {{rank_max}}
GROUP BY keyword
ORDER BY keyword_opportunity_score DESC NULLS LAST,
         observed_skus DESC, keyword ASC
LIMIT 200;
