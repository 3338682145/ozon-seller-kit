SELECT
  COUNT(*) AS observed_keyword_sku_rows,
  COUNT(DISTINCT sku) AS distinct_skus,
  COUNT(DISTINCT keyword_id) AS distinct_keywords,
  COUNT(*) FILTER (WHERE keyword_opportunity_score IS NOT NULL)
    AS rows_with_verified_keyword_score,
  ROUND(AVG(price_rub), 2) AS avg_current_master_price_rub,
  MIN(search_position) AS best_observed_position
FROM analytics.v_product_keyword_filter
WHERE keyword_normalized ILIKE '%' || {{keyword}} || '%'
  AND price_rub <= {{max_price}}
  AND search_position <= {{rank_max}};
