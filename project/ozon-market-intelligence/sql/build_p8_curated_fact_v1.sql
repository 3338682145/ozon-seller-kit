-- OMI curated P8 fact v1
-- Supabase project eohvguguegxbhszvssbd
-- Grain: run_id + snapshot_id + keyword + sku
-- Only P8 position 1..108. Raw tables are preserved.

INSERT INTO ozon_meta.calculation_runs
(run_id,calculation_version,source_snapshot_id,started_at,status,parameters,validation)
VALUES
('market_core_v1_20261102','market-core-p6-p7-p8-v1','toys_2026_11_02_33e5f029',now(),'running',
 '{"p8_position_filter":"1..108","upstream_run":"p6_p7_foundation_20261102_v1"}'::jsonb,'{}'::jsonb)
ON CONFLICT(run_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS ozon_analytics.fact_p8_keyword_sku_108 (
 run_id TEXT NOT NULL REFERENCES ozon_meta.calculation_runs(run_id),
 snapshot_id TEXT NOT NULL REFERENCES ozon_meta.source_snapshots(snapshot_id),
 keyword TEXT NOT NULL, sku TEXT NOT NULL, position INTEGER NOT NULL,
 p8_price_rub DOUBLE PRECISION, p8_seller_id TEXT, p8_title TEXT,
 p8_rating DOUBLE PRECISION, p8_reviews DOUBLE PRECISION,
 p8_popularity DOUBLE PRECISION, p8_relevance DOUBLE PRECISION,
 p8_promo_raw TEXT, p8_cpc_bid_raw DOUBLE PRECISION,
 cluster_id_v1 TEXT, match_score_v1 DOUBLE PRECISION, esi_v1 DOUBLE PRECISION,
 p6_matched BOOLEAN NOT NULL, p6_category1 TEXT, p6_category3 TEXT, p6_category3_id TEXT,
 p6_seller_id TEXT, p6_seller_name TEXT,
 p6_gross_units_28d DOUBLE PRECISION, p6_gross_gmv_rub_28d DOUBLE PRECISION,
 p6_avg_price_rub DOUBLE PRECISION, p6_redemption_rate_pct DOUBLE PRECISION,
 p6_net_units_est_28d DOUBLE PRECISION, p6_net_gmv_est_rub_28d DOUBLE PRECISION,
 p6_drr_raw DOUBLE PRECISION, p6_create_date_raw TEXT,
 PRIMARY KEY(run_id,snapshot_id,keyword,sku)
);

CREATE INDEX IF NOT EXISTS ix_fact_p8_run_snapshot_keyword_position
ON ozon_analytics.fact_p8_keyword_sku_108(run_id,snapshot_id,keyword,position);
CREATE INDEX IF NOT EXISTS ix_fact_p8_inverted_sku_keyword
ON ozon_analytics.fact_p8_keyword_sku_108(run_id,snapshot_id,sku,keyword) INCLUDE(position);
CREATE INDEX IF NOT EXISTS ix_fact_p8_keyword_seller_position
ON ozon_analytics.fact_p8_keyword_sku_108(run_id,snapshot_id,keyword,p8_seller_id,position);
CREATE INDEX IF NOT EXISTS ix_fact_p8_category_keyword_sku
ON ozon_analytics.fact_p8_keyword_sku_108(run_id,snapshot_id,p6_category3_id,keyword,sku);
CREATE INDEX IF NOT EXISTS ix_fact_p8_snapshot_fk
ON ozon_analytics.fact_p8_keyword_sku_108(snapshot_id);
ALTER TABLE ozon_analytics.fact_p8_keyword_sku_108 ENABLE ROW LEVEL SECURITY;

INSERT INTO ozon_analytics.fact_p8_keyword_sku_108
(run_id,snapshot_id,keyword,sku,position,p8_price_rub,p8_seller_id,p8_title,p8_rating,p8_reviews,
 p8_popularity,p8_relevance,p8_promo_raw,p8_cpc_bid_raw,cluster_id_v1,match_score_v1,esi_v1,
 p6_matched,p6_category1,p6_category3,p6_category3_id,p6_seller_id,p6_seller_name,
 p6_gross_units_28d,p6_gross_gmv_rub_28d,p6_avg_price_rub,p6_redemption_rate_pct,
 p6_net_units_est_28d,p6_net_gmv_est_rub_28d,p6_drr_raw,p6_create_date_raw)
SELECT
 'market_core_v1_20261102',k.snapshot_id,k.keyword,k.sku,k.position::integer,
 k.price,k.seller_id,k.name,k.rating,k.reviews,k.popularity,k.relevance,k.promo,k.cpc,
 f.cluster_id,f.match_score,f.esi,(p.sku IS NOT NULL),
 p.category1,p.category3,p.category3_id,p.seller_id,p.seller_name,p.sold_count,p.gmv_sum,p.avg_price,
 p.redemption_rate,
 CASE WHEN p.redemption_rate IS NOT NULL THEN p.sold_count*p.redemption_rate/100.0 END,
 CASE WHEN p.redemption_rate IS NOT NULL AND p.avg_price IS NOT NULL
      THEN p.sold_count*p.redemption_rate/100.0*p.avg_price END,
 p.drr,p.create_date
FROM ozon_raw.keyword_sku k
LEFT JOIN ozon_raw.fact_keyword_sku f
 ON f.snapshot_id=k.snapshot_id AND f.keyword=k.keyword AND f.sku=k.sku
LEFT JOIN ozon_raw.sku_snapshot_v2 p
 ON p.snapshot_id=k.snapshot_id AND p.sku=k.sku
WHERE k.snapshot_id='toys_2026_11_02_33e5f029'
 AND k.position BETWEEN 1 AND 108
ON CONFLICT(run_id,snapshot_id,keyword,sku) DO NOTHING;

ANALYZE ozon_analytics.fact_p8_keyword_sku_108;
