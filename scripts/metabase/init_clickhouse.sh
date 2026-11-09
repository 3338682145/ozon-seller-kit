#!/bin/sh
set -eu
: "${CLICKHOUSE_USER:?}" "${CLICKHOUSE_PASSWORD:?}" "${MB_CH_READER_PASSWORD:?}"
case "$MB_CH_READER_PASSWORD" in CHANGE_ME*|'') echo 'Set MB_CH_READER_PASSWORD first' >&2; exit 1 ;; esac
# Restrict to a fixed read-only username and SHA-256 hash, not interpolated raw secrets.
reader_hash="$(printf %s "$MB_CH_READER_PASSWORD" | sha256sum | cut -d ' ' -f 1)"
ch() {
  clickhouse-client --host clickhouse --port 9000 --user "$CLICKHOUSE_USER" \
     --password "$CLICKHOUSE_PASSWORD" "$@"
}
ch --multiquery < /metabase/030_clickhouse_views.sql
ch --query "CREATE USER IF NOT EXISTS metabase_reader IDENTIFIED WITH sha256_hash BY '$reader_hash' SETTINGS readonly = 1, max_execution_time = 15"
ch --query "ALTER USER metabase_reader IDENTIFIED WITH sha256_hash BY '$reader_hash' SETTINGS readonly = 1, max_execution_time = 15"
ch --query 'GRANT SELECT ON analytics.v_serp_observations TO metabase_reader'
ch --query 'GRANT SELECT ON analytics.v_price_history TO metabase_reader'
echo 'ClickHouse restricted views and read-only account ready.'
