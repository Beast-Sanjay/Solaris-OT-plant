#!/usr/bin/env bash
# Idempotent initialization for both fresh and persistent DB01 data volumes.
set -euo pipefail
cd "$(dirname "$0")/.."
for n in {1..30}; do
  if docker compose exec -T db01 pg_isready -U otlab -d corporate >/dev/null 2>&1; then
    docker compose exec -T db01 psql -v ON_ERROR_STOP=1 -U otlab -d corporate < db/001_init.sql
    echo '[PASS] DB01 work_orders schema and seed data ready.'
    exit 0
  fi
  sleep 2
done
echo '[FAIL] DB01 did not become ready; run docker compose logs db01' >&2
exit 1
