#!/bin/sh
set -eu
: "${POSTGRES_USER:?}" "${POSTGRES_PASSWORD:?}" "${POSTGRES_DB:?}"
: "${MB_APP_DB_NAME:?}" "${MB_APP_DB_USER:?}" "${MB_APP_DB_PASSWORD:?}"
: "${MB_READER_USER:?}" "${MB_READER_PASSWORD:?}"
for value in "$MB_APP_DB_PASSWORD" "$MB_READER_PASSWORD"; do
  case "$value" in CHANGE_ME*|'') echo 'Set unique Metabase passwords before launching' >&2; exit 1 ;; esac
done
export PGHOST=postgres PGPORT=5432 PGUSER="$POSTGRES_USER" PGPASSWORD="$POSTGRES_PASSWORD"
psql -v ON_ERROR_STOP=1 -d "$POSTGRES_DB" \
  -f /metabase/010_pg_analytics.sql
psql -v ON_ERROR_STOP=1 -d "$POSTGRES_DB" \
  -v app_user="$MB_APP_DB_USER" -v app_password="$MB_APP_DB_PASSWORD" \
  -v app_database="$MB_APP_DB_NAME" -v reader_user="$MB_READER_USER" \
  -v reader_password="$MB_READER_PASSWORD" -f /metabase/020_pg_roles.psql
# Credentials never printed; keep database and business views separate.
echo 'PostgreSQL analytics view + isolated Metabase app DB + read-only role ready.'
