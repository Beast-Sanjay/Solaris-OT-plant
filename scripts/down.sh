#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -f compose.mrhotshot.yaml ]]; then docker compose -f compose.yaml -f compose.mrhotshot.yaml down; else docker compose -f compose.yaml down; fi
printf 'Stopped. Volumes and AD accounts preserved. To destroy all state explicitly add -v manually.\n'
