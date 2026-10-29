#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-}" in
  --solar) docker compose -f compose.yaml -f compose.solar.yaml down ;;
  --full-solar)
    [[ -f compose.mrhotshot.yaml ]] || { echo 'compose.mrhotshot.yaml missing'; exit 1; }
    docker compose -f compose.yaml -f compose.solar.yaml -f compose.mrhotshot.yaml down ;;
  --full) docker compose -f compose.yaml -f compose.mrhotshot.yaml down ;;
  '') docker compose -f compose.yaml down ;;
  *) echo 'usage: scripts/down.sh [--solar|--full|--full-solar]'; exit 2 ;;
esac
printf 'Stopped. Persistent historian, Samba AD and corporate DB volumes preserved.
'
