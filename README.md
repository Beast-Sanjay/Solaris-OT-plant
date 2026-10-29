# SOLARIS ONE v7 — Connected Solar Plant Purdue OT Lab

A containerized **10 MWac / 11.2 MWp** solar photovoltaic *digital twin* with real inter-container API/Modbus communications, 5 Purdue levels (L0–L4), an industrial DMZ, two Samba AD domains, a SOC, three optional Windows/QEMU guests, and a plant operations UI.

**Plant is simulated.** No live solar hardware, grid dispatch connection, real safety assurance, vendor-certified SunSpec mapping, or power-flow/protection accreditation is supplied.

## Download contents

- `compose.yaml` — **52 Compose service definitions**, including helper conduits and optional-profile utilities, across **9 isolated Docker networks**. Do not confuse the number of containers with the **15 operational solar asset records**.
- `services/solar_*.py` — actual weather/PV/inverter/PPC/transformer/feeder/relay/grid-dispatch/SCADA/historian processes.
- `services/solar_ui/` — solar control-room UI and live device-by-device asset explorer.
- `services/maintenance_bot.py` — CORP AD-gated historian → automatically generated SQL work orders.
- `compose.windows.yaml` — 3 optional `dockurr/windows` QEMU/KVM guests, provisioned from **user-supplied** Windows ISOs.
- `windows-tools/*.ps1` — guest-side Windows file-server, IT reporting, and OT engineering functionality.
- [Plant topology diagram](docs/topology.png), `docs/ASSET_ROLES.md`, `docs/DEVICE_MATRIX.md` — architectures, device purposes, interfaces and consequences.
- `scripts/` and `tests/` — provisioning, validation, test, and live smoke scripts.

## Deployment requirements

Use a dedicated Ubuntu/Linux VM (e.g., on Proxmox) with Docker Engine, Compose v2, Python 3.8+, and `python3-yaml`. Allow image download at build time. Plan at least 8 GB RAM for the core lab; full SOC search and/or Windows guests require substantially more. Check for IP overlaps with the listed Docker subnets. The VM must not be bridged into real OT or corporate control networks.

**Normal solar lab:**

```bash
sudo apt-get install -y python3-yaml git
./scripts/setup.sh       # generates local secrets; checks address overlaps
./scripts/up.sh          # builds and starts the core solar / AD / SOC / IT lab
./scripts/check_lab.sh   # on-host AD, historian, SQL fault-work-order, isolation checks
```

**Access (only on the Docker host loopback):**

| Web app / service | URL |
|---|---|
| Solar SCADA with operator controls | http://127.0.0.1:1882 |
| Individual live asset explorer | http://127.0.0.1:1882/assets |
| OT grid-dispatch order console | http://127.0.0.1:1883 |
| Enterprise solar maintenance / DB01 | http://127.0.0.1:18082 |
| AD-authenticated read-only historian | http://127.0.0.1:18080/api/devices/latest |
| CA01 demo certificate authority | http://127.0.0.1:18083/api/status |
| **Live external solar portal (analytics, enquiries and status)** | http://127.0.0.1:18081 |
| **Corporate AD public service desk** | http://127.0.0.1:18085 |
| **L0 field technician console (fault repair + injection)** | http://127.0.0.1:19002 |
| **SOC alert dashboard** | http://127.0.0.1:19090 |
| SOC events API | http://127.0.0.1:19090/api/events |
| IDMZ SSH jump | `127.0.0.1:2222` |

Credentials and simulator-only control token are generated into `.env` by `scripts/init_env.py`. `.env` is **not packaged in the ZIP**. The operator SCADA requires the `CONTROL_TOKEN` field from `.env` for control commands. This prototype uses training authentication and must not be publicly exposed or attached to real equipment.

## Every solar asset has a purpose

