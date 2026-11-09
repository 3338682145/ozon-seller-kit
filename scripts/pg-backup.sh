#!/usr/bin/env bash
set -euo pipefail
# Local-only. Record and verify encrypted off-host copies before production.
cd "$(dirname "$0")/.."
mkdir -p backups
chmod 700 backups
file="backups/ozon-$(date -u +%Y%m%dT%H%M%SZ).dump"
docker compose exec -T postgres sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$file"
sha256sum "$file" > "$file.sha256"
chmod 600 "$file" "$file.sha256"
echo "backup artifact created (restore not tested): $file"
