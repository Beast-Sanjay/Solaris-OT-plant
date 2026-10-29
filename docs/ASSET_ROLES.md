# SOLARIS ONE v7 — Purpose-driven plant asset contracts

**Rule:** Every modeled plant asset has a producer, an operating responsibility, an observable consumer, and a reproducible failure or state-change consequence. Process simulations are educational; electrical calculations are intentionally simplified and not suitable for grid design, protection setting, or engineering certification.

## Operational devices — live chain

| Asset(s) | Role / produced data | Actual downstream consumer | Observable behavior |
|---|---|---|---|
| MET-01 (`met-station`, L0) | Irradiance, temperature and wind | Four PV arrays | Generation varies on accelerated daylight/cloud cycle |
| PV-01 (L0) | Healthy reference string block | INV-01 | Baseline yield at comparable irradiance |
| PV-02 (L0) | Soiling 7.5% | INV-02 / historian / maintenance bot | Lower DC/AC yield, auto cleaning work order |
| PV-03 (L0) | Two disconnected strings | INV-03 / historian / maintenance bot | Lower current / output, auto string-repair work order |
| PV-04 (L0) | Independent temperature/yield comparison block | INV-04 | Independent measured DC availability |
| INV-01…04 (L1) | Convert DC to AC; 12 live Modbus registers each | PPC via dedicated L1/L2 conduits | Curtailment commands alter actual AC output and meter |
| TX-33KV-01 (L1) | Aggregate 690 V AC bus step-up to 33 kV, losses, winding/oil temp | Feeder and relay | Power loss and temperature visible; feeder has no direct PPC power feed |
| FDR-33KV-01 (L1) | Revenue energy integration, line current, breaker, trip latch | Relay, PPC, SCADA, historian | Opening or tripping breaker stops grid export; latched trip prevents reclose |
| REL-33KV-01 (L1) | Protection checks / trip and reset | FDR-33KV-01 | Simulated trip results in relay latch; manual reset + separate close necessary |
| PPC-01 (L2) | Aggregates actual Modbus readings; applies min(grid order, operator cap) | Four inverters and transformer | Measured curtailment and feeder export change together |
| SCADA-01 (L2) | Real-time dashboards, alarms, operator control; asset explorer | Historian via read-only conduit | 15 asset records; controls authenticated, no direct L1 WAN publication |
| GRID-ORDER-01 (L3) | Grid dispatch ceiling and order ID | PPC via GET-only L3/L2 conduit | Reducing the ceiling changes plant production and feeder export |
| Historian (L3) | SQL time series for 15 assets, alarm emission | AD-gated historian gateway and SOC | Time-stamped values visible to authorized IT; alarms forwarded to SOC |
| ICS-DC01 (L3) | Separate Samba AD/Kerberos/DNS domain | Windows OT engineering guest (once joined) | Authenticates OT engineering login; no IT trust |

## Supporting IT, network, and security assets

