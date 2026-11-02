-- OMI database structure optimization v1
-- Supabase project: eohvguguegxbhszvssbd
-- Source snapshot: toys_2026_11_02_33e5f029
-- Safe/idempotent: adds natural-key constraints and query indexes; does not delete or rewrite source rows.

-- 1) Natural primary keys for verified one-row-per-entity source tables.
-- Each key was checked for duplicate and NULL values before applying.
ALTER TABLE ozon_raw.blue_v3 ALTER COLUMN snapshot_id SET NOT NULL, ALTER COLUMN query SET NOT NULL;
ALTER TABLE ozon_raw.dim_cluster ALTER COLUMN snapshot_id SET NOT NULL, ALTER COLUMN cluster_id SET NOT NULL;
ALTER TABLE ozon_raw.fact_keyword_sku ALTER COLUMN snapshot_id SET NOT NULL, ALTER COLUMN keyword SET NOT NULL, ALTER COLUMN sku SET NOT NULL;
ALTER TABLE ozon_raw.keyword_p7 ALTER COLUMN snapshot_id SET NOT NULL, ALTER COLUMN query SET NOT NULL;
ALTER TABLE ozon_raw.keyword_score ALTER COLUMN snapshot_id SET NOT NULL, ALTER COLUMN query SET NOT NULL, ALTER COLUMN version SET NOT NULL;
ALTER TABLE ozon_raw.keyword_seerfar ALTER COLUMN snapshot_id SET NOT NULL, ALTER COLUMN query SET NOT NULL;
ALTER TABLE ozon_raw.keyword_sku ALTER COLUMN snapshot_id SET NOT NULL, ALTER COLUMN keyword SET NOT NULL, ALTER COLUMN sku SET NOT NULL;
ALTER TABLE ozon_raw.product_seerfar ALTER COLUMN snapshot_id SET NOT NULL, ALTER COLUMN sku SET NOT NULL;
ALTER TABLE ozon_raw.query_metrics_v2 ALTER COLUMN snapshot_id SET NOT NULL, ALTER COLUMN keyword SET NOT NULL;
ALTER TABLE ozon_raw.sku_snapshot_v2 ALTER COLUMN snapshot_id SET NOT NULL, ALTER COLUMN sku SET NOT NULL;
ALTER TABLE ozon_raw.category ALTER COLUMN snapshot_id SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS pk_raw_blue_v3 ON ozon_raw.blue_v3(snapshot_id,query);
CREATE UNIQUE INDEX IF NOT EXISTS pk_raw_dim_cluster ON ozon_raw.dim_cluster(snapshot_id,cluster_id);
CREATE UNIQUE INDEX IF NOT EXISTS pk_raw_fact_keyword_sku ON ozon_raw.fact_keyword_sku(snapshot_id,keyword,sku);
CREATE UNIQUE INDEX IF NOT EXISTS pk_raw_keyword_p7 ON ozon_raw.keyword_p7(snapshot_id,query);
CREATE UNIQUE INDEX IF NOT EXISTS pk_raw_keyword_score ON ozon_raw.keyword_score(snapshot_id,query,version);
CREATE UNIQUE INDEX IF NOT EXISTS pk_raw_keyword_seerfar ON ozon_raw.keyword_seerfar(snapshot_id,query);
CREATE UNIQUE INDEX IF NOT EXISTS pk_raw_keyword_sku ON ozon_raw.keyword_sku(snapshot_id,keyword,sku);
CREATE UNIQUE INDEX IF NOT EXISTS pk_raw_product_seerfar ON ozon_raw.product_seerfar(snapshot_id,sku);
CREATE UNIQUE INDEX IF NOT EXISTS pk_raw_query_metrics_v2 ON ozon_raw.query_metrics_v2(snapshot_id,keyword);
CREATE UNIQUE INDEX IF NOT EXISTS pk_raw_sku_snapshot_v2 ON ozon_raw.sku_snapshot_v2(snapshot_id,sku);
CREATE UNIQUE INDEX IF NOT EXISTS pk_raw_category ON ozon_raw.category(snapshot_id);

