#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 scripts/init_env.py
if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
  echo '[ERROR] Docker Engine + Compose v2 required.' >&2; exit 1
fi
if [[ ! -f upstream/docker/docker-compose.yml ]]; then
  command -v git >/dev/null || { echo '[ERROR] git required'; exit 1; }
  git clone --depth 1 https://github.com/AsherDLL/mrhOTshOT_Docker_pub.git upstream
fi
if ! python3 -c 'import yaml' 2>/dev/null; then
  echo '[ERROR] PyYAML needed for integration: python3 -m pip install pyyaml' >&2; exit 1
fi
python3 scripts/integrate_upstream.py
python3 scripts/validate.py
python3 scripts/host_preflight.py
printf '\nReady to build. Run:\n  docker compose -f compose.yaml -f compose.mrhotshot.yaml up -d --build\n'
