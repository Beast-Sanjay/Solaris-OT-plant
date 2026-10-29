# SOC / asset discovery / original mrhOTshOT integrations

## Original mrhOTshOT

The upstream repository (`AsherDLL/mrhOTshOT_Docker_pub`) has a flat `otlab` management backbone plus `it-net`, `ot-net`, and `mgmt-net`, with original FUXA, Caldera, attack dashboard and router. In strict mode the adapter remaps original protocol targets and SIS to our `level1`, and FUXA to `level2`, without publishing industrial protocol ports on the host. The universal backbone, Caldera agent, attack runner, and deliberately vulnerable original router are **not brought into this deployment**.

Adapter code: `scripts/integrate_upstream.py`. It reads `upstream/docker/docker-compose.yml` on the Docker host and writes `compose.mrhotshot.yaml`. It does not edit original upstream files. The original HMI seed script must be run from the `upstream` directory. Change the mode to an isolated legacy lab VM if you need the original attack-scenario experience; do not make the strict network flat just to make old scenarios work.

## Sensor visibility: Zeek, Suricata, Malcolm

An isolated `soc` Docker bridge alone provides **no SPAN/TAP**. A container connected to the SOC bridge does not see unrelated packets across the L1/L2/DMZ bridges. For realistic passive OT monitoring, mirror bridge-side veth packets to a capture interface or use host-network AF_PACKET on the correct Docker bridge interfaces. Use `docker network inspect` and Linux `ip link` to identify bridge interfaces (names are not guaranteed stable). Avoid generating duplicate alert streams when observing both ingress and egress of the same cross-zone flow.

Suggested passive observation coverage for ASTRICS:

- L1 `plc-*` and `sis` process communications (industrial Modbus, IEC104, DNP3, BACnet, OPC UA, S7, etc. as exposed by upstream).
- L2 -> L1 `control-conduit` (source and destination with unmodified Modbus TCP payloads).
- Level 4 -> Industrial DMZ `it-access` HTTPS would be appropriate in a hardened lab; the current gateway uses localhost HTTP Basic and LDAP over LDAPS.
- Level 3 historian, `soc-conduit` and authentication-audit events.

For a passive application event feed, the L3 historian's threshold alert calls `POST http://soc-conduit:8080/api/events`, which is sent through a dedicated Level3+SOC HTTP-only gateway. SOC collector persists events in SQLite and (when the optional elastic service exists) forwards events to `purdue-events` in Elasticsearch. This **is not a complete IDS**, and the current SOC collector has no network-packet analyzer.

### Malcolm

Malcolm can be deployed on **a separate, sufficiently large monitoring VM**, per its upstream hardware and licensing requirements. It is intentionally not embedded or auto-downloaded here. Route mirrored packets/pcaps to Malcolm's own ingest path, or export structured events to a pipeline that can ingest them. Do not connect Malcolm's management plane to Level 1/0 as a general network gateway. The original repo has a Suricata sensor option (`make sensor-up`), but its `otlab`/`it-net` assumptions differ from our strict bridges; reconfigure capture interfaces before reuse.

## Modbus register map: `plc-demo:15020` inside L1

FC03/04 reads (0-based holding-register offsets):

| Offset | Meaning | Encoding |
| --- | --- | --- |
| 0 | Tank level | percent ×10, unsigned 16-bit |
| 1 | Pump running | 0/1 |
| 2 | Flow | L/min ×10 |
| 3 | Temperature | Celsius ×10 |
| 4 | Pump setpoint | percent, 10–90 |
| 5 | Field communication healthy | 0/1 |

FC06 write allowed only to offset 4 (setpoint). This demo provides **no physical process control**. The Level 2 SCADA uses FC03 and does not issue writes. Writes are available for authorized simulation from Level 1 or the designated Level 2 conduit.

## Production migration checklist

Before using any of these patterns beyond a fenced-off cyber lab: replace application relays with stateful industrial firewalls and flow enforcement, build actual IT/OT identity federation (if needed) with least privilege, use validated TLS/PKI for LDAPS and HTTP, implement logs for all denied flows and authentication attempts, enforce MFA on jump/brokers, retain packets with proper privacy controls, pin and verify upstream commits/images, and independently test fail-closed behaviour on conduit failure.