| Level | Asset | Physical / operating responsibility | Real consequence |
|---|---|---|---|
| L0 | `MET-01` | Irradiance, ambient/module temperature, wind | Drives independent field DC output |
| L0 | `PV-01` | Healthy 36-string reference | Baseline for comparing array outputs |
| L0 | `PV-02` | 7.5% soiled PV block | Lower AC generation and automated cleaning order |
| L0 | `PV-03` | Two failed strings | Measured string loss and automated repair order |
| L0 | `PV-04` | Separate fourth block and yield coefficient | Independently varies inverter output |
| L1 | `INV-01…04` | Four 2.5 MWac conversion controllers, native Modbus TCP | Respond to PPC caps; output measured at transformer |
| L1 | `TX-33KV-01` | Estimated 0.69/33 kV transformer, losses, winding temperature | Feeder imports its output, not a hard-coded PPC number |
| L1 | `FDR-33KV-01` | Outgoing breaker + revenue meter / integrated kWh | Open breaker means no exported power |
| L1 | `REL-33KV-01` | Independent protection relay / latched trip and reset | Trip prevents PPC from reclosing breaker |
| L2 | `PPC-01` | Polls four Modbus devices, applies lowest of grid/operator limits | Dispatch changes all four inverters and feeder power |
| L2 | `SCADA-01` | Dashboard, alarm views and token-gated commands | Operator setpoints and relay test cause real sim state changes |
| L3 | `GRID-ORDER-01` | Grid export-limit order entry | Enforced on PPC via read-only cross-zone feed |
| L3 | Historian | Persists time-series values for **15 assets** | Corporate / SOC gets asset evidence and alarms |
| L3 | `ICS-DC01` | Independent OT Samba domain | Domain join/auth for optional Windows engineering guest |

Supporting components are also assigned actual roles: the corporate `dc01` validates historian access; `db01` persists maintenance work orders; `maintenance-bot` reads historian with CORP AD and creates work orders for PV-02 and PV-03; the SOC ingests alarms; `ca01` issues training certificates; `jump-server` provides the IDMZ SSH terminal; the Docker conduits carry allowlisted cross-zone traffic. For complete producer/consumer pairs see **[docs/ASSET_ROLES.md](docs/ASSET_ROLES.md)**.

## End-to-end behaviors

**Generation:** MET → individual PV arrays → L0/L1 conduits → individual Modbus inverters → PPC → transformer → feeder → SCADA → L3 historian.

**Grid instructions:** OT grid-dispatch app → read-only L3/L2 conduit → PPC selects `min(grid limit, local operator limit)` → inverter curtailment → measured lower feeder export.

**Protection:** relay observes feeder current, frequency, voltage, transformer temperature. A simulator-only test trip latches feeder OPEN. Press **Reset relay latch** then separately **Close** to restore output. Manual closing before reset is rejected.

**Maintenance:** PV-02 and PV-03 fault fields propagate to historian. The L4 `maintenance-bot` authenticates with `it-access` against CORP Samba AD, then stores `AUTO-PV-02-SOILING` and `AUTO-PV-03-STRINGS` in PostgreSQL. The IT maintenance UI displays them and allows Corporate AD-authenticated approval/closure with an immutable SQL audit history. PV repair itself occurs separately at the isolated Level 0 field service console. This specific cross-AD/SQL flow requires full host Docker verification.

## External web application — functional public workflow (v7)

The public page `http://127.0.0.1:18081` now has:

- Responsive SOLARIS ONE site; live output, exported power, four-inverter availability, weather, historical graphs and an estimated (sample-integrated) MWh figure since 00:00 UTC. **Missing telemetry intervals are excluded**, not interpolated or silently filled; no numerical data is fabricated on disconnect.
- Public notices published and archived by corporate operators.
- A persisted enquiry form for virtual site visits, partnerships, data requests and general questions. SQLite survives restarts in Docker volume `public_portal_data`.
- Each form submission returns a randomly generated `SOL-...` reference and a private access code. Visitor can track progress and read a staff reply without authenticating or exposing anyone else's tickets. **The access code is shown once; the demonstration does not send email.**
- A separate corporate staff page at `http://127.0.0.1:18085` allows `CORP.OTLAB.TEST` users to review tickets, progress their status (`received → under_review → responded → closed`) and post public notices. This page requires working Corporate Samba LDAP sign-in.

