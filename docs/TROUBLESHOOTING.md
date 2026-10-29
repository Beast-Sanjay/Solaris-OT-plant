# Troubleshooting and deployment acceptance checks

These steps run on the **Linux VM where Docker Engine is installed**, not in the package authoring sandbox.

## Before building

1. Check `docker compose version` and `docker info`.
2. `python3 scripts/init_env.py`, `python3 scripts/validate.py`, and `python3 scripts/host_preflight.py`.
3. Verify `/mnt/data` or other Docker volumes are on a filesystem supporting POSIX ACL and security xattrs. Samba AD domain-controller provisioning sometimes requires extra privileges/capabilities on nested Docker/Proxmox storage; the two DCs use `cap_add: SYS_ADMIN` but are **not privileged** by default.
4. Ensure images can be pulled: `python:3.12-slim`, `debian:bookworm-slim`, `postgres:16-alpine`, `nginx:1.27-alpine`. Optional Elastic 8.17.0 images require access to `docker.elastic.co`.
5. Do not run the original mrhOTshOT stack simultaneously: it publishes some of the same host ports and uses incompatible flat networking.

## Compose validation (mandatory before trusting a deployment)

```bash
docker compose -f compose.yaml config >/tmp/purdue-rendered-compose.yaml
# full mode only:
docker compose -f compose.yaml -f compose.mrhotshot.yaml config >/tmp/purdue-full-rendered-compose.yaml
```

Check `docker compose ps` and logs after startup:

```bash
docker compose logs --tail=100 dc01 ics-dc01 it-access plc-demo scada historian
docker compose exec dc01 samba-tool domain level show
docker compose exec ics-dc01 samba-tool domain level show
docker compose exec it-workstation dig @10.0.0.10 _ldap._tcp.corp.otlab.test SRV +short
```

## Samba AD fails provisioning or LDAP returns 401

- Look for DNS bind errors on port 53, missing filesystem xattr/ACL support, Samba security ACL set failures, or wrong static IP.
- Samba first provisioning of `/var/lib/samba/private/sam.ldb` must complete successfully. If it fails halfway, stop the stack and troubleshoot; do not blindly delete DC volumes unless you want to start a **new** domain.
- AD domain users are created **once**, during initial provisioning. Editing `.env` after the first boot does not rotate passwords or re-create accounts. To rotate, use `samba-tool user setpassword analyst` inside dc01 and adjust clients.
- `it-access` uses LDAPS 636 with an unverified locally generated Samba certificate; ensure Samba is listening on 636 (check `ss -lntp` inside the DC if available). The gateway currently suppresses specific bind errors and returns HTTP 401. For controlled debugging, test authentication with LDAP tools from an IT-zone container.
- Samba stores its certificate and realm configuration in its data volume. A production deployment must verify the CA chain; this training lab intentionally does not.
- Some host filesystems and rootless Docker configurations cannot run Samba AD ACLs reliably. For production use a real Windows Server AD VM or a separately validated Samba VM.

## FUXA missing targets after full install

The legacy FUXA seed file expects `plc-heating` on Modbus TCP/502. In strict mode, `plc-heating` is a DNS alias **inside Level 2** pointing at `control-conduit`, while the real Level 1 PLC also has `plc-heating-l1` alias for the conduit. Check:

```bash
docker compose -f compose.yaml -f compose.mrhotshot.yaml ps
# Only FUXA is on Level 2; the original target is on Level 1.
# Once services are ready, seed the FUXA UI:
(cd upstream && python3 scripts/seed_fuxa_hmi.py --wait)
```

All original PLC services retain their original protocol ports inside Level 1, but host-port publication is removed. A scenario written for the original dashboard/Caldera/flat network **will not necessarily work** in strict mode. Don't restore the shared `otlab` bridge: it would defeat the intended topology.

## Connection policy testing

`it-access` is an HTTP gateway: it validates credentials against the corporate AD domain; the only proxied routes are `/api/latest` and `/api/history`. An attempt to send `POST` to the historian through this gateway is not supported. The historian has no direct Level 4 network interface, and the workstation cannot resolve Level 1 service names via the Level 4 Docker DNS. For a higher-assurance audit, inspect every container's network membership with:

```bash
docker inspect "$(docker compose ps -q it-access)" --format '{{json .NetworkSettings.Networks}}'
docker inspect "$(docker compose ps -q plc-demo)" --format '{{json .NetworkSettings.Networks}}'
```

No Docker bridge automatically guarantees that packets from an unrelated external interface are blocked: verify host firewalling and that the Docker daemon is not configured to permit direct routed inter-bridge access. `internal: true` plus app-level gateways is an architectural baseline, not a validated industrial firewall appliance.

## Package regression tests

`python3 scripts/validate.py` checks static topology and published ports; `python3 -m unittest discover -s tests -v` checks Modbus framing and generated upstream overlay conventions; `python3 scripts/smoke_local.py` performs a local end-to-end L0/L1/L2/L3/SOC pipeline run. It does not prove Kerberos, Samba, full Docker startup or real firewall isolation.
