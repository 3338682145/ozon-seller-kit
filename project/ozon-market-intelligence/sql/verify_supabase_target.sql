-- Read-only environment check; use project_id eohvguguegxbhszvssbd.
-- Does not alter business tables, permissions, or Auth.
SELECT
  1 AS connection_ok,
  current_database() AS database_name,
  current_setting('server_version') AS postgres_version,
  now() AS checked_at_utc,
  COALESCE((
    SELECT jsonb_agg(jsonb_build_object(
      'schema', n.nspname, 'name', c.relname, 'kind', c.relkind
    ) ORDER BY n.nspname, c.relname)
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind IN ('r','p','v','m')
      AND n.nspname NOT IN (
        'pg_catalog','information_schema','auth','storage','realtime',
        'extensions','supabase_functions','supabase_migrations','vault',
        'graphql','graphql_public','pgsodium','pgsodium_masks','net','cron'
      )
      AND n.nspname NOT LIKE 'pg_%'
      AND (
        c.relname IN (
          'dim_cluster','keyword_sku','fact_keyword_sku','sku_snapshot_v2',
          'query_metrics_v2','keyword_p7','keyword_seerfar',
          'cluster_market_165','keyword_market_1642'
        ) OR n.nspname LIKE 'ozon%'
      )
  ), '[]'::jsonb) AS ozon_analysis_relations;
