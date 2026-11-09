-- Execute as the ClickHouse admin; SQL SECURITY DEFINER makes base facts
-- inaccessible to the Metabase reader. Existing raw fact payloads stay hidden.
CREATE DATABASE IF NOT EXISTS analytics;

CREATE OR REPLACE VIEW analytics.v_serp_observations
DEFINER = CURRENT_USER SQL SECURITY DEFINER
AS SELECT
    keyword,
    ozon_id AS sku,
    toDate(observed_at) AS observed_date,
    observed_at,
    calculated_at,
    position AS search_position,
    is_advert,
    price_rub,
    source,
    dataset_version,
    data_type,
    algorithm_version
FROM default.fact_keyword_sku_daily FINAL
WHERE position >= 1 AND position <= 1000 AND keyword != '';

-- Views return only approved fields; no raw payload, secrets or agent decisions.
CREATE OR REPLACE VIEW analytics.v_price_history
DEFINER = CURRENT_USER SQL SECURITY DEFINER
AS SELECT
    ozon_id AS sku,
    toDate(observed_at) AS observed_date,
    observed_at,
    price_rub,
    source,
    dataset_version,
    data_type,
    algorithm_version
FROM default.fact_price_history FINAL
WHERE price_rub IS NOT NULL AND ozon_id != '';
