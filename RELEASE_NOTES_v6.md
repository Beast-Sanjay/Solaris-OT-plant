# SOLARIS ONE v6 — Functional assets update

New compared with v5:

- **Fixed critical cross-zone control issue.** Old HTTP conduits stripped `X-PPC-Token`; PPC POSTs to inverter, transformer, relay and feeder could fail on Docker. New conduits enforce and forward verified credentials for allowlisted control routes. SOC telemetry has an explicit POST-only exception.
- **Field technician service** (`field-service`, Purdue Level 0, `127.0.0.1:19002`): authenticated array cleaning, fault injection, failed-string repair, durable device state, service log. The service cannot reach other Purdue networks.
- **Public solar website is now a functional data consumer** (`127.0.0.1:18081`): read-only, sanitized, cached output from the L3 historian via the IDMZ publisher, live generation/export, irradiation, illustrative CO2 rate and history chart.
- **Corporate maintenance operations**: authenticated Corporate Samba AD approvals and closure for work orders with SQL event/audit history. No network path from Corporate IT to Level 0 devices.
- **SOC browser UI** (`127.0.0.1:19090`) for stored historian events.
- **Conduit-integrated smoke tests** (actual TCP Modbus frames and authenticated HTTP through relay subprocesses), PV repair propagation tests, and publisher leak-negative tests.
- **Updated read-only host diagnostics**, per-device acceptance matrix and network diagram.

Verification performed here: 24 Python tests; synthetic field repair/secure relay/public pipeline smoke; complete local solar process chain (four inverters, PPC, transformer, relay, feeder, SCADA, historian) passing **through local conduit subprocesses**; static YAML/network checks.

What remains **unverified in this environment** (Docker and `/dev/kvm` unavailable): full Compose container startup, live Samba provisioning and LDAP bind, PostgreSQL work-order transaction over real DB01, Nginx browser rendering on a deployed host, Windows ISO installation, and domain join. Run `scripts/check_lab.sh` and guest diagnostics on the actual Docker/Proxmox VM.

Do not connect these simulated controllers to real industrial networks.
