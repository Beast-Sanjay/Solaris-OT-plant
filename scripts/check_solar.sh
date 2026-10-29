#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
cmd=(docker compose -f compose.yaml -f compose.solar.yaml)
if [[ "${1:-}" == '--full' ]]; then cmd+=( -f compose.mrhotshot.yaml ); fi
printf '=== Solar Digital Twin stack ===\n'
"${cmd[@]}" ps solar-physics solar-inverter-01 solar-inverter-02 solar-inverter-03 solar-inverter-04 solar-ppc solar-scada solar-historian solar-it-access
printf '\n=== L2 SCADA telemetry ===\n'
curl --fail --show-error --max-time 8 -sS http://127.0.0.1:1883/api/state | python3 -c 'import json,sys; s=json.load(sys.stdin);p=s.get("plant",{}); assert s.get("connected") and len(p.get("inverters",{}))==4,"PPC or inverter telemetry unavailable";print("[PASS] four inverters connected, grid export:",p["pcc"]["export_mw"],"MW")'
printf '\n=== Level 3 historian persistence (AD authenticated) ===\n'
[[ -f .env ]] || { echo 'Missing .env. Run scripts/init_env.py'; exit 1; }
pass=$(sed -n 's/^CORP_AD_ANALYST_PASSWORD=//p' .env)
[[ -n "$pass" ]] || { echo 'Missing AD analyst password'; exit 1; }
curl --fail --show-error --max-time 8 -sS -u "analyst:$pass" http://127.0.0.1:18084/api/latest | python3 -c 'import json,sys; x=json.load(sys.stdin);s=x["historian"]["sample"];assert s and len(s["state"]["plant"]["inverters"])==4;print("[PASS] AD-gated L4->IDMZ->L3 historian; sample export:",s["export_mw"],"MW")'
printf '\n=== Docker-level IT-to-control DNS isolation ===\n'
if "${cmd[@]}" exec -T it-workstation getent hosts solar-inverter-01 >/dev/null 2>&1; then
 echo '[FAIL] Corporate IT unexpectedly resolves Level 1 controller'; exit 1
else echo '[PASS] Corporate IT does not resolve Level 1 inverter'; fi
printf '\nAll solar checks passed.\n'
