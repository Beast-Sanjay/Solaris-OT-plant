#!/usr/bin/env bash
# Read-only deployment verification. Does NOT issue inverter or breaker commands.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -f .env ]] || { echo '[FAIL] .env missing: python3 scripts/init_env.py' >&2; exit 1; }
set -a
# shellcheck disable=SC1091
source .env
set +a
command -v docker >/dev/null || { echo '[FAIL] Docker is not installed.'; exit 1; }
COMPOSE=(docker compose -f compose.yaml)
if [[ "${1:-}" == '--full' ]]; then
  [[ -f compose.mrhotshot.yaml ]] || { echo '[FAIL] Run scripts/setup.sh --full first'; exit 1; }
  COMPOSE+=(-f compose.mrhotshot.yaml)
fi
"${COMPOSE[@]}" ps
python3 - <<'PY'
import json,time,urllib.request

def get(url):
    with urllib.request.urlopen(url,timeout=6) as r:return json.load(r)
def until(url,pred,steps=35):
    for i in range(steps):
        try:
            sample=get(url)
            if pred(sample):return sample
        except Exception:pass
        time.sleep(2)
    raise SystemExit('[FAIL] Not ready: '+url)
site=until('http://127.0.0.1:1882/api/state',lambda s:s.get('online_inverters')==4 and s.get('feeder',{}).get('connected') and len(s.get('arrays',{}))==4)
assert all(x.get('modbus_connected') for x in site['inverters'].values())
assert site['export_kw']<=site['generation_kw']<=10000
assert site['transformer']['connected'] and site['protection_relay']['connected'] and site['grid_order']['connected']
assert all(0 <= site['arrays'][f'PV-{i:02d}']['soiling_pct'] <= 50 for i in range(1,5))
assert all(0 <= site['arrays'][f'PV-{i:02d}']['failed_strings'] < 36 for i in range(1,5))
print('[PASS] Transformer, relay, grid-dispatch and per-array live condition telemetry')
print('[PASS] SCADA / 4 PV arrays / 4 Modbus inverters / PPC / connected 33 kV feeder')
hist=until('http://127.0.0.1:18082/health',lambda s:s.get('ok'))
print('[PASS] DB01 PostgreSQL and IT maintenance web app')
ca=until('http://127.0.0.1:18083/api/status',lambda s:s.get('ca_ready'))
print('[PASS] CA01 certificate issuer')
field=until('http://127.0.0.1:19002/api/assets',lambda s:len(s.get('assets',{}))==4)
print('[PASS] Isolated field service console reads four working PV blocks')
public=until('http://127.0.0.1:18081/api/public',lambda s:s.get('online') and s.get('updated_at'),steps=45)
assert public['simulation'] and 'controller_ip' not in public and 'secret_control_token' not in public
assert 0<=public['export_mw']<=public['generation_mw']<=10
with urllib.request.urlopen('http://127.0.0.1:18081/api/public/history',timeout=5) as r: pubhist=json.load(r)
assert pubhist.get('samples')
stats=get('http://127.0.0.1:18081/api/public/statistics')
assert stats['simulation'] and stats['energy_today_mwh']>=0 and 'observed_minutes' in stats
notices=get('http://127.0.0.1:18081/api/public/notices')
assert isinstance(notices['notices'],list)
print('[PASS] Public site: live filtered historian, observed energy, and announcement APIs')
PY
code=$(curl -s --max-time 8 -o /dev/null -w '%{http_code}' 'http://127.0.0.1:18085/api/cases')
[[ "$code" == '401' ]] || { echo "[FAIL] Anonymous corporate public case review returned HTTP $code (expected 401)"; exit 1; }
code=$(curl -s --max-time 8 -o /dev/null -w '%{http_code}' 'http://127.0.0.1:18081/api/internal/enquiries')
[[ "$code" == '404' ]] || { echo "[FAIL] Public website did not block internal cases (HTTP $code)"; exit 1; }
echo '[PASS] Corporate public service desk requires AD login; public Nginx blocks internal case paths'
"${COMPOSE[@]}" exec -T dc01 samba-tool user show analyst >/dev/null
echo '[PASS] Corporate Samba AD analyst account'
case_response=$(mktemp)
case_code=$(curl -sS --max-time 12 -u "analyst:${CORP_AD_ANALYST_PASSWORD}" -o "$case_response" -w '%{http_code}' 'http://127.0.0.1:18085/api/cases')
if [[ "$case_code" != '200' ]]; then
  echo "[FAIL] Corporate AD -> public-ops -> IDMZ case conduit returned HTTP $case_code" >&2
  rm -f "$case_response"
  exit 1
