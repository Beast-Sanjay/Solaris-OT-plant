"""Level 2 supervisory UI and Modbus poller (FC03 only)."""
import os
import socket
import struct
import threading
import time
from http.server import ThreadingHTTPServer
from common import JSONHandler, send_json

state = {'connected': False, 'last_update': None, 'error': 'initializing', 'values': {}}
lock = threading.Lock()
html = '''<!doctype html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Purdue SCADA</title><style>body{background:#101525;color:#f2f3fc;font:17px system-ui;max-width:820px;margin:6vh auto;padding:20px}h1{color:#aa7eff}pre{padding:25px;background:#1c2541;border-radius:16px;line-height:1.8}small{color:#9faed2}</style><h1>Level 2 — Supervisory SCADA</h1><small>Synthetic process telemetry from Level 1 over a specific Modbus conduit</small><pre id="data">Connecting…</pre><script>async function refresh(){try{let r=await fetch('/api/state');document.getElementById('data').textContent=JSON.stringify(await r.json(),null,2)}catch(e){document.getElementById('data').textContent=String(e)}}refresh();setInterval(refresh,2000)</script></html>'''.encode()


def read_exact(sock, n):
    b = bytearray()
    while len(b) < n:
        packet = sock.recv(n - len(b))
        if not packet: raise OSError('closed')
        b.extend(packet)
    return bytes(b)


def read_regs(host, port):
    with socket.create_connection((host, port), timeout=2) as s:
        s.settimeout(2)
        s.sendall(struct.pack('!HHHBBHH', 17, 0, 6, 1, 3, 0, 6))
        header = read_exact(s, 7)
        tid, proto, length, unit = struct.unpack('!HHHB', header)
        if tid != 17 or proto != 0 or length > 253: raise OSError('invalid Modbus header')
        pdu = read_exact(s, length - 1)
        if pdu[:2] != b'\x03\x0c' or len(pdu) != 14: raise OSError('bad Modbus reply')
        return struct.unpack('!6H', pdu[2:])


def poller():
    while True:
        try:
            level, pump, flow, temp, setpoint, connected = read_regs(os.getenv('MODBUS_HOST', 'control-conduit'), int(os.getenv('MODBUS_PORT', '15020')))
            obj = {'level_pct': level / 10, 'pump_on': bool(pump), 'flow_lpm': flow / 10,
                   'temperature_c': temp / 10, 'setpoint_pct': setpoint, 'field_connected': bool(connected)}
            with lock: state.update(connected=True, last_update=time.time(), error=None, values=obj)
        except (OSError, ValueError) as exc:
            with lock: state.update(connected=False, error=type(exc).__name__)
        time.sleep(2)


class Handler(JSONHandler):
    def do_GET(self):
        if self.path in ('/', '/index.html'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(html)))
            self.end_headers()
            self.wfile.write(html)
        elif self.path == '/api/state':
            with lock: obj = dict(state)
            send_json(self, 200, {'source': 'level2-scada', **obj})
        else:
            send_json(self, 404, {'error': 'not_found'})


if __name__ == '__main__':
    threading.Thread(target=poller, daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0', int(os.getenv('PORT', '8080'))), Handler).serve_forever()
