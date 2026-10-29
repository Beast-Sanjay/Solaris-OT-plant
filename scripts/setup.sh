#!/usr/bin/env bash
# Solar first: clone upstream original protocol fleet only when --full was requested.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/init_env.py
if [[ "${1:-}" == '--full' ]]; then
    command -v git >/dev/null || { echo '[ERROR] git required for full mode'; exit 1; }
    [[ -f upstream/docker/docker-compose.yml ]] || git clone --depth 1 https://github.com/AsherDLL/mrhOTshOT_Docker_pub.git upstream
    python3 -c 'import yaml' 2>/dev/null || { echo '[ERROR] Install python3-yaml for integration'; exit 1; }
    python3 scripts/integrate_upstream.py
fi
if python3 -c 'import yaml' 2>/dev/null; then
    python3 scripts/validate.py
    python3 scripts/validate_windows.py
else
    echo '[WARN] Install python3-yaml to run topology assertions.'
fi
python3 scripts/host_preflight.py
printf '\nReady: ./scripts/up.sh%s\n' "${1:+ $1}"