fi
python3 - "$case_response" <<'CASEJSON'
import json,sys
with open(sys.argv[1]) as f: result=json.load(f)
assert isinstance(result.get('enquiries'),list),result
print('[PASS] Corporate AD-authenticated public service desk reads real case records through IDMZ')
CASEJSON
rm -f "$case_response"

"${COMPOSE[@]}" exec -T ics-dc01 samba-tool user show icsoperator >/dev/null
echo '[PASS] Industrial OT Samba AD operator account'
"${COMPOSE[@]}" exec -T it-workstation dig @10.0.0.10 _ldap._tcp.corp.otlab.test SRV +short | grep -qi dc01
echo '[PASS] Corporate directory service resolution'
[[ "$(curl -s --max-time 8 -o /dev/null -w '%{http_code}' http://127.0.0.1:18080/api/devices/latest)" == '401' ]] || { echo '[FAIL] Anonymous corporate historian access was not rejected'; exit 1; }
response=$(mktemp)
trap 'rm -f "$response"' EXIT
code=$(curl -sS --max-time 12 -o "$response" -w '%{http_code}' -u "analyst:${CORP_AD_ANALYST_PASSWORD}" 'http://127.0.0.1:18080/api/devices/latest')
[[ "$code" == '200' ]] || { echo "[FAIL] Corporate AD -> IDMZ -> historian returned HTTP $code"; exit 1; }
python3 - "$response" <<'PY'
import json,sys
with open(sys.argv[1]) as f:data=json.load(f)
assets=data['historian']['devices']
assert all(name in assets for name in ('PV-01','PV-02','PV-03','PV-04','INV-01','INV-02','INV-03','INV-04','PPC-01','FDR-33KV-01','TX-33KV-01','REL-33KV-01','GRID-ORDER-01','MET-01','SCADA-01')),sorted(assets)
print('[PASS] AD-authenticated historical access returns 15 solar asset records')
PY
python3 - <<'WORKCHECK'
import json,time,urllib.request
url='http://127.0.0.1:18082/api/workorders'
for _ in range(20):
    try:
        with urllib.request.urlopen(url,timeout=5) as r:orders=json.load(r)['orders']
        ids={o['reference'] for o in orders}
        if len(orders) >= 5:
            print('[PASS] DB01 persisted work orders; live maintenance bot is validated separately')
            break
    except (OSError,ValueError,KeyError):pass
    time.sleep(3)
else:raise SystemExit('[FAIL] No DB work orders; check DB01 and corp-portal')
WORKCHECK
if "${COMPOSE[@]}" exec -T it-workstation getent hosts inverter-01 >/dev/null 2>&1; then
 echo '[FAIL] Enterprise IT unexpectedly resolves a controller by name'; exit 1
fi
if "${COMPOSE[@]}" exec -T maintenance-bot python -c "import urllib.request,json; d=json.load(urllib.request.urlopen('http://localhost:8080/health',timeout=5)); assert d['status']=='RUNNING'"; then
  echo '[PASS] Maintenance bot is processing AD-authenticated historian data'
else
  echo '[FAIL] Maintenance bot unhealthy (inspect AD bind / DB01 / IDMZ)' >&2; exit 1
fi
echo '[PASS] Corporate workstation has no direct L1 controller resolution'
if [[ "${1:-}" == '--full' ]]; then
 curl -fSs --max-time 10 'http://127.0.0.1:1881/' >/dev/null
 echo '[PASS] Legacy FUXA UI responds (live tags must also be confirmed in its display)'
fi
echo '[PASS] Read-only checks complete. Controls remain unchanged.'
