#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v docker >/dev/null || { echo 'Docker is required for Compose smoke testing' >&2; exit 2; }
if [[ ! -e .env ]]; then
  cp .env.example .env
  python - <<'PY'
from pathlib import Path
from secrets import token_urlsafe
p=Path('.env'); t=p.read_text()
for name in ('POSTGRES_PASSWORD','MINIO_SECRET_KEY','CLICKHOUSE_PASSWORD','API_KEY','VIEWER_KEY','ADMIN_KEY'):
    t=t.replace(name+'=GENERATE_ME',name+'='+token_urlsafe(30))
p.write_text(t)
p.chmod(0o600)
PY
fi
docker compose up -d --build
printf 'API: http://127.0.0.1:8000/docs ; Grafana: http://127.0.0.1:3000\n'
