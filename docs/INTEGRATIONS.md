# Integrations — SOLARIS ONE

## Network zones

All nine internal Docker networks are intentionally isolated. The solar plant uses explicit cross-zone read-only and write-limited conduits. L4 has no direct route to L1; enterprise users can request historical data only via the AD-authenticated IDMZ API gateway.

## Active Directory

Samba DC `dc01` represents CORP IT, with a separate Samba DC `ics-dc01` for operations. They are **not domain-joined to each other** and do not have a forest trust. The corporate analyst can access only the historian gateway (read-only):

```bash
set -a; source .env; set +a
curl -u "analyst:$CORP_AD_ANALYST_PASSWORD" \
  http://127.0.0.1:18080/api/devices/latest
```

This Basic-authentication test gateway is loopback-only, and is not production TLS/PKI hardened.

## OPC / FUXA / original mrhOTshOT targets

Optional `./scripts/setup.sh --full && ./scripts/up.sh --full` clones the upstream repository and adds its original 11 protocol targets, SIS, and FUXA in an *independent legacy protocol demonstration annex*. FUXA's two existing views are a district-heating and substation demo; they are **not** representations of the solar plant. The new solar SCADA at port 1882 displays the 10 MW PV process.

The original mrhOTshOT console and Caldera agent use a shared management network and are not deployed in strict Purdue mode. Their deployment would bypass the segmentation assumptions. To obtain native SunSpec-certified simulation, IEC 61850/IEC 104 power-plant operations, and a full engineering power-flow model, further implementations are required.

## SOC and threat detection

The historian posts inverter outages and feeder-open alarms through an application-limited conduit to `soc-collector`. Optional Elasticsearch and Kibana use `docker compose --profile elastic ...`; no automatic Zeek/Suri packet tap is included. Use a packet mirroring setup on the lab VM for passive security monitoring.

## Sample APIs

```bash
# Plant + inverter state
curl http://127.0.0.1:1882/api/state
# Corporate IT app
curl http://127.0.0.1:18082/api/workorders
# AD-authenticated, read-only historian data
curl -u "analyst:$CORP_AD_ANALYST_PASSWORD" http://127.0.0.1:18080/api/plant/history?limit=10
# Token-protected simulated PPC setpoint (0-100%); use your local .env token
curl -H "X-Lab-Control-Token: $CONTROL_TOKEN" -H 'Content-Type: application/json' \
  -d '{"export_limit_pct":60}' http://127.0.0.1:1882/api/control
```

Do not attach these simulator APIs to operating inverters or grid protection equipment.


### Windows guests using dockur/windows (v4)

Opt-in Windows 11 / Windows Server guests are provided in `compose.windows.yaml`.
They run QEMU/KVM Windows VMs inside Docker containers, **not native Windows
containers**. Corporate guests use the `level4` network and Samba `dc01`; OT
engineering uses `level3` and `ics-dc01`. Domain joins are manual to avoid
placing AD administrator passwords in the container environment. Each guest
requires KVM and a locally staged ISO because zone networks are internal.

See [WINDOWS_DOCKUR.md](WINDOWS_DOCKUR.md) for full deployment, Windows
PowerShell onboarding, DNS/LDAP/Kerberos verification, and security boundaries.
