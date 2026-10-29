# Solar Lab troubleshooting

Run `./scripts/check_lab.sh` after containers start; it checks the actual device paths without sending control commands.

## Start commands

```bash
./scripts/setup.sh
./scripts/up.sh
docker compose ps
docker compose logs --tail=100 ppc-01 scada inverter-01 feeder-33kv historian
```

The first start requires Docker image pulls; there is no Docker daemon in the package-building environment, so full Compose startup remains unverified there.

## Missing PV telemetry / SCADA shows offline

- `docker compose logs met-station pv-array-01 inverter-01 inverter-conduit-01 ppc-01 scada` shows the whole flow.
- In Compose, `met-station` and PV blocks share only **level0**. The inverter can query the PV field only through `array-conduit-01` (L0↔L1).
- PPC queries each inverter through its matching `inverter-conduit-*` (L1↔L2), over both native Modbus and JSON.
- Run `docker compose exec -T ppc-01 python -c "from urllib.request import urlopen; print(urlopen('http://inverter-conduit-01:8080/api/state').read()[:200])"`.
- Check the Docker network IP ranges for overlap with existing Proxmox bridges or VPN routes.

## Feeder export reads zero

Check if `feeder.breaker_closed` is `false` or `export_limit_pct` is zero in `http://127.0.0.1:1882/api/state`. In this model an open feeder commands **zero inverter AC output**. Use the SCADA operator controls and `.env` token to close the breaker or adjust the limit.

## Operator dispatch says unauthorized

`grep '^CONTROL_TOKEN=' .env` to find the token. Enter it using **Operator access token** in the SCADA interface. A token is created on first setup and is never silently rotated. This is local training authorization, not production RBAC.

## AD never becomes ready

```bash
docker compose logs --tail=120 dc01 ics-dc01
docker compose exec dc01 samba-tool user show analyst
docker compose exec ics-dc01 samba-tool user show icsoperator
```

Existing Samba volumes can retain previously provisioned realm or password state; do not delete volumes if you need to preserve domain objects. Samba provisioning may require xattrs and appropriate Linux volume handling. Keep the DC IPs static.

## DB01 maintenance page empty

```bash
./scripts/migrate_db.sh
docker compose logs db01 corp-portal
curl -s http://127.0.0.1:18082/api/workorders
```

## Need original protocol targets and FUXA

```bash
sudo apt-get install -y git python3-yaml
./scripts/setup.sh --full
./scripts/up.sh --full
./scripts/check_lab.sh --full
```

The original HMI shows **heating and substation** operations, not Solar PV. Only the new port `1882` UI displays the solar plant. Upstream Caldera and dashboard are deliberately not enabled in strict-mode Purdue design.
