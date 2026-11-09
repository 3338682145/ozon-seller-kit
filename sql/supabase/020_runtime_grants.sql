-- Run AFTER Alembic, from the account which owns collector_core tables.
-- First create a dedicated LOGIN role named collector_runtime in Supabase
-- Database Roles / SQL Editor, with a random password stored as a secret.
-- Do NOT use Supabase service_role or postgres for the API and Workers.
BEGIN;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'collector_runtime') THEN
    RAISE EXCEPTION 'Create a separate collector_runtime LOGIN role before applying grants';
  END IF;
END $$;
REVOKE ALL ON SCHEMA collector_core FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA collector_core TO collector_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA collector_core TO collector_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA collector_core TO collector_runtime;
ALTER DEFAULT PRIVILEGES IN SCHEMA collector_core
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO collector_runtime;
ALTER DEFAULT PRIVILEGES IN SCHEMA collector_core
  GRANT USAGE, SELECT ON SEQUENCES TO collector_runtime;
COMMIT;
