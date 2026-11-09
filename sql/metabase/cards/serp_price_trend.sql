-- Uses observed SERP prices, not a true product-level historical price join.
SELECT
  observed_date,
  round(avg(toFloat64(price_rub)), 2) AS avg_observed_serp_price_rub,
  uniqExact(sku) AS priced_observed_skus
FROM analytics.v_serp_observations
WHERE keyword ILIKE concat('%', {{keyword}}, '%')
  AND price_rub <= {{max_price}}
  AND search_position <= {{rank_max}}
GROUP BY observed_date
ORDER BY observed_date ASC
LIMIT 365;
