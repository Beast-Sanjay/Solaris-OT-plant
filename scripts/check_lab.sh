#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -f .env ]] || { echo 'Missing .env - run scripts/init_env.py'; exit 1; }
# Parse only our generated format, no shell eval of arbitrary values.
userpass=$(sed -n 's/^CORP_AD_ANALYST_PASSWORD=//p' .env)
[[ -n "$userpass" ]] || { echo 'Missing analyst password'; exit 1; }
echo 'SCADA Level 2 telemetry:'
curl --max-time 6 -fsS http://127.0.0.1:1882/api/state | python3 -m json.tool
echo 'Active Directory-authenticated historian query across IT -> IDMZ -> L3:'
curl --max-time 8 -fsS -u "analyst:$userpass" http://127.0.0.1:18080/api/latest | python3 -m json.tool
echo 'Verify DC1 SRV records:'
docker compose exec -T it-workstation dig @10.0.0.10 _ldap._tcp.corp.otlab.test SRV +short || true
echo 'Verify OT isolation (L4 workstation cannot resolve PLC service from L1):'
if docker compose exec -T it-workstation getent hosts plc-demo >/dev/null 2>&1; then
  echo '[WARN] plc-demo hostname resolved; inspect accidental multi-network membership.'
else
  echo '[PASS] L4 has no DNS record for L1 plc-demo.'
fi