**Network trust:** Nginx in Web DMZ only proxies public GET and ticket POST paths to `public-publisher`. `public-case-conduit` permits explicitly selected, shared-secret-authenticated staff routes from the IDMZ, used by `public-ops` (L4/IDMZ). No portal container joins L0/L1/L2 and public routes never proxy PLC/PPC/SCADA commands. All public host ports bind to `127.0.0.1`; there is **no automatic Internet exposure**. For a real Internet deployment, add HTTPS, DDoS and spam controls, secret rotation, operator MFA/authorization policy, and a privacy notice first. Personal data is a training demo and automatically expires after 90 days on service startup. Do not submit real customer data.

Public HTTP API: `GET /api/public`, `/api/public/history`, `/api/public/statistics`, `/api/public/notices`; `POST /api/enquiries`, `/api/enquiries/track`. Private management endpoints are reachable **only through the internal conduit** and are not forwarded by Nginx. Full details: `docs/EXTERNAL_PORTAL.md`.

Run `python3 scripts/smoke_external_portal.py` for **live local HTTP** tests with a fake historian (and real Nginx if installed). Host smoke also remains `./scripts/check_lab.sh`; it tests live Docker wiring, including directory services. No Windows guest is required for the public portal.

## Windows roles — optional genuine Windows guests

Supply your own licensed ISOs in `windows-media/windows11.iso` and `windows-media/windowsserver2022.iso`, then use a Linux Docker host with nested virtualization / `/dev/kvm`:

```bash
./scripts/windows-up.sh it       # http://127.0.0.1:8006 Windows 11 / CORP
./scripts/windows-up.sh server   # http://127.0.0.1:8007 Windows Server 2022 / CORP
./scripts/windows-up.sh ot       # http://127.0.0.1:8008 Windows 11 / ICS
./scripts/windows-doctor.sh
```

Once Windows is installed, manually join `CORP.OTLAB.TEST` (IT + Server) or `ICS.OTLAB.TEST` (OT engineering), then run the supplied **guest PowerShell scripts**:

- IT Windows: `Z:\Install-SolarWorkstation.ps1 -Role IT`, then `Z:\Get-SolarMaintenance.ps1` (export DB01 work orders to a local and optionally corporate SMB CSV).
- Windows Server: elevated `Z:\Install-SolarFileServer.ps1` (installs native Windows File Server role and an L4 `SolarMaintenance` SMB share).
- OT engineering Windows: `Z:\Install-SolarWorkstation.ps1 -Role OT`, then `Z:\Get-SolarEngineeringSnapshot.ps1` (poll read-only L3 SCADA and create an operational CSV).

These are **real Windows VM roles**, not extra preinstalled Docker application services. Installation, domain join, Windows licensing, QEMU network reachability, and guest scripts have not been exercised in this artifact environment. See [docs/WINDOWS_DOCKUR.md](docs/WINDOWS_DOCKUR.md).

## Optional original general OT protocol fleet

```bash
./scripts/setup.sh --full
./scripts/up.sh --full
./scripts/check_lab.sh --full
```

This opt-in mode downloads the upstream mrhOTshOT source and adds non-solar PLC protocol targets + FUXA. Those devices do **not** contribute to solar plant feeder generation. Their purpose is separate protocol detection/purple-team training, not renewable plant process behavior.

## Validation

Run without Docker:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate.py
python3 scripts/validate_windows.py
python3 scripts/smoke_v6.py
python3 scripts/smoke_solar.py
```

**Verified locally:** 24 Python tests and the full solar multi-process smoke suite, including the four native Modbus endpoints, grid curtailment, transformer-fed feeder, latching trip/reset behavior, historian storage and read-only SCADA API. **Not verified here:** complete Docker image builds/network isolation, Samba provisioning and real LDAP bind, actual automatic DB work-order insertion, Windows installation/domain join, browser rendering on your host. This environment does not have Docker/KVM. `scripts/check_lab.sh` tests the main dependencies when deployed on your Docker VM and fails on missing functionality.

Author credits for upstream project and third-party packages: [NOTICE.md](NOTICE.md).
