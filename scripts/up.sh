#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f .env ]]; then python3 scripts/init_env.py; fi
if [[ "${1:-}" == '--solar' || "${1:-}" == '--full-solar' ]]; then
  args=(-f compose.yaml -f compose.solar.yaml)
  if [[ "${1:-}" == '--full-solar' ]]; then
    [[ -f compose.mrhotshot.yaml ]] || { echo 'Run ./scripts/setup.sh first'; exit 1; }
    args+=(-f compose.mrhotshot.yaml)
  fi
  docker compose "${args[@]}" up -d --build
  echo 'Solar SCADA: http://127.0.0.1:1883 | AD-gated solar historian: http://127.0.0.1:18084/api/latest'
  exit 0
fi
if [[ "${1:-}" == '--full' ]]; then
  [[ -f compose.mrhotshot.yaml ]] || { echo 'Run ./scripts/setup.sh first'; exit 1; }
  docker compose -f compose.yaml -f compose.mrhotshot.yaml up -d --build
else
  docker compose -f compose.yaml up -d --build
fi
printf '\nSCADA: http://127.0.0.1:1882 | AD historian gateway: http://127.0.0.1:18080/api/latest\nSOC: http://127.0.0.1:19090/api/events | Jump via SSH: 127.0.0.1:2222\n'
