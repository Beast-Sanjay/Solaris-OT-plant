#!/usr/bin/env bash
# Host-side validation of AD and optional Windows containers; never changes guest state.
set -euo pipefail
cd "$(dirname "$0")/.."
echo '=== Host prerequisites ==='
if [[ -c /dev/kvm ]];then echo '[PASS] /dev/kvm character device present';else echo '[FAIL] /dev/kvm not available';fi
if [[ -c /dev/net/tun ]];then echo '[PASS] /dev/net/tun present';else echo '[FAIL] /dev/net/tun not available';fi
for x in windows-media/windows11.iso windows-media/windowsserver2022.iso;do
  if [[ -s "$x" ]];then echo "[OK] ISO supplied: $x";else echo "[INFO] No ISO at $x (required for matching Windows profile)";fi
done
command -v docker >/dev/null || { echo '[WARN] Docker not installed: cannot perform AD/container checks'; exit 1; }
docker compose version || exit 1
cmd=(docker compose -f compose.yaml -f compose.windows.yaml)
"${cmd[@]}" config --quiet && echo '[PASS] Combined Compose config recognized'
"${cmd[@]}" ps
rc=0
for zone in 'dc01|10.0.0.10|corp.otlab.test' 'ics-dc01|172.18.10.10|ics.otlab.test';do
  IFS='|' read -r container ip realm <<< "$zone"
  if ! "${cmd[@]}" exec -T "$container" samba-tool domain info "$ip" >/dev/null 2>&1;then
    echo "[FAIL] $container Samba domain details inaccessible";rc=1
    continue
  fi
  echo "[PASS] $container domain responds at $ip"
  if "${cmd[@]}" exec -T "$container" sh -c "dig @$ip _ldap._tcp.$realm SRV +short | grep -iq $container";then
    echo "[PASS] $container LDAP DNS SRV record"
  else
    echo "[FAIL] $container SRV DNS lookup failed";rc=1
  fi
  if "${cmd[@]}" exec -T "$container" sh -c "dig @$ip _kerberos._tcp.$realm SRV +short | grep -iq $container";then
    echo "[PASS] $container Kerberos DNS SRV record"
  else
    echo "[FAIL] $container Kerberos DNS SRV lookup failed";rc=1
  fi
done
for svc in win-it win-server win-ot;do
 if "${cmd[@]}" ps -q "$svc" | grep -q .;then
   echo "[INFO] Windows VM service $svc exists; use Windows guest scripts to verify domain JOIN"
 else
   echo "[INFO] $svc not started (optional profile)"
 fi
done
exit "$rc"
