# SOLARIS ONE v7 — External solar plant portal

## Purpose

The website is a working simulated solar-plant visitor portal, not a controller HMI. It publishes selected historian measurements, calculates observations from persisted aggregates, displays notices, accepts visitor requests, generates tracking receipts and allows authenticated corporate operators to respond. It **never** writes a plant setpoint, controls a breaker or queries a PLC directly.

## Applications

| Component | Container | Network | Host URL / interface |
|---|---|---|---|
| Public solar site | `web-server` / Nginx | Web DMZ | `http://127.0.0.1:18081` |
| Safe data/visitor backend | `public-publisher` | Web DMZ + IDMZ | Only private service address |
| Corporate case relay | `public-case-conduit` | Web DMZ + IDMZ | Only private service address |
| Staff portal | `public-ops` | L4 + IDMZ | `http://127.0.0.1:18085` |
| Historical source | `historian` via `historian-conduit` | L3 → IDMZ | Get-only allowlist, never public |
| Identity provider | `dc01` Samba AD | L4 | Corp AD LDAP bind |

## Public site workflows

1. **Live generation:** `/api/public` is updated every 30 seconds from L3 historian. Current DC/DC-to-AC is modeled in the plant, while the public feed only shows total generation and export, irradiance, available inverter count, alarm summary and an illustrative CO₂ impact rate. A communication failure sets `online=false`; client marks data stale.
2. **Analytics:** `/api/public/history` returns recent allowlisted samples for a two-series chart; `/api/public/statistics` calculates observed exported energy since 00:00 UTC from cached feeder samples. If two samples are separated by more than 3 × the poll interval, the period is excluded rather than extrapolated. This is **not** audited production metering.
3. **Site announcements:** `/api/public/notices` returns active corporate notices. Staff can create/archive notices on the private dashboard; any notices that are archived disappear on the next public poll.
4. **Enquiry:** Public visitor chooses `site_visit`, `partnership`, `data_request` or `general`, enters name, email and a message. `POST /api/enquiries` validates and stores the request in SQLite, returning a unique reference and one-time-shown access code. Email is stored for the staff desk but **no email is sent**.
5. **Tracking:** `POST /api/enquiries/track` with both reference and access code returns ticket status and any staff response. The code is hashed in the database. Without a matching pair, the endpoint returns 404 rather than disclosing whether a request exists.
6. **Staff response:** Staff navigate to port `18085` and enter their Corporate Samba AD credentials. The API rejects anonymous access, then the staff UI lists requests, permits valid transitions, stores their response, and publishes notices. After status changes, the visitor can track the new status.

## End-to-end exercise

```bash
./scripts/setup.sh
./scripts/up.sh
./scripts/check_lab.sh
python3 scripts/smoke_external_portal.py
```

Open the public site and check that data is received. Submit a sample request using **fictional contact data**, and save the generated reference + code. Open `http://127.0.0.1:18085` on the **Docker host**, use the `analyst` Corporate AD account (password stored in `.env`), load the case, set it to `under_review`, then `responded` with a reply. Return to the public site, select **Track a request**, enter the two saved strings and verify the response. Publish a notice from the staff UI and confirm it appears on the public site. No OT command should ever be sent as part of this flow.

For container debugging:

```bash
docker compose -f compose.yaml logs --tail=100 public-publisher public-case-conduit public-ops web-server
docker compose -f compose.yaml exec public-publisher ls -l /data
curl -s http://127.0.0.1:18081/api/public
curl -s http://127.0.0.1:18081/api/public/statistics
curl -s http://127.0.0.1:18081/api/public/notices
```

## Access control and safety

- Nginx permits **only** documented public GET paths and two strictly bounded POST paths. Internal and control routes return 404. Static files are self-hosted; no external JS/CDN is loaded.
- Corporate case access uses two checks: Samba AD sign-in at `public-ops`, followed by a dedicated shared secret at the IDMZ conduit and publisher. There is no network route from either public service to SCADA/PPC/PLC networks.
- Public POST data is bounded (2 KB JSON), validated and rate-limited (5 tickets/hour per source at the application; additional Nginx request throttling). Basic honeypot input reduces automated submissions. Visitor access codes are high-entropy and never stored in plaintext.
- Customer PII lives in `public_portal_data` (SQLite volume). Requests older than 90 days are purged on service startup; implement a periodic retention job before Internet exposure. Do not use real customer data in this training range.
- Public ports bind to localhost. This is **not** deployment-ready for the Internet. Production would require HTTPS termination, WAF/abuse handling, robust authenticated staff sessions/MFA, least-privilege AD groups, a mail service for notifications, secrets management and independent privacy/security review. Existing `corp_portal.verify_ad` disables upstream TLS certificate validation, which is acceptable only for an isolated lab and must be changed before real deployment.
- No Windows VM is required for public access; Samba AD itself must be working for staff case management. Full Samba initialization and Docker networking cannot be proven without starting containers on the target host.

## Verification boundary

The isolated HTTP smoke starts a real publisher and a fake historian; it validates the authenticated relay, live requests, persistence, tracking, notices and — when local Nginx is present — the public reverse proxy. This test does **not** establish that the full Compose stack builds, AD authentication works at runtime or Windows guests boot. Verify those separately on your Linux/KVM host.
