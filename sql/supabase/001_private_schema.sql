-- Run ONCE with a trusted Supabase SQL Editor account BEFORE Alembic.
-- No data in existing ozon_raw, ozon_analytics or public is altered.
BEGIN;
CREATE SCHEMA IF NOT EXISTS collector_core;
REVOKE ALL ON SCHEMA collector_core FROM PUBLIC;
REVOKE ALL ON SCHEMA collector_core FROM anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA collector_core FROM PUBLIC, anon, authenticated;
COMMIT;
