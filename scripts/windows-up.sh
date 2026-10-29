#!/usr/bin/env bash
# Start one (or all) OPTIONAL dockurr/windows VMs after checking nested KVM + ISOs.
set -euo pipefail
cd "$(dirname "$0")/.."
choice="${1:-it}"
case "$choice" in
  it) services=(win-it);profiles=(windows-it);isos=(windows11.iso);;
  server) services=(win-server);profiles=(windows-server);isos=(windowsserver2022.iso);;
  ot) services=(win-ot);profiles=(windows-ot);isos=(windows11.iso);;
  all) services=(win-it win-server win-ot);profiles=(windows-it windows-server windows-ot);isos=(windows11.iso windowsserver2022.iso);;
  *) echo 'Usage: ./scripts/windows-up.sh it|server|ot|all' >&2; exit 2;;
esac
command -v docker >/dev/null || { echo '[FAIL] Docker not installed on this Linux VM'; exit 1; }
docker compose version >/dev/null || { echo '[FAIL] docker compose v2 required'; exit 1; }
if [[ ! -c /dev/kvm ]]; then
  echo '[FAIL] /dev/kvm missing. Enable virtualization/nested virtualization on Proxmox and grant device access.' >&2; exit 1
fi
[[ -c /dev/net/tun ]] || { echo '[FAIL] /dev/net/tun missing'; exit 1; }
[[ -f .env ]] || python3 scripts/init_env.py
for iso in "${isos[@]}";do
  [[ -s "windows-media/$iso" ]] || { echo "[FAIL] Local Windows ISO missing: windows-media/$iso (do NOT place on production network)" >&2; exit 1; }
done
for svc in "${services[@]}";do
  case "$svc" in
    win-it) mkdir -p windows-data/it-workstation;;
    win-server) mkdir -p windows-data/win-server;;
    win-ot) mkdir -p windows-data/ot-engineering;;
  esac
done
if [[ "$choice" == 'all' ]];then
  echo '[INFO] Three Windows guests need approximately 12 GB guest RAM PLUS solar Linux services and system overhead.'
fi
args=(docker compose -f compose.yaml -f compose.windows.yaml)
for profile in "${profiles[@]}";do args+=(--profile "$profile");done
"${args[@]}" config --quiet
# Linux containers are started as dependencies, all core plant services remain network-isolated.
"${args[@]}" up -d "${services[@]}"
cat <<'OUT'
Windows virtual machines are provisioning from LOCAL ISO files, not downloaded.
Windows guest desktop (web viewer, local Docker host only):
  win-it      http://127.0.0.1:8006   RDP via host 127.0.0.1:33891
  win-server  http://127.0.0.1:8007   RDP via host 127.0.0.1:33892
  win-ot      http://127.0.0.1:8008   RDP via host 127.0.0.1:33893
Only URLs for Windows services actually started will respond.
After OS installation:
  Open Windows PowerShell as Administrator in the Windows desktop.
  Set-ExecutionPolicy -Scope Process Bypass -Force
  & 'Z:\Join-LabDomain.ps1' -Zone Corporate   # IT and server
  & 'Z:\Join-LabDomain.ps1' -Zone OT          # engineering guest
Read docs/WINDOWS_DOCKUR.md for DNS/domain setup, license and limitations.
OUT
