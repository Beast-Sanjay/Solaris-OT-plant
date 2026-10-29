"""Single authoritative solar plant state. ALL sensor values originate here.

Simplified PVWatts-inspired DC equation, static efficiency and thermal proxy.
Not a grid dynamic solver, protection study or validated equipment digital twin.
"""
import copy
import os
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
from common import Handler, body_json, send_json

IDS = ('INV-01', 'INV-02', 'INV-03', 'INV-04')
AC_MW = 25.0
DC_MW = 27.5
TRANSFORMER_LOSS = 0.015


def limited(value, lo, hi, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not lo <= float(value) <= hi:
        raise ValueError(f'{name} must be between {lo} and {hi}')
    return float(value)


class Plant:
    def __init__(self):
        self.lock = threading.RLock()
        self.weather = {'irradiance_wm2': 1000.0, 'ambient_c': 25.0, 'wind_ms': 2.0}
        self.grid_breaker_closed = True
        self.grid_voltage_kv = 33.0
        self.grid_frequency_hz = 50.0
        self.inverters = {i: {'limit_kw': 25000, 'breaker_closed': True, 'online': True, 'energy_mwh': 0.0} for i in IDS}
        self.grid_export_mwh = 0.0
        self.last_monotonic = time.monotonic()
        self.last_command = {'kind': 'initial', 'time': time.time()}
        self.snapshot = {}
        with self.lock: self.tick()

    def tick(self):
        with self.lock:
            elapsed = min(10, max(0, time.monotonic() - self.last_monotonic))
            self.last_monotonic = time.monotonic()
            g = self.weather['irradiance_wm2']
            temp = self.weather['ambient_c'] + 0.03 * g  # simple NOCT-like approximation
            # PVWatts DC: Pdc = Pdc0*(G/1000)*(1 + gamma*(Tcell-25)).
            dc = max(0, DC_MW * (g / 1000) * max(0, 1 - 0.0035 * (temp - 25)) * 0.97)
            inv_available = min(AC_MW, dc * 0.96)
            outputs = {}
            dc_total = 0.0
            ac_total = 0.0
            for ident, inv in self.inverters.items():
                available = inv_available if inv['online'] else 0.0
                ac = min(available, inv['limit_kw'] / 1000.0) if (inv['breaker_closed'] and self.grid_breaker_closed) else 0.0
                inv['energy_mwh'] += ac * elapsed / 3600.0
                dc_total += dc if inv['online'] else 0.0
                ac_total += ac
                outputs[ident] = {
                    'id': ident, 'dc_available_mw': round(dc if inv['online'] else 0.0, 4),
                    'ac_available_mw': round(available, 4), 'ac_power_mw': round(ac, 4),
                    'limit_mw': round(inv['limit_kw']/1000, 4),
                    'breaker_closed': inv['breaker_closed'], 'online': inv['online'],
                    'energy_mwh': round(inv['energy_mwh'], 5),
                    'cell_temperature_c': round(temp, 2)
                }
            export = ac_total * (1 - TRANSFORMER_LOSS)
            self.grid_export_mwh += export * elapsed / 3600
            self.snapshot = {
                'plant': 'SOLAR-TWIN-100MW', 'mode': 'simulation', 'timestamp': time.time(),
                'weather': copy.deepcopy(self.weather),
                'transformer': {'loss_fraction': TRANSFORMER_LOSS, 'input_mw': round(ac_total, 4),
                                'loss_mw': round(ac_total - export, 4)},
                'pcc': {'breaker_closed': self.grid_breaker_closed, 'export_mw': round(export, 4),
                        'voltage_kv': self.grid_voltage_kv if self.grid_breaker_closed else 0.0,
                        'frequency_hz': self.grid_frequency_hz if self.grid_breaker_closed else 0.0,
                        'source_voltage_kv': self.grid_voltage_kv, 'source_frequency_hz': self.grid_frequency_hz,
                        'export_energy_mwh': round(self.grid_export_mwh, 5)},
                'dc_total_mw': round(dc_total, 4),
                'ac_total_mw': round(ac_total, 4),
                'available_export_mw': round(sum(v['ac_available_mw'] for v in outputs.values()) * (1 - TRANSFORMER_LOSS), 4),
                'inverters': outputs, 'last_command': copy.deepcopy(self.last_command),
                'model_note': 'PVWatts-inspired steady-state educational approximation; not validated plant data'
            }
            return copy.deepcopy(self.snapshot)

    def command(self, data):
        action = data.get('action')
        with self.lock:
            if action == 'weather':
                for key, lo, hi in [('irradiance_wm2', 0, 1200), ('ambient_c', -10, 65), ('wind_ms', 0, 35)]:
                    if key in data:
                        self.weather[key] = limited(data[key], lo, hi, key)
            elif action == 'grid_conditions':
                if 'voltage_kv' in data: self.grid_voltage_kv = limited(data['voltage_kv'], 0, 40, 'voltage_kv')
                if 'frequency_hz' in data: self.grid_frequency_hz = limited(data['frequency_hz'], 45, 55, 'frequency_hz')
            elif action == 'grid_breaker':
                if type(data.get('closed')) is not bool: raise ValueError('closed must be bool')
                self.grid_breaker_closed = data['closed']
            elif action in ('inverter_limit', 'inverter_breaker', 'inverter_online'):
                ident = data.get('inverter')
                if ident not in self.inverters: raise ValueError('unknown inverter')
                if action == 'inverter_limit':
                    self.inverters[ident]['limit_kw'] = int(round(limited(data.get('limit_kw'), 0, 25000, 'limit_kw')))
                elif action == 'inverter_breaker':
                    if type(data.get('closed')) is not bool: raise ValueError('closed must be bool')
                    self.inverters[ident]['breaker_closed'] = data['closed']
                else:
                    if type(data.get('online')) is not bool: raise ValueError('online must be bool')
                    self.inverters[ident]['online'] = data['online']
            elif action == 'reset':
                self.weather = {'irradiance_wm2':1000.0, 'ambient_c':25.0, 'wind_ms':2.0}
                self.grid_breaker_closed = True
                self.grid_voltage_kv = 33.0
                self.grid_frequency_hz = 50.0
                for inv in self.inverters.values():
                    inv.update(limit_kw=25000, breaker_closed=True, online=True)
            else: raise ValueError('unknown action')
            self.last_command = {'kind': action, 'time': time.time(), 'source': str(data.get('source', 'l1'))[:40]}
            return self.tick()


plant = Plant()


class API(Handler):
    def do_GET(self):
        if urlsplit(self.path).path == '/api/state': send_json(self, 200, plant.tick())
        elif urlsplit(self.path).path == '/health': send_json(self, 200, {'ok': True})
        else: send_json(self, 404, {'error': 'not_found'})

    def do_POST(self):
        if urlsplit(self.path).path != '/api/command': return send_json(self, 404, {'error': 'not_found'})
        try: send_json(self, 200, plant.command(body_json(self)))
        except (ValueError, TypeError) as e: send_json(self, 400, {'error': str(e)})


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', int(os.getenv('PORT','8080'))), API).serve_forever()
