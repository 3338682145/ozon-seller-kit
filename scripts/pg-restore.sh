#!/usr/bin/env bash
set -euo pipefail
[[ "${HUMAN_APPROVED_RESTORE:-}" == "YES" ]] || { echo 'Require documented human approval and HUMAN_APPROVED_RESTORE=YES' >&2; exit 3; }
[[ $# -eq 1 ]] || { echo 'usage: pg-restore.sh backup.dump' >&2; exit 2; }
file="$1"
sha256sum -c "$file.sha256" || exit 4
# Avoid destructive default restore: human must carry out a recovery runbook.
echo "Backup verified. Restore must be run in an isolated staging DB before production cutover."