| Service | Actual function / use | Demonstration or validation |
|---|---|---|
| `array-conduit-01..04` | L0→L1 allowlisted PV readings | Inverter DC values respond to each array |
| `inverter-conduit-01..04` | L1↔L2 private Modbus and PPC command relay | SCADA reports four healthy native Modbus sessions and authenticated PPC limit updates |
| `transformer-conduit` | PPC sends measured bus power to L1 transformer | Transformer reports input/loss/delivered output |
| `feeder-conduit`, `relay-conduit` | Restricted telemetry/control crossing L1↔L2 | Breaker and protection state seen by PPC; token required for writes |
| `grid-conduit` | Read-only L3→L2 grid order delivery | PPC uses grid ceiling, no grid control on L2 endpoint |
| `supervisory-conduit` | SCADA read-only status to L3 | Historian saves values; no control permitted |
| `soc-conduit` | L3→SOC alert POST | PV faults / relay trip / feeder open generate SOC events |
| `historian-conduit` | L3/IDMZ historian GET only | IT cannot address L1 directly |
| `jump-server`, `jump-entry` | IDMZ SSH landing + read-only historian tooling | IT SSH terminal into IDMZ, no default L1 network |
| `dc01` | Real Corporate Samba AD/Kerberos/DNS | IT analyst binds via LDAP to `it-access` |
| `it-access` | Validates Corporate AD user; GET historical readings across IDMZ | Invalid credentials fail; valid analyst gets historian asset data |
| `it-workstation` | Linux corporate client used for AD/DNS tests and read-only queries | `scripts/check_lab.sh` confirms corporate-only access |
| `db01` | PostgreSQL for maintenance work orders | `corp-portal` UI shows persisted records |
| `maintenance-bot` | Uses CORP AD account to read historian through `it-access`; creates SQL fault work orders | PV-02 and PV-03 automatically create two work orders once AD and containers are ready |
| `corp-portal` | DB01 orders, Corporate AD-authenticated approve/close transitions and immutable audit trail | Browser `http://localhost:18082` |
| `ca01` | Signs and verifies lab CSRs (training CA; not Windows ADCS) | API and unit tests demonstrate certificate issuance |
| `soc-collector` | Stores solar process and communication events; serves working SOC dashboard | `http://localhost:19090/` and `/api/events` |
| `public-publisher`, `web-server`, `web-entry` | Filtered live plant metrics, graph data, observed MWh, public notices and persisted visitor enquiries | `http://localhost:18081`; visitor receives tracking reference/access code; no controller endpoint is reachable |
| `public-case-conduit`, `public-ops` | Shared-secret-gated private case relay from Web DMZ through IDMZ to L4 AD-authenticated staff UI | `http://localhost:18085`; staff responds, transitions cases and publishes/archives announcements; public visitor can track replies |
| `field-service` | Level 0 technician service with authenticated cleaning, string repair, injected faults and SQLite intervention audit | `http://localhost:19002` · edits persist in PV block volume; downstream DC/AC/export change |
| `elastic`, `kibana` | Optional SOC log search and visualization | `--profile elastic`; non-essential to core power flow |
| `attacker` | Optional simulated WAN test node | `--profile redteam`; not started by default |

## Windows workstations / servers (optional real guests)

The Windows guests boot actual Windows with **dockurr/windows QEMU/KVM**. None is ready to perform a Windows role until a licensed OS is installed, joined to the appropriate Samba domain, and its corresponding **guest-side PowerShell setup** has run.

- **Windows 11 IT (`win-it`, CORP/L4):** corporate maintenance operator. Run `Z:\Install-SolarWorkstation.ps1 -Role IT`, then `Z:\Get-SolarMaintenance.ps1` to export live SQL work orders to CSV and the approved L4 SMB share.
- **Windows Server 2022 (`win-server`, CORP/L4):** domain-joined file server. Run elevated `Z:\Install-SolarFileServer.ps1`; creates a native Windows SMB share for maintenance reports (no fake file-server placeholder).
- **Windows 11 OT engineering (`win-ot`, ICS/L3):** read-only engineering inspection. Run `Z:\Install-SolarWorkstation.ps1 -Role OT` then `Z:\Get-SolarEngineeringSnapshot.ps1`; reads SCADA through L3 read-only gateway, produces time-stamped CSV, and has no L1 controller NIC or control API.

**Limitations:** The optional original mrhOTshOT annex is a separate training set. Its general ICS protocol PLCs are not connected electrically to this solar plant. Avoid including them in a solar-only exercise unless an explicit use case is created. No licensed proprietary software, live utility dispatch, physical PV hardware, or protection-grade relay logic is included.

## Reproducible demonstrations

1. **PV fault → work order:** PV-02 has 7.5% soiling; PV-03 has two disconnected strings. The inverter readings reflect this, historian records the fault fields, then the `maintenance-bot` creates `AUTO-PV-02-SOILING` and `AUTO-PV-03-STRINGS` in `db01` via AD-gated access.
2. **Grid order → export limit:** Send an authenticated `POST /api/order` to grid-dispatch `:1883` with `{"order_id":"DISPATCH-001","export_limit_pct":40}`. The PPC respects the new 40% upper limit, independent of the local operator slider.
3. **Protective trip:** SCADA `Protection relay TEST TRIP` sets a breaker trip latch. An attempted close returns HTTP 409 until `Reset relay latch`, then a separate breaker close. All values are recorded as simulated history.
4. **Engineering / IT split:** The OT Windows guest can only read L3 SCADA state; the IT guest accesses plant history only after Corporate AD verification and can collect maintenance work orders. Neither has an L1 NIC.

## Validation boundaries

Local Python smoke tests exercise simulator HTTP + native Modbus and 15 device historian records. They **do not prove** real Docker images build, Samba AD is provisioned, the maintenance bot completes authenticated SQL writes, or Windows guests boot and join domains. Run `./scripts/check_lab.sh` and `./scripts/windows-doctor.sh` on the Docker host, then perform each Windows guest script and connectivity checks.
