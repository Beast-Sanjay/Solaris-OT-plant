"""Power Plant Controller: polls four independent inverter Modbus servers.
Allocates plant-level active power target to inverter limits via Modbus FC06.
"""
import copy
import os
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
from common import Handler, body_json, request_json, send_json, read_regs, write_reg

FIELD = os.getenv('FIELD_URL', 'http://solar-field-conduit:8080')
HOSTS = [x.strip() for x in os.getenv('INVERTER_HOSTS', 'solar-inverter-01,solar-inverter-02,solar-inverter-03,solar-inverter-04').split(',')]
INVERTERS = [f'INV-{i:02d}' for i in range(1, len(HOSTS)+1)]
PORTS = [int(p) for p in os.getenv('INVERTER_PORTS', ','.join(['502']*len(HOSTS))).split(',')]
if len(PORTS) != len(HOSTS): raise ValueError('INVERTER_PORTS length mismatch')
TRANSFORMER_EFF = 0.985
lock = threading.RLock()
target_export_mw = 100.0
status = {'connected': False, 'last_poll': None, 'target_export_mw': 100.0, 'device_status': {}, 'plant': {}}


def distribute(target_mw, available_mw):
    """Allocate inverter AC output MW so feeder export <= PPC target MW.
    Independently disconnected inverters get zero; handles insufficient sunlight.
    """
    if target_mw < 0: raise ValueError('negative target')
    available = [max(0.0, min(25.0, float(x))) for x in available_mw]
    total = sum(available)
    required = min(total, target_mw / TRANSFORMER_EFF)
    return [0.0 if total == 0 else required * cap / total for cap in available]


def control_once():
    global status
    plant = request_json(FIELD + '/api/state')
    with lock: target = target_export_mw
    caps = []
    devices = {}
    for ident, host, port in zip(INVERTERS, HOSTS, PORTS):
        try:
            r = read_regs(host, port, 0, 10)
            # DC output is already derated for array effects; apply conversion efficiency.
            max_ac = min(25.0, r[1] * 0.96 / 1000) if (r[3] and r[4]) else 0.0
            caps.append(max_ac)
            devices[ident] = {'connected': True, 'registers': r, 'host': host}
        except (OSError, ValueError, TimeoutError) as ex:
            caps.append(0)
            devices[ident] = {'connected': False, 'error': type(ex).__name__, 'host': host}
    limits = distribute(target, caps)
    for ident, host, port, limit in zip(INVERTERS, HOSTS, PORTS, limits):
        if devices[ident]['connected']:
            kw = max(0, min(25000, int(limit*1000)))  # floor: never exceed setpoint
            if devices[ident]['registers'][2] != kw:
                try: write_reg(host, 100, kw, port=port)
                except (OSError, ValueError, TimeoutError): devices[ident]['control_error'] = True
            devices[ident]['commanded_limit_kw'] = kw
    # Use a fresh authoritative state after device commands land.
    plant = request_json(FIELD + '/api/state')
    new = {'connected': all(d['connected'] for d in devices.values()), 'last_poll': time.time(),
           'target_export_mw': target, 'device_status': devices, 'plant': plant}
    with lock: status = new
    return copy.deepcopy(new)


def poll_loop():
    while True:
        try: control_once()
        except Exception as e:
            with lock: status.update(connected=False, error=type(e).__name__)
        time.sleep(1)


def execute_command(data):
    global target_export_mw
    kind = data.get('action')
    if kind == 'plant_limit':
        value = data.get('mw')
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100:
            raise ValueError('plant limit must be 0..100 MW')
        with lock: target_export_mw = float(value)
    elif kind == 'weather':
        fields = {k: data[k] for k in ('irradiance_wm2','ambient_c','wind_ms') if k in data}
        if not fields: raise ValueError('weather needs at least one parameter')
        request_json(FIELD + '/api/command', {'action': 'weather', **fields, 'source': 'scada-instructor'})
    elif kind == 'grid_conditions':
        fields = {k:data[k] for k in ('voltage_kv','frequency_hz') if k in data}
        if not fields: raise ValueError('missing grid voltage or frequency')
        request_json(FIELD + '/api/command', {'action':'grid_conditions', **fields, 'source':'grid-test-instructor'})
    elif kind == 'grid_breaker':
        if type(data.get('closed')) is not bool: raise ValueError('closed must be boolean')
        request_json(FIELD + '/api/command', {'action': 'grid_breaker', 'closed': data['closed'], 'source': 'scada-operator'})
    elif kind == 'inverter_breaker':
        ident = data.get('inverter')
        if ident not in INVERTERS or type(data.get('closed')) is not bool:
            raise ValueError('unknown inverter or invalid breaker state')
        write_reg(HOSTS[INVERTERS.index(ident)], 101, int(data['closed']), port=PORTS[INVERTERS.index(ident)])
    elif kind == 'reset':
        request_json(FIELD + '/api/command', {'action': 'reset', 'source': 'scada-operator'})
        with lock: target_export_mw = 100.0
    else: raise ValueError('unsupported PPC command')
    return {'accepted': True, 'action': kind, 'target_export_mw': target_export_mw}


class API(Handler):
    def do_GET(self):
        if urlsplit(self.path).path == '/api/state':
            with lock: s = copy.deepcopy(status)
            send_json(self, 200, s)
        elif urlsplit(self.path).path == '/health': send_json(self, 200, {'ok': True})
        else: send_json(self, 404, {'error': 'not_found'})

    def do_POST(self):
        if urlsplit(self.path).path != '/api/command': return send_json(self, 404, {'error':'not_found'})
        try: send_json(self, 200, execute_command(body_json(self)))
        except (ValueError, TypeError) as ex: send_json(self, 400, {'error':str(ex)})
        except (OSError, TimeoutError) as ex: send_json(self, 503, {'error':type(ex).__name__})


if __name__ == '__main__':
    threading.Thread(target=poll_loop, daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0', int(os.getenv('PORT','8080'))), API).serve_forever()
