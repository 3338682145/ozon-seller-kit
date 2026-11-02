-- OMI keyword market mart v1
-- One row per core keyword; Secondary associations never enter market aggregation.

CREATE TABLE IF NOT EXISTS ozon_analytics.bridge_keyword_cluster_v1 (
 run_id TEXT NOT NULL REFERENCES ozon_meta.calculation_runs(run_id),
 snapshot_id TEXT NOT NULL REFERENCES ozon_meta.source_snapshots(snapshot_id),
 keyword TEXT NOT NULL, primary_cluster_id TEXT,
 assignment_status TEXT NOT NULL CHECK(assignment_status IN ('PRIMARY_ASSIGNED','UNASSIGNED')),
 PRIMARY KEY(run_id,snapshot_id,keyword)
);
CREATE INDEX IF NOT EXISTS ix_bridge_keyword_cluster_cluster
ON ozon_analytics.bridge_keyword_cluster_v1(run_id,snapshot_id,primary_cluster_id);
CREATE INDEX IF NOT EXISTS ix_bridge_keyword_cluster_snapshot_fk
ON ozon_analytics.bridge_keyword_cluster_v1(snapshot_id);
ALTER TABLE ozon_analytics.bridge_keyword_cluster_v1 ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS ozon_analytics.mart_keyword_market_base_v1 (
 run_id TEXT NOT NULL REFERENCES ozon_meta.calculation_runs(run_id),
 snapshot_id TEXT NOT NULL REFERENCES ozon_meta.source_snapshots(snapshot_id),
 keyword TEXT NOT NULL, primary_cluster_id TEXT,
 p7_query_exact TEXT, p7_search_buyers_28d BIGINT,
 p7_no_action_share_raw DOUBLE PRECISION, p7_zr_share_raw DOUBLE PRECISION,
 p7_conv_pct_raw DOUBLE PRECISION, p7_dyn_7d_raw DOUBLE PRECISION,
 p7_dyn_28d_raw DOUBLE PRECISION, p7_ca_raw DOUBLE PRECISION,
 p8_sku_count_top108 BIGINT NOT NULL, p6_matched_sku_count_top108 BIGINT NOT NULL,
 p6_match_coverage_pct_top108 DOUBLE PRECISION,
 antistress_sku_count_top108 BIGINT NOT NULL, non_antistress_sku_count_top108 BIGINT NOT NULL,
 antistress_share_of_p6_matched_pct DOUBLE PRECISION,
 p6_gross_units_top108 DOUBLE PRECISION, p6_net_units_est_top108 DOUBLE PRECISION,
 p6_gross_gmv_rub_top108 DOUBLE PRECISION, p6_net_gmv_est_rub_top108 DOUBLE PRECISION,
 category_scope_status TEXT NOT NULL,
 PRIMARY KEY(run_id,snapshot_id,keyword)
);
CREATE INDEX IF NOT EXISTS ix_mart_keyword_cluster
ON ozon_analytics.mart_keyword_market_base_v1(run_id,snapshot_id,primary_cluster_id);
CREATE INDEX IF NOT EXISTS ix_mart_keyword_scope
ON ozon_analytics.mart_keyword_market_base_v1(run_id,snapshot_id,category_scope_status);
CREATE INDEX IF NOT EXISTS ix_mart_keyword_snapshot_fk
ON ozon_analytics.mart_keyword_market_base_v1(snapshot_id);
ALTER TABLE ozon_analytics.mart_keyword_market_base_v1 ENABLE ROW LEVEL SECURITY;

WITH kw_cluster AS (
 SELECT keyword,max(cluster_id) FILTER(WHERE cluster_id IS NOT NULL) AS primary_cluster_id
 FROM ozon_raw.fact_keyword_sku
 WHERE snapshot_id='toys_2026_11_02_33e5f029'
 GROUP BY keyword
)
INSERT INTO ozon_analytics.bridge_keyword_cluster_v1
(run_id,snapshot_id,keyword,primary_cluster_id,assignment_status)
SELECT 'market_core_v1_20261102','toys_2026_11_02_33e5f029',k.keyword,c.primary_cluster_id,
 CASE WHEN c.primary_cluster_id IS NULL THEN 'UNASSIGNED' ELSE 'PRIMARY_ASSIGNED' END
FROM (
 SELECT DISTINCT keyword FROM ozon_raw.keyword_sku
 WHERE snapshot_id='toys_2026_11_02_33e5f029' AND position BETWEEN 1 AND 108
) k
LEFT JOIN kw_cluster c ON c.keyword=k.keyword
ON CONFLICT(run_id,snapshot_id,keyword) DO NOTHING;

INSERT INTO ozon_analytics.mart_keyword_market_base_v1
(run_id,snapshot_id,keyword,primary_cluster_id,p7_query_exact,p7_search_buyers_28d,
 p7_no_action_share_raw,p7_zr_share_raw,p7_conv_pct_raw,p7_dyn_7d_raw,p7_dyn_28d_raw,p7_ca_raw,
 p8_sku_count_top108,p6_matched_sku_count_top108,p6_match_coverage_pct_top108,
 antistress_sku_count_top108,non_antistress_sku_count_top108,antistress_share_of_p6_matched_pct,
 p6_gross_units_top108,p6_net_units_est_top108,p6_gross_gmv_rub_top108,p6_net_gmv_est_rub_top108,
 category_scope_status)
