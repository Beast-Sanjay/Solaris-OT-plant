"""L2 SCADA for two independent simulated Modbus TCP controllers.

Read-only visualization: control writes are made locally at L1 for demonstration,
never through the enterprise historian gateway.
"""
import json
import os
import socket
import struct
import threading
import time
from http.server import ThreadingHTTPServer
from common import JSONHandler, send_json

state = {'connected': False, 'last_update': None, 'error': 'initializing', 'values': {}, 'devices': {}}
lock = threading.Lock()
HTML = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Industrial SCADA | Purdue L2</title>
<style>body{background:#101525;color:#edf1fa;font-family:system-ui;margin:0;padding:28px}header{max-width:1080px;margin:auto}h1{color:#b58afe}small{color:#abb6d2}#grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:18px;max-width:1080px;margin:26px auto}article{border:1px solid #39445a;border-radius:14px;background:#1c253b;padding:20px}.good{color:#78e0a2}.bad{color:#ffa2a2}.bar{background:#374258;height:14px;border-radius:10px;overflow:hidden}.fill{background:#a177e5;height:100%}strong{font-size:1.25rem}</style>
<header><small>INDUSTRIAL CYBER RANGE · PURDUE LEVEL 2</small><h1>Live Supervisory SCADA</h1><p>Independent simulated tanks, Modbus TCP controller telemetry, and communication health. Values are live from Level 1.</p></header><main id="grid"></main>
<script>const escapeText=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));async function poll(){try{const r=await fetch('/api/state');const s=await r.json();document.getElementById('grid').innerHTML=Object.entries(s.devices||{}).map(([name,d])=>{const v=d.values||{};const pct=Number(v.level_pct||0);return `<article><small>${escapeText(name)}</small><h2 class="${d.connected?'good':'bad'}">${d.connected?'● Connected':'● Offline'}</h2><strong>${pct.toFixed(1)}% tank level</strong><div class="bar"><div class="fill" style="width:${Math.min(100,Math.max(0,pct))}%"></div></div><p>Pump: ${v.pump_on?'ON':'OFF'}</p><p>Flow: ${Number(v.flow_lpm||0).toFixed(1)} L/min</p><p>Temperature: ${Number(v.temperature_c||0).toFixed(1)} °C</p><p>Setpoint: ${v.setpoint_pct??'-'}%</p><small>Field device: ${v.field_connected?'online':'offline'} · ${d.error||'no errors'}</small></article>`}).join('')||'<article>No controller telemetry yet.</article>'}catch(e){document.getElementById('grid').textContent='SCADA service unavailable: '+e}}poll();setInterval(poll,2000)</script></html>'''.encode()


def endpoints():
    result = {}
    raw = os.getenv('DEVICE_ENDPOINTS', '')
    if not raw:
        raw = 'plc-demo=' + os.getenv('MODBUS_HOST', 'control-conduit') + ':' + os.getenv('MODBUS_PORT', '15020')
    for item in raw.split(','):
        name, endpoint = item.strip().split('=', 1)
        host, port = endpoint.rsplit(':', 1)
        if not name or name in result: raise ValueError('duplicate/empty SCADA device')
        result[name] = (host, int(port))
    return result


def read_exact(sock, n):
    b = bytearray()
    while len(b) < n:
        part = sock.recv(n-len(b))
        if not part: raise OSError('closed')
        b.extend(part)
    return bytes(b)


def read_regs(host, port):
    with socket.create_connection((host, port), timeout=2) as s:
        s.settimeout(2)
        s.sendall(struct.pack('!HHHBBHH', 17, 0, 6, 1, 3, 0, 6))
        header = read_exact(s, 7)
        tid, proto, length, unit = struct.unpack('!HHHB', header)
        if tid != 17 or proto != 0 or not 2 <= length <= 253: raise OSError('invalid Modbus header')
        pdu = read_exact(s, length-1)
        if pdu[:2] != b'\x03\x0c' or len(pdu) != 14: raise OSError('invalid Modbus response')
        return struct.unpack('!6H', pdu[2:])


def poller():
    devices = endpoints()
    while True:
        snapshots = {}
        for name, (host, port) in devices.items():
            try:
                level,pump,flow,temp,setpoint,connected = read_regs(host,port)
                values = {'level_pct': level/10, 'pump_on': bool(pump), 'flow_lpm': flow/10,
                          'temperature_c': temp/10, 'setpoint_pct': setpoint, 'field_connected': bool(connected)}
                snapshots[name] = {'connected': True, 'last_update': time.time(), 'error': None, 'values': values}
            except (OSError, ValueError) as ex:
                snapshots[name] = {'connected': False, 'last_update': None, 'error': type(ex).__name__, 'values': {}}
        primary = snapshots.get('plc-demo', next(iter(snapshots.values())))
        with lock:
            state.update(devices=snapshots, connected=primary['connected'],
                         last_update=primary['last_update'], error=primary['error'], values=primary['values'])
        time.sleep(2)


class Handler(JSONHandler):
    def do_GET(self):
        if self.path in ('/', '/index.html'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(HTML)))
            self.end_headers()
            self.wfile.write(HTML)
        elif self.path == '/api/state':
            with lock: obj = dict(state)
            send_json(self, 200, {'source': 'level2-scada', **obj})
        elif self.path == '/health':
            with lock: current = dict(state)
            healthy = bool(current['devices']) and all(d['connected'] for d in current['devices'].values())
            send_json(self, 200 if healthy else 503, {'ok': healthy, 'device_count': len(current['devices'])})
        else:
            send_json(self, 404, {'error': 'not_found'})


if __name__ == '__main__':
    threading.Thread(target=poller, daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0', int(os.getenv('PORT', '8080'))), Handler).serve_forever()
