# SOLARIS ONE v6 — Operational commissioning and acceptance matrix

**Scope:** Synthetic industrial power flow only. A passing test establishes that the modeled software behaves as described, **not** that it is physically accurate or safe for real plant control.

## Live asset responsibility matrix

| Device or service | Actual producer | Actual consumer / effect | Operational commissioning check |
|---|---|---|---|
| MET-01 | Accelerated irradiance / temperatures / wind | All four array output models | `met-station /api/state`, watch variable irradiance |
| PV-01 | 36-string reference DC output | INV-01 via L0/L1 conduit | `field-service /api/assets` → PV-01; confirm DC kW |
| PV-02 | DC power reduced by soiling | INV-02, historian, work-order bot | Clean PV-02 in field console; DC/AC output rises |
| PV-03 | DC current and output reduced by failed strings | INV-03, historian, work-order bot | Repair strings; failed count becomes zero, power rises |
| PV-04 | Independent temperature/yield model | INV-04, PPC plant sum | Compare PV-01 to PV-04 at common irradiance |
| INV-01–04 | Native Modbus TCP register map + AC kW | PPC L2 via individual gated conduits | `scripts/smoke_solar.py`: real Modbus frame via conduit |
| PPC-01 | Local and grid dispatch limits | Four inverter caps, transformer, breaker | Set cap from 100 to 20% in SCADA; export changes |
| TX-33KV-01 | Delivered power, losses, winding temp | Feeder/relay; monitored by PPC | Confirm delivered kW below incoming kW |
| FDR-33KV-01 | Export current, breaker, cumulative kWh | PPC, relay, historian | Open breaker: export = 0, PV field remains energized |
| REL-33KV-01 | Trip latch / reason | Feeder breaker; SOC alarm | Trip test → close denied → reset → deliberate close |
| GRID-ORDER-01 | Grid operator export ceiling/order ID | PPC via GET-only conduit | Order 40% at :1883; PPC honors lower of two limits |
| SCADA-01 | HMI, asset explorer and operator controls | PPC / historian | :1882 shows 15 live asset readings |
| Historian | SQLite time series, per-device history | SOC and authorized IT; public publisher | :18080 AD-authenticated `/api/devices/latest` |
| SOC collector | Persistent event queue, live browser UI | Detection analyst | :19090; simulate a PV fault, inspect new event |
| MAINT-BOT-01 | AD-gated automated fault proposals | DB01 work orders | PV-02 and PV-03 create auto references after AD ready |
| DB01 + Corporate portal | PostgreSQL work-order state and audit | IT maintenance staff and Windows report export | :18082; AD user approval and closure logged |
| Field Service | Real local change to PV simulation and audit log | Level 0 arrays / downstream generation | :19002; repair, cleaning, injection; restart persists |
| Public Publisher | Filtered L3 historian aggregate cache | Nginx web DMZ, no OT routes | :18081 `/api/public` & `/api/public/history` |
| Web server / WAN relay | Read-only solar website | Local/simulated visitor | :18081; confirms live simulated numbers |
| CORP DC01 | Samba LDAP/Kerberos/DNS | IT access gateway and corporate portal | `scripts/check_lab.sh` + `windows-doctor.sh` |
| ICS-DC01 | Separate Samba domain | Optional Win OT engineering guest | SRV DNS + Windows domain join on KVM host |
| CA01 | Real CSR signing and test certificates | Training certificate client / verification | Unit test `test_sign_and_verify_csr` |
| Jump server | SSH and read-only L3 historian query | Enterprise operator in industrial DMZ | SSH localhost:2222, run `ot-status` |
| WIN-IT / WIN-SERVER / WIN-OT | Optional QEMU virtual machines inside dockurr/windows | Domain-joined maintenance file share and OT reports | Install Windows, join correct domain, run supplied guest scripts |

## Local tests (without Docker)

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate.py
python3 scripts/validate_windows.py
python3 scripts/smoke_v6.py
python3 scripts/smoke_solar.py
```

The v6 smoke tests run on loopback using actual Python service subprocesses and real HTTP/Modbus frames. **They do not validate Linux Docker network isolation or the installed Windows operating systems.**

## Docker host commissioning (with Docker Engine)

```bash
./scripts/setup.sh
./scripts/up.sh
./scripts/check_lab.sh
```

`check_lab.sh` verifies Samba user provisioning, AD-authenticated historian reads, DB01 reachability, maintenance bot status, 15 historian devices, the public feed, PV field service, and Level 4 isolation. It is read-only: it does not open the breaker or alter plant setpoints.

## Manual multi-stage demonstration

1. Open SCADA `http://127.0.0.1:1882` and the live public dashboard `http://127.0.0.1:18081`. Wait for historian publication (~30 seconds after historian has data).
2. Check PV-02 condition in SCADA `/assets?asset=PV-02`; inspect `AUTO-PV-02-SOILING` in the corporate portal (requires a working Corporate AD, DB01, and maintenance bot).
3. At `http://127.0.0.1:19002`, enter the generated `CONTROL_TOKEN`, choose PV-02 → Clean. Observe new PV and inverter kW, PPC, feeder, historian. The public page follows with a delay.
4. On the corporate portal, enter Corporate AD credentials, approve the maintenance order, then close it **after** verifying the simulated repair. Each change writes an audit row. This is an administrative workflow, not a remote field command.
5. Use the grid portal `http://127.0.0.1:1883` to set an export limit. Observe curtailed inverter power.
6. Use SCADA relay test: trip, attempt to close, reset latch, deliberately close. Observe SOC events.
7. Restart an array container and check its maintenance state is retained in its Docker named volume.
8. If you want Windows guests, supply licensed ISO media and enable `/dev/kvm`, then run `./scripts/windows-up.sh it|server|ot` and guest-side join/role scripts.

## Verification boundaries

- Measured power, weather, faults, energy and protection are simplified **simulation**, not vendor-certified firmware.
- Optional original mrhOTshOT protocol PLC annex remains independent; those PLCs **do not feed the solar electrical bus**.
- Full Docker builds, Active Directory binds, PostgreSQL and Windows guest boots are not reproducible in the artifact environment where Docker and KVM are absent. Validate them on the deployment host before claiming real integrated completion.
- HTTP training credentials and shared tokens are not suitable for use on an Internet-facing production system. Host ports intentionally bind to `127.0.0.1`.
