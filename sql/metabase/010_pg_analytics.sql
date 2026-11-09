-- Ozon Metabase read-only presentation schema. Apply ONLY after Alembic migrations.
-- No writes to existing production base tables. Input facts are explicit, verified,
-- keyword-level snapshots; an absent input means an absent opportunity score.
CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS analytics.keyword_opportunity_inputs (
    id VARCHAR(36) PRIMARY KEY,
    keyword_id VARCHAR(36) NOT NULL REFERENCES public.keywords(id),
    as_of_date DATE NOT NULL,
    max_slot30 SMALLINT NOT NULL CHECK (max_slot30 BETWEEN 0 AND 30),
    new_top10_share NUMERIC(8,6) NOT NULL CHECK (new_top10_share BETWEEN 0 AND 1),
    observed_top10_count SMALLINT NOT NULL CHECK (observed_top10_count BETWEEN 1 AND 10),
    source VARCHAR(64) NOT NULL,
    dataset_version VARCHAR(128) NOT NULL,
    algorithm_version VARCHAR(64) NOT NULL DEFAULT 'gold-analytics-v1',
    evidence_ref TEXT NOT NULL CHECK (length(trim(evidence_ref)) > 0),
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    verified_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_opportunity_keyword_snapshot UNIQUE (keyword_id, as_of_date, source, dataset_version),
    CONSTRAINT ck_opportunity_verified_evidence CHECK (NOT verified OR verified_at IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS ix_kwop_verified_latest
    ON analytics.keyword_opportunity_inputs (keyword_id, as_of_date DESC, verified_at DESC)
    WHERE verified = TRUE;
CREATE INDEX IF NOT EXISTS ix_kwsku_search_latest
    ON public.keyword_product_relations (keyword_id, observed_date DESC, position, ozon_id);
CREATE INDEX IF NOT EXISTS ix_product_price_rub
    ON public.products (price_rub) WHERE currency = 'RUB';

-- One latest SERP snapshot DATE per keyword; no accidental mixing old and new
-- SKU observations. Duplicate source observations have a deterministic tie-break.
-- The score is KEYWORD-LEVEL and repeats for SKUs matching that keyword.
CREATE OR REPLACE VIEW analytics.v_product_keyword_filter
WITH (security_barrier = true)
AS
WITH latest_day AS (
    SELECT keyword_id, MAX(observed_date) AS observed_date
    FROM public.keyword_product_relations
    GROUP BY keyword_id
),
ranked AS (
    SELECT r.*,
           ROW_NUMBER() OVER (
               PARTITION BY r.keyword_id, r.ozon_id
               ORDER BY r.source ASC, r.position ASC NULLS LAST, r.id ASC
           ) AS rn
    FROM public.keyword_product_relations r
    JOIN latest_day ld
      ON ld.keyword_id = r.keyword_id AND ld.observed_date = r.observed_date
    WHERE r.position BETWEEN 1 AND 1000
),
score_ranks AS (
    SELECT s.*,
           ROW_NUMBER() OVER (
               PARTITION BY s.keyword_id, s.as_of_date
               ORDER BY s.verified_at DESC, s.id DESC
           ) AS rn
    FROM analytics.keyword_opportunity_inputs s
    WHERE s.verified = TRUE AND s.algorithm_version = 'gold-analytics-v1'
)
SELECT
    k.id AS keyword_id,
    k.text AS keyword,
    k.normalized AS keyword_normalized,
    p.ozon_id AS sku,
    p.title AS product_title,
    p.category_id,
    p.seller_id,
    p.price_rub,
    p.currency,
    p.observed_at AS price_observed_at,
    r.position AS search_position,
    r.is_advert,
    r.source AS rank_source,
    r.dataset_version AS rank_dataset_version,
    r.observed_date AS rank_observed_date,
    CAST(s.as_of_date AS TEXT) AS score_as_of_date,
    s.source AS score_source,
    s.dataset_version AS score_dataset_version,
    s.algorithm_version AS score_algorithm_version,
    CASE WHEN s.id IS NOT NULL THEN
      ROUND(100 * (
         0.60 * (1 - LEAST(s.max_slot30::numeric / 10, 1))
         + 0.40 * LEAST(s.new_top10_share / 0.40, 1)
      ), 2)
    ELSE NULL END AS keyword_opportunity_score,
    CASE WHEN s.id IS NOT NULL THEN 'verified_keyword_score'
         ELSE 'missing_verified_inputs' END AS opportunity_status
FROM ranked r
JOIN public.keywords k ON k.id = r.keyword_id
JOIN public.products p ON p.ozon_id = r.ozon_id
LEFT JOIN score_ranks s
  ON s.keyword_id = r.keyword_id
 AND CAST(s.as_of_date AS TEXT) = r.observed_date
 AND s.rn = 1
WHERE r.rn = 1 AND p.currency = 'RUB' AND p.price_rub IS NOT NULL;

COMMENT ON VIEW analytics.v_product_keyword_filter IS
  'Read-only latest SERP keyword×SKU snapshot with product master price; score is keyword-level and NULL until verified source inputs exist.';
COMMENT ON TABLE analytics.keyword_opportunity_inputs IS
  'Write-protected from Metabase; ingestion by authorized ETL only after verifying seller identity, observed top10 and evidence.';
