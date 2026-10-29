#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/init_env.py
if [[ "${1:-}" == '--full' ]]; then
  [[ -f compose.mrhotshot.yaml ]] || { echo '[ERROR] ./scripts/setup.sh --full before full mode'; exit 1; }
  docker compose -f compose.yaml -f compose.mrhotshot.yaml up -d --build
  if ! python3 scripts/seed_fuxa_purdue.py --wait; then
    echo '[WARN] Legacy FUXA seed pending; retry: python3 scripts/seed_fuxa_purdue.py --wait' >&2
  fi
else
  docker compose -f compose.yaml up -d --build
fi
./scripts/migrate_db.sh
cat <<'OUT'

SOLARIS ONE (localhost only)
  Solar SCADA + operator controls:    http://127.0.0.1:1882
  Live asset explorer:               http://127.0.0.1:1882/assets
  OT grid dispatch portal:           http://127.0.0.1:1883
  Enterprise maintenance / DB01:     http://127.0.0.1:18082
  AD-authenticated historian API:    http://127.0.0.1:18080/api/devices/latest
  CA01:                              http://127.0.0.1:18083/api/status
  External solar portal:             http://127.0.0.1:18081
  AD-authenticated public requests:  http://127.0.0.1:18085
  SOC event collector:              http://127.0.0.1:19090/api/events
  Jump SSH:                         127.0.0.1:2222
  Legacy FUXA (--full mode):         http://127.0.0.1:1881

  Read/control token: grep '^CONTROL_TOKEN=' .env
  Read-only verification: ./scripts/check_lab.sh
OUT