DO $$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='pk_raw_blue_v3' AND conrelid='ozon_raw.blue_v3'::regclass) THEN
  ALTER TABLE ozon_raw.blue_v3 ADD CONSTRAINT pk_raw_blue_v3 PRIMARY KEY USING INDEX pk_raw_blue_v3;
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='pk_raw_dim_cluster' AND conrelid='ozon_raw.dim_cluster'::regclass) THEN
  ALTER TABLE ozon_raw.dim_cluster ADD CONSTRAINT pk_raw_dim_cluster PRIMARY KEY USING INDEX pk_raw_dim_cluster;
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='pk_raw_fact_keyword_sku' AND conrelid='ozon_raw.fact_keyword_sku'::regclass) THEN
  ALTER TABLE ozon_raw.fact_keyword_sku ADD CONSTRAINT pk_raw_fact_keyword_sku PRIMARY KEY USING INDEX pk_raw_fact_keyword_sku;
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='pk_raw_keyword_p7' AND conrelid='ozon_raw.keyword_p7'::regclass) THEN
  ALTER TABLE ozon_raw.keyword_p7 ADD CONSTRAINT pk_raw_keyword_p7 PRIMARY KEY USING INDEX pk_raw_keyword_p7;
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='pk_raw_keyword_score' AND conrelid='ozon_raw.keyword_score'::regclass) THEN
  ALTER TABLE ozon_raw.keyword_score ADD CONSTRAINT pk_raw_keyword_score PRIMARY KEY USING INDEX pk_raw_keyword_score;
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='pk_raw_keyword_seerfar' AND conrelid='ozon_raw.keyword_seerfar'::regclass) THEN
  ALTER TABLE ozon_raw.keyword_seerfar ADD CONSTRAINT pk_raw_keyword_seerfar PRIMARY KEY USING INDEX pk_raw_keyword_seerfar;
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='pk_raw_keyword_sku' AND conrelid='ozon_raw.keyword_sku'::regclass) THEN
  ALTER TABLE ozon_raw.keyword_sku ADD CONSTRAINT pk_raw_keyword_sku PRIMARY KEY USING INDEX pk_raw_keyword_sku;
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='pk_raw_product_seerfar' AND conrelid='ozon_raw.product_seerfar'::regclass) THEN
  ALTER TABLE ozon_raw.product_seerfar ADD CONSTRAINT pk_raw_product_seerfar PRIMARY KEY USING INDEX pk_raw_product_seerfar;
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='pk_raw_query_metrics_v2' AND conrelid='ozon_raw.query_metrics_v2'::regclass) THEN
  ALTER TABLE ozon_raw.query_metrics_v2 ADD CONSTRAINT pk_raw_query_metrics_v2 PRIMARY KEY USING INDEX pk_raw_query_metrics_v2;
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='pk_raw_sku_snapshot_v2' AND conrelid='ozon_raw.sku_snapshot_v2'::regclass) THEN
  ALTER TABLE ozon_raw.sku_snapshot_v2 ADD CONSTRAINT pk_raw_sku_snapshot_v2 PRIMARY KEY USING INDEX pk_raw_sku_snapshot_v2;
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='pk_raw_category' AND conrelid='ozon_raw.category'::regclass) THEN
  ALTER TABLE ozon_raw.category ADD CONSTRAINT pk_raw_category PRIMARY KEY USING INDEX pk_raw_category;
 END IF;
END $$;

-- 2) Search/relationship indexes for the common query paths.
CREATE INDEX IF NOT EXISTS ix_raw_keyword_sku_snapshot_keyword_position
ON ozon_raw.keyword_sku(snapshot_id,keyword,position) INCLUDE(sku,seller_id,price);
CREATE INDEX IF NOT EXISTS ix_raw_keyword_sku_snapshot_sku
ON ozon_raw.keyword_sku(snapshot_id,sku);
CREATE INDEX IF NOT EXISTS ix_raw_fact_keyword_sku_snapshot_cluster_sku
ON ozon_raw.fact_keyword_sku(snapshot_id,cluster_id,sku);
CREATE INDEX IF NOT EXISTS ix_raw_fact_keyword_sku_snapshot_sku
ON ozon_raw.fact_keyword_sku(snapshot_id,sku);
CREATE INDEX IF NOT EXISTS ix_raw_sku_snapshot_snapshot_category_sku
ON ozon_raw.sku_snapshot_v2(snapshot_id,category3_id,sku);
CREATE INDEX IF NOT EXISTS ix_raw_sku_snapshot_snapshot_seller
ON ozon_raw.sku_snapshot_v2(snapshot_id,seller_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_raw_sku_power_snapshot_sku_cluster
ON ozon_raw.sku_power(snapshot_id,sku,cluster_id) WHERE cluster_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_raw_sku_power_snapshot_sku_null_cluster
ON ozon_raw.sku_power(snapshot_id,sku) WHERE cluster_id IS NULL;
CREATE INDEX IF NOT EXISTS ix_raw_sku_power_snapshot_cluster_sku
ON ozon_raw.sku_power(snapshot_id,cluster_id,sku);

-- 3) Supporting indexes for metadata FK lookups and audit trails.
CREATE INDEX IF NOT EXISTS ix_calculation_runs_source_snapshot_fk ON ozon_meta.calculation_runs(source_snapshot_id);
CREATE INDEX IF NOT EXISTS ix_decision_log_supersedes_fk ON ozon_meta.decision_log(supersedes);
CREATE INDEX IF NOT EXISTS ix_run_events_run_id_fk ON ozon_meta.run_events(run_id);
CREATE INDEX IF NOT EXISTS ix_artifact_registry_run_id_fk ON ozon_meta.artifact_registry(run_id);
CREATE INDEX IF NOT EXISTS ix_quality_audit_snapshot_fk ON ozon_analytics.p6_p7_quality_audit(snapshot_id);

-- 4) Refresh planner statistics after index creation.
ANALYZE ozon_raw.blue_v3;
ANALYZE ozon_raw.category;
ANALYZE ozon_raw.dim_cluster;
ANALYZE ozon_raw.fact_keyword_sku;
ANALYZE ozon_raw.keyword_p7;
ANALYZE ozon_raw.keyword_score;
ANALYZE ozon_raw.keyword_seerfar;
ANALYZE ozon_raw.keyword_sku;
ANALYZE ozon_raw.product_seerfar;
ANALYZE ozon_raw.query_metrics_v2;
ANALYZE ozon_raw.sku_power;
ANALYZE ozon_raw.sku_snapshot_v2;
