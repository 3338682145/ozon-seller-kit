-- OMI P6/P7 normalized fact foundation v1
-- Source snapshot: toys_2026_11_02_33e5f029
-- Run ID: p6_p7_foundation_20261102_v1
-- Execute in Supabase SQL Editor / MCP against project eohvguguegxbhszvssbd.
-- This script is idempotent for this run_id. For a new source snapshot, create a new run_id.

INSERT INTO ozon_meta.calculation_runs
(run_id,calculation_version,source_snapshot_id,started_at,status,parameters,validation)
VALUES
('p6_p7_foundation_20261102_v1','p6-p7-foundation-v1','toys_2026_11_02_33e5f029',now(),'running',
 '{"p6_snapshot_date":"2026-10-30","p6_window_days":28,"p7_snapshot_date":"2026-10-29","p7_window_days":28,"p7_ca_handling":"preserve raw; unit semantics unverified","p7_dyn_handling":"preserve raw; comparison baseline unverified"}'::jsonb,
 '{}'::jsonb)
ON CONFLICT(run_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS ozon_analytics.fact_p6_sku_28d (
 run_id TEXT NOT NULL REFERENCES ozon_meta.calculation_runs(run_id),
 snapshot_id TEXT NOT NULL REFERENCES ozon_meta.source_snapshots(snapshot_id),
 snapshot_date DATE NOT NULL, window_days INTEGER NOT NULL, sku TEXT NOT NULL,
 name TEXT, brand TEXT, seller_id TEXT, seller_name TEXT,
 category1 TEXT, category3 TEXT, category3_id TEXT, sales_schema TEXT,
 gross_units_28d DOUBLE PRECISION, gross_gmv_rub_28d DOUBLE PRECISION,
 avg_price_rub DOUBLE PRECISION, redemption_rate_pct DOUBLE PRECISION,
 net_units_est_28d DOUBLE PRECISION, net_gmv_est_rub_28d DOUBLE PRECISION,
 sales_dynamics_gmv_raw DOUBLE PRECISION, drr_raw DOUBLE PRECISION,
 promo_revenue_share_raw DOUBLE PRECISION, days_with_trafarets DOUBLE PRECISION,
 stock_end_raw DOUBLE PRECISION, accessibility_by_days_raw DOUBLE PRECISION,
 views_raw DOUBLE PRECISION, conv_to_cart_pdp_raw DOUBLE PRECISION,
 conv_to_cart_search_raw DOUBLE PRECISION, create_date_raw TEXT,
 min_seller_price_raw DOUBLE PRECISION, photo TEXT, rating DOUBLE PRECISION,
 reviews DOUBLE PRECISION, volume_l DOUBLE PRECISION, net_est_status TEXT NOT NULL,
 PRIMARY KEY(run_id,snapshot_id,sku)
);

CREATE TABLE IF NOT EXISTS ozon_analytics.fact_p7_keyword_28d (
 run_id TEXT NOT NULL REFERENCES ozon_meta.calculation_runs(run_id),
 snapshot_id TEXT NOT NULL REFERENCES ozon_meta.source_snapshots(snapshot_id),
 snap_date DATE NOT NULL, query TEXT NOT NULL, search_buyers_28d BIGINT,
 dyn_7d_raw DOUBLE PRECISION, dyn_28d_raw DOUBLE PRECISION, uniq_sellers BIGINT,
 zr_share_pct DOUBLE PRECISION, no_action_share_pct DOUBLE PRECISION,
 conv_pct DOUBLE PRECISION, search_order_gmv_raw_rub DOUBLE PRECISION,
 ord_raw BIGINT, ca_raw DOUBLE PRECISION, items_views_raw BIGINT,
 avg_price_raw_rub DOUBLE PRECISION, group_name TEXT, type_id TEXT,
 imported_at_raw TEXT, ca_semantics_status TEXT NOT NULL DEFAULT 'unit_unverified',
 dyn_semantics_status TEXT NOT NULL DEFAULT 'comparison_baseline_unverified',
 PRIMARY KEY(run_id,snapshot_id,query)
);

CREATE TABLE IF NOT EXISTS ozon_analytics.bridge_core_keyword_p7 (
 run_id TEXT NOT NULL REFERENCES ozon_meta.calculation_runs(run_id),
 snapshot_id TEXT NOT NULL REFERENCES ozon_meta.source_snapshots(snapshot_id),
 core_keyword TEXT NOT NULL, p7_query TEXT,
 mapping_status TEXT NOT NULL CHECK(mapping_status IN ('EXACT','NO_EXACT_MATCH')),
 search_buyers_28d BIGINT, PRIMARY KEY(run_id,snapshot_id,core_keyword)
);

CREATE TABLE IF NOT EXISTS ozon_analytics.p6_p7_quality_audit (
 run_id TEXT NOT NULL REFERENCES ozon_meta.calculation_runs(run_id),
 snapshot_id TEXT NOT NULL REFERENCES ozon_meta.source_snapshots(snapshot_id),
 source_layer TEXT NOT NULL, source_rows BIGINT NOT NULL,
 distinct_entities BIGINT NOT NULL, null_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
 range_checks JSONB NOT NULL DEFAULT '{}'::jsonb, notes JSONB NOT NULL DEFAULT '{}'::jsonb,
 PRIMARY KEY(run_id,snapshot_id,source_layer)
);

CREATE INDEX IF NOT EXISTS idx_fact_p6_sku_snapshot ON ozon_analytics.fact_p6_sku_28d(snapshot_id,sku);
CREATE INDEX IF NOT EXISTS idx_fact_p6_seller ON ozon_analytics.fact_p6_sku_28d(snapshot_id,seller_id);
CREATE INDEX IF NOT EXISTS idx_fact_p6_category ON ozon_analytics.fact_p6_sku_28d(snapshot_id,category3_id);
CREATE INDEX IF NOT EXISTS idx_fact_p7_query ON ozon_analytics.fact_p7_keyword_28d(snapshot_id,query);
CREATE INDEX IF NOT EXISTS idx_bridge_p7_query ON ozon_analytics.bridge_core_keyword_p7(snapshot_id,p7_query);

ALTER TABLE ozon_analytics.fact_p6_sku_28d ENABLE ROW LEVEL SECURITY;
ALTER TABLE ozon_analytics.fact_p7_keyword_28d ENABLE ROW LEVEL SECURITY;
ALTER TABLE ozon_analytics.bridge_core_keyword_p7 ENABLE ROW LEVEL SECURITY;
ALTER TABLE ozon_analytics.p6_p7_quality_audit ENABLE ROW LEVEL SECURITY;

INSERT INTO ozon_analytics.fact_p6_sku_28d
(run_id,snapshot_id,snapshot_date,window_days,sku,name,brand,seller_id,seller_name,category1,category3,category3_id,sales_schema,
gross_units_28d,gross_gmv_rub_28d,avg_price_rub,redemption_rate_pct,net_units_est_28d,net_gmv_est_rub_28d,
sales_dynamics_gmv_raw,drr_raw,promo_revenue_share_raw,days_with_trafarets,stock_end_raw,accessibility_by_days_raw,
views_raw,conv_to_cart_pdp_raw,conv_to_cart_search_raw,create_date_raw,min_seller_price_raw,photo,rating,reviews,volume_l,net_est_status)
SELECT 'p6_p7_foundation_20261102_v1',s.snapshot_id,m.snapshot_date,m.window_days,s.sku,s.name,s.brand,s.seller_id,s.seller_name,
s.category1,s.category3,s.category3_id,s.sales_schema,s.sold_count,s.gmv_sum,s.avg_price,s.redemption_rate,
CASE WHEN s.redemption_rate IS NOT NULL THEN s.sold_count*s.redemption_rate/100.0 END,
CASE WHEN s.redemption_rate IS NOT NULL AND s.avg_price IS NOT NULL THEN s.sold_count*s.redemption_rate/100.0*s.avg_price END,
s.sales_dynamics,s.drr,s.promo_revenue_share,s.days_with_trafarets,s.stock,s.accessibility_by_days,s.views,
s.conv_to_cart_pdp,s.conv_to_cart_search,s.create_date,s.min_seller_price,s.photo,s.rating,s.reviews,s.volume,
CASE WHEN s.redemption_rate IS NULL THEN 'MISSING_REDEMPTION_RATE' ELSE 'ESTIMATED_FROM_REDEMPTION_RATE' END
FROM ozon_raw.sku_snapshot_v2 s
JOIN ozon_meta.source_snapshots m ON m.snapshot_id=s.snapshot_id
WHERE s.snapshot_id='toys_2026_11_02_33e5f029'
ON CONFLICT(run_id,snapshot_id,sku) DO NOTHING;

INSERT INTO ozon_analytics.fact_p7_keyword_28d
(run_id,snapshot_id,snap_date,query,search_buyers_28d,dyn_7d_raw,dyn_28d_raw,uniq_sellers,zr_share_pct,
no_action_share_pct,conv_pct,search_order_gmv_raw_rub,ord_raw,ca_raw,items_views_raw,avg_price_raw_rub,
group_name,type_id,imported_at_raw,ca_semantics_status,dyn_semantics_status)
SELECT 'p6_p7_foundation_20261102_v1',p.snapshot_id,p.snap_date::date,p.query,p.count_28d,p.dyn_7d,p.dyn_28d,
p.uniq_sellers,p.zr_share,p.no_action_share,p.conv_pct,p.gmv,p.ord,p.ca,p.items_views,p.avg_price,p.group_name,p.type_id,
p.imported_at,'UNIT_UNVERIFIED_RAW_ONLY','COMPARISON_BASELINE_UNVERIFIED_RAW_ONLY'
FROM ozon_raw.keyword_p7 p WHERE p.snapshot_id='toys_2026_11_02_33e5f029'
ON CONFLICT(run_id,snapshot_id,query) DO NOTHING;

WITH core AS (
 SELECT DISTINCT keyword FROM ozon_raw.keyword_sku
 WHERE snapshot_id='toys_2026_11_02_33e5f029' AND position BETWEEN 1 AND 108
), p7 AS (
 SELECT query,count_28d FROM ozon_raw.keyword_p7 WHERE snapshot_id='toys_2026_11_02_33e5f029'
)
INSERT INTO ozon_analytics.bridge_core_keyword_p7
(run_id,snapshot_id,core_keyword,p7_query,mapping_status,search_buyers_28d)
SELECT 'p6_p7_foundation_20261102_v1','toys_2026_11_02_33e5f029',c.keyword,p.query,
CASE WHEN p.query IS NULL THEN 'NO_EXACT_MATCH' ELSE 'EXACT' END,p.count_28d
FROM core c LEFT JOIN p7 p ON p.query=c.keyword
ON CONFLICT(run_id,snapshot_id,core_keyword) DO NOTHING;

INSERT INTO ozon_analytics.p6_p7_quality_audit
(run_id,snapshot_id,source_layer,source_rows,distinct_entities,null_counts,range_checks,notes)
SELECT 'p6_p7_foundation_20261102_v1','toys_2026_11_02_33e5f029','P6_SKU_28D',count(*),count(DISTINCT sku),
jsonb_build_object('redemption_rate_pct',count(*) FILTER(WHERE redemption_rate_pct IS NULL)),
jsonb_build_object('redemption_min',min(redemption_rate_pct),'redemption_max',max(redemption_rate_pct),
'redemption_out_of_range',count(*) FILTER(WHERE redemption_rate_pct<0 OR redemption_rate_pct>100)),
jsonb_build_object('gross_units_sum',sum(gross_units_28d),'net_units_est_sum',sum(net_units_est_28d),
'gross_gmv_sum_rub',sum(gross_gmv_rub_28d),'net_gmv_est_sum_rub',sum(net_gmv_est_rub_28d))
FROM ozon_analytics.fact_p6_sku_28d WHERE run_id='p6_p7_foundation_20261102_v1'
ON CONFLICT(run_id,snapshot_id,source_layer) DO NOTHING;

INSERT INTO ozon_analytics.p6_p7_quality_audit
(run_id,snapshot_id,source_layer,source_rows,distinct_entities,null_counts,range_checks,notes)
SELECT 'p6_p7_foundation_20261102_v1','toys_2026_11_02_33e5f029','P7_KEYWORD_28D',count(*),count(DISTINCT query),
jsonb_build_object('dyn_7d',count(*) FILTER(WHERE dyn_7d_raw IS NULL),'dyn_28d',count(*) FILTER(WHERE dyn_28d_raw IS NULL)),
jsonb_build_object('dyn_7d_min',min(dyn_7d_raw),'dyn_7d_max',max(dyn_7d_raw),'dyn_28d_min',min(dyn_28d_raw),'dyn_28d_max',max(dyn_28d_raw),
'ca_raw_min',min(ca_raw),'ca_raw_max',max(ca_raw)),
jsonb_build_object('ca_semantics','raw only; unit/denominator unverified','dyn_semantics','raw only; comparison baseline unverified',
'count_28d','per-query unique buyers; do not sum across queries'))
FROM ozon_analytics.fact_p7_keyword_28d WHERE run_id='p6_p7_foundation_20261102_v1'
ON CONFLICT(run_id,snapshot_id,source_layer) DO NOTHING;

-- Exact match only: unmatched keywords are retained, not assumed to have zero demand.
INSERT INTO ozon_meta.run_events(run_id,stage,event_type,message,payload)
VALUES('p6_p7_foundation_20261102_v1','build','completed','P6/P7 normalized facts and exact keyword bridge built in Supabase.',
'{"p6_rows":29823,"p7_rows":9979,"core_keyword_rows":1642,"exact_p7_matches":560,"unmatched_core_keywords":1082}'::jsonb);
