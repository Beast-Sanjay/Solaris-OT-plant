# SOLARIS ONE v5 — Solar asset ports and data contracts

The plant is a teaching simulator, not a vendor-certified Modbus / SunSpec implementation. All physical and security events are synthetic.

| Role | Docker name(s) | Zone | Protocols | Inputs → outputs |
|---|---|---|---|---|
| Weather station | `met-station` | L0 | HTTP 8080 | Accelerated time → irradiance, ambient/module temp, wind |
| PV blocks | `pv-array-01..04` | L0 | HTTP 8080 | MET-01 weather + soiling + string failures → DC kW, string current, voltage |
| DC/AC inverters | `inverter-01..04` | L1 | HTTP 8080, native Modbus TCP 15020 | Each PV DC power + PPC cap → AC kW, energy, voltage, current, PF, temperature |
| Step-up transformer | `transformer-33kv` | L1 | HTTP 8080 | PPC input kW → estimated 33 kV delivered kW, losses, winding temperature |
| Feeder/breaker/meter | `feeder-33kv` | L1 | HTTP 8080 | Transformer output + relay trip → grid export, current, cumulative kWh, trip latch |
| Protection relay | `protection-relay` | L1 | HTTP 8080 | Feeder V/I/frequency, TX temperature → independent trip/reset commands |
| Plant controller | `ppc-01` | L2 | HTTP 8080 / Modbus client | Four inverters + grid order → dispatch cap, transformer bus input, breaker commands |
| Solar SCADA | `scada` | L2 | HTTP 8080, host localhost:1882 | PPC → operator screen, alarms, simulator-only control; `/assets` explorer |
| Grid orders | `grid-dispatch` | L3 | HTTP 8080, host localhost:1883 | Order ID + export limit → GET-only L2 dispatch constraint |
| Historian | `historian` | L3 | HTTP 8080 | L2 SCADA state → persistent 15 asset records + SOC events |
| Maintenance planner | `maintenance-bot` | L4 | HTTP/AD Basic/SQL | AD-authenticated historical fault → DB01 work orders |

All devices are on Docker-private Purdue zone bridges. The host has no published Modbus 15020 ports. The cross-zone application/Modbus conduits implement narrow allowlists; they are **not** production network firewalls.

### Inverter native Modbus TCP map (zero-based holding registers; FC03 or FC04)

| Register | Encoding |
|---|---|
| 0 | AC kW × 10 |
| 1 | Consumed DC kW × 10 |
| 2 | AC voltage V |
| 3 | AC current A × 10 |
| 4 | Frequency Hz × 100 |
| 5 | Module temperature °C × 10 |
| 6 | Irradiance W/m² |
| 7 | PPC limit % × 10 |
| 8 | Inverter running / online |
| 9 | Integrated kWh lower 16 bits |
| 10 | Power factor × 1000 |
| 11 | PV-array communications connected |

Only Modbus register reads are supported. PPC command writes use token-authenticated HTTP on the internal network. All ranges and protection thresholds are invented simulator settings and must not be used for real PV equipment.

### API examples

- `GET http://localhost:1882/api/state` — full live plant and 15 asset views.
- `GET http://localhost:1882/assets` — per-device telemetry explorer.
- `POST http://localhost:1882/api/control` with `X-Lab-Control-Token: $CONTROL_TOKEN` and JSON `{"export_limit_pct":35}` — simulator operator limit.
- `POST http://localhost:1882/api/control` with JSON `{"relay_action":"test_trip"}` — simulated relay test trip; reset separately via `{"relay_action":"reset_trip"}`.
- `POST http://localhost:1883/api/order` with header `X-Grid-Token: $CONTROL_TOKEN` and JSON `{"order_id":"GRID-001","export_limit_pct":40}` — grid dispatch ceiling.
- `GET http://localhost:18080/api/devices/latest` with CORP AD Basic credentials — read-only historian evidence.

See [ASSET_ROLES.md](ASSET_ROLES.md) for every container's functional producer/consumer obligation and Windows workflows.
