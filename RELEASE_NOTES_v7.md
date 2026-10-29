# SOLARIS ONE v7 — Functional external solar website

Changes since v6:

- Replaced the read-only external landing page with a fully interactive solar visitor website; all measurements still come from **simulated** solar assets and the filtered historian.
- Added observed exported MWh from persisted samples, fresh/stale status, live generation/export chart, public notice board, visitor enquiry submission and private tracking with staff replies.
- Added a persistent SQLite public-service store (`public_portal_data`) for tickets, notices and public summary telemetry; stored tracking credentials are hashed.
- Added a separate Corporate AD-authenticated staff web application (`public-ops`, port 18085) and tightly scoped, token-authenticated IDMZ case conduit. Neither endpoint has direct access to the controller or SCADA networks.
- Added rate limiting, input validation, allowlisted Nginx routes, content-security policy, and localhost-only host publication.
- Added live local HTTP tests of the service endpoints, actual Nginx public routes, and the staff conduit; added deployment checks for public API availability and anonymous access restrictions.

**Verification:** 30 Python unit tests, the independent v6 field-maintenance/publisher smoke, and live HTTP public portal smoke (including actual Nginx and private relay), plus static nine-zone Docker config checks, passed in the execution environment. One additional full solar-controller smoke attempt exceeded its timeout; this run is not counted as passed. These tests use a fake historian for the isolated public smoke. Full Docker Compose deployment, actual Samba LDAP login, PostgreSQL IT flows and dockurr/windows guests remain **unverified** here because there is no Docker/KVM runtime.

**No email delivery, real cloud hosting, physical power system, or production-grade public security** is claimed. The public app is functional inside this simulated training lab.
