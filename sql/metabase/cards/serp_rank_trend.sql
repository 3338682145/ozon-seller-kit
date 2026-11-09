-- ClickHouse-only historical observation; not a PG->CH cross-database JOIN.
SELECT
  observed_date,
  uniqExact(sku) AS observed_skus,
  countIf(is_advert = 1) AS observed_ad_slots,
  min(search_position) AS best_observed_rank
FROM analytics.v_serp_observations
WHERE keyword ILIKE concat('%', {{keyword}}, '%')
  AND price_rub <= {{max_price}}
  AND search_position <= {{rank_max}}
GROUP BY observed_date
ORDER BY observed_date ASC
LIMIT 365;