SELECT
 'market_core_v1_20261102','toys_2026_11_02_33e5f029',b.keyword,b.primary_cluster_id,
 p.query,p.search_buyers_28d,p.no_action_share_pct,p.zr_share_pct,p.conv_pct,p.dyn_7d_raw,p.dyn_28d_raw,p.ca_raw,
 count(f.sku),count(*) FILTER(WHERE f.p6_matched),
 100.0*count(*) FILTER(WHERE f.p6_matched)/NULLIF(count(*),0),
 count(*) FILTER(WHERE f.p6_matched AND f.p6_category3_id='92811'),
 count(*) FILTER(WHERE f.p6_matched AND f.p6_category3_id IS DISTINCT FROM '92811'),
 100.0*count(*) FILTER(WHERE f.p6_matched AND f.p6_category3_id='92811')/
 NULLIF(count(*) FILTER(WHERE f.p6_matched),0),
 sum(f.p6_gross_units_28d) FILTER(WHERE f.p6_matched),
 sum(f.p6_net_units_est_28d) FILTER(WHERE f.p6_matched),
 sum(f.p6_gross_gmv_rub_28d) FILTER(WHERE f.p6_matched),
 sum(f.p6_net_gmv_est_rub_28d) FILTER(WHERE f.p6_matched),
 CASE
  WHEN count(*) FILTER(WHERE f.p6_matched)=0 THEN 'NO_P6_MATCH_IN_TOP108'
  WHEN count(*) FILTER(WHERE f.p6_matched AND f.p6_category3_id='92811')=0 THEN 'NON_ANTISTRESS_IN_P6_MATCHED_TOP108'
  WHEN count(*) FILTER(WHERE f.p6_matched AND f.p6_category3_id='92811')
       =count(*) FILTER(WHERE f.p6_matched) THEN 'ANTISTRESS_ONLY_IN_P6_MATCHED_TOP108'
  ELSE 'MIXED_CATEGORY_IN_P6_MATCHED_TOP108'
 END
FROM ozon_analytics.bridge_keyword_cluster_v1 b
JOIN ozon_analytics.fact_p8_keyword_sku_108 f
 ON f.run_id=b.run_id AND f.snapshot_id=b.snapshot_id AND f.keyword=b.keyword
LEFT JOIN ozon_analytics.fact_p7_keyword_28d p
 ON p.run_id='p6_p7_foundation_20261102_v1'
AND p.snapshot_id=b.snapshot_id AND p.query=b.keyword
WHERE b.run_id='market_core_v1_20261102'
GROUP BY b.keyword,b.primary_cluster_id,p.query,p.search_buyers_28d,
 p.no_action_share_pct,p.zr_share_pct,p.conv_pct,p.dyn_7d_raw,p.dyn_28d_raw,p.ca_raw
ON CONFLICT(run_id,snapshot_id,keyword) DO NOTHING;

CREATE OR REPLACE VIEW ozon_analytics.v_p6_antistress_28d_v1
WITH (security_invoker=true) AS
SELECT * FROM ozon_analytics.fact_p6_sku_28d
WHERE run_id='p6_p7_foundation_20261102_v1'
AND snapshot_id='toys_2026_11_02_33e5f029' AND category3_id='92811';

CREATE OR REPLACE VIEW ozon_analytics.v_p8_antistress_top108_v1
WITH (security_invoker=true) AS
SELECT * FROM ozon_analytics.fact_p8_keyword_sku_108
WHERE run_id='market_core_v1_20261102'
AND snapshot_id='toys_2026_11_02_33e5f029'
AND p6_matched=true AND p6_category3_id='92811';

CREATE OR REPLACE VIEW ozon_analytics.v_keyword_market_scope_v1
WITH (security_invoker=true) AS
SELECT * FROM ozon_analytics.mart_keyword_market_base_v1
WHERE run_id='market_core_v1_20261102'
AND snapshot_id='toys_2026_11_02_33e5f029';

CREATE OR REPLACE VIEW ozon_analytics.v_sku_cluster_power_source_v1
WITH (security_invoker=true) AS
SELECT snapshot_id,sku,cluster_id,esi_total,n_kw,n_top10,n_top30,best_rank,
       best_esi,main_kw,conv_eff,real_power
FROM ozon_raw.sku_power;

COMMENT ON TABLE ozon_analytics.bridge_keyword_cluster_v1 IS
'V1 primary keyword-to-demand-cluster bridge. One row per keyword. Demand cluster is not Product Family.';
COMMENT ON TABLE ozon_analytics.mart_keyword_market_base_v1 IS
'One row per keyword with P7 exact-match metrics, P8 top108 coverage and P6 category composition of P8-visible matched SKUs. Cross-keyword sums are non-additive.';
COMMENT ON VIEW ozon_analytics.v_p6_antistress_28d_v1 IS
'P6 28-day SKU facts filtered to category3_id=92811. Net values are estimates; missing redemption stays NULL.';
COMMENT ON VIEW ozon_analytics.v_p8_antistress_top108_v1 IS
'P8 top108 rows whose matched P6 SKU is category3_id=92811; this is the observable shelf subset, not the whole market.';
COMMENT ON VIEW ozon_analytics.v_sku_cluster_power_source_v1 IS
'SKU power source grain is snapshot_id x sku x cluster_id; not one row per SKU.';

ANALYZE ozon_analytics.bridge_keyword_cluster_v1;
ANALYZE ozon_analytics.mart_keyword_market_base_v1;
