"""Level 1 Modbus TCP controller. Read/write demo only; never attach hardware."""
import json
import os
import socketserver
import struct
import threading
import time
from urllib.request import Request, urlopen

lock = threading.Lock()
state = {'level': 44.0, 'flow': 0.0, 'temp': 27.0, 'pump': False, 'setpoint': int(os.getenv('INITIAL_SETPOINT', '55')), 'connected': False}
URL = os.getenv('FIELD_URL', 'http://field-conduit:8080')


def controller():
    last_pump = None
    while True:
        try:
            with urlopen(URL + '/api/state', timeout=2) as reply:
                sample = json.load(reply)
            with lock:
                state['level'], state['flow'], state['temp'] = float(sample['level']), float(sample['flow']), float(sample['temperature'])
                state['connected'] = True
                target = float(state['setpoint'])
                # Basic hysteresis; no arbitrary remote actuator exposure.
                if state['level'] <= target - 4: state['pump'] = True
                elif state['level'] >= target + 4: state['pump'] = False
                pump = state['pump']
            if pump != last_pump:
                data = json.dumps({'pump': pump}).encode()
                req = Request(URL + '/api/actuator', data=data, method='POST', headers={'Content-Type': 'application/json'})
                with urlopen(req, timeout=2): pass
                last_pump = pump
        except (OSError, ValueError, KeyError, TimeoutError):
            with lock: state['connected'] = False
            last_pump = None
        time.sleep(1)


def registers():
    with lock:
        return [int(state['level'] * 10), int(state['pump']), int(state['flow'] * 10),
                int(state['temp'] * 10), int(state['setpoint']), int(state['connected'])]


def modbus_response(pdu):
    if not pdu: return b''
    fc = pdu[0]
    if fc in (3, 4):
        if len(pdu) != 5: return bytes([fc | 0x80, 3])
        start, count = struct.unpack('!HH', pdu[1:5])
        reg = registers()
        if count == 0 or count > 125: return bytes([fc | 0x80, 3])
        if start + count > len(reg): return bytes([fc | 0x80, 2])
        return bytes([fc, count * 2]) + struct.pack('!' + 'H' * count, *reg[start:start + count])
    if fc == 6:
        if len(pdu) != 5: return bytes([fc | 0x80, 3])
        addr, value = struct.unpack('!HH', pdu[1:5])
        if addr != 4: return bytes([fc | 0x80, 2])
        if not 10 <= value <= 90: return bytes([fc | 0x80, 3])
        with lock: state['setpoint'] = value
        return pdu
    return bytes([fc | 0x80, 1])


class ModbusHandler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(10)
        while True:
            try:
                header = self.receive(7)
                if not header: return
                tid, proto, length, unit = struct.unpack('!HHHB', header)
                if proto != 0 or length < 2 or length > 254: return
                pdu = self.receive(length - 1)
                if not pdu: return
                reply = modbus_response(pdu)
                self.request.sendall(struct.pack('!HHHB', tid, 0, len(reply) + 1, unit) + reply)
            except (OSError, ValueError, struct.error):
                return

    def receive(self, n):
        result = bytearray()
        while len(result) < n:
            chunk = self.request.recv(n - len(result))
            if not chunk: return None
            result.extend(chunk)
        return bytes(result)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == '__main__':
    threading.Thread(target=controller, daemon=True).start()
    print(f"{os.getenv('PLC_NAME','plc-demo')} Modbus TCP on {os.getenv('MODBUS_PORT','15020')}; registers 0..5, setpoint register 4", flush=True)
    Server(('0.0.0.0', int(os.getenv('MODBUS_PORT', '15020'))), ModbusHandler).serve_forever()
