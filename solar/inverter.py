"""Real Modbus/TCP simulated inverter; all registers derived from L0 plant state.
FC03/04 reads; FC06 writes inverter limit or breaker state via L0 actuator conduit.
This is a documented demo register map, NOT an official SunSpec model.
"""
import os
import socketserver
import struct
from common import request_json, recv_exact

IDENT = os.getenv('INVERTER_ID', 'INV-01')
FIELD = os.getenv('FIELD_URL', 'http://solar-field-conduit:8080')


def registers(plant):
    v = plant['inverters'][IDENT]
    w = plant['weather']; pcc = plant['pcc']
    return [int(round(v['ac_power_mw']*1000)), int(round(v['dc_available_mw']*1000)),
            int(round(v['limit_mw']*1000)), int(v['online']), int(v['breaker_closed']),
            int(round(w['irradiance_wm2'])), int(round(v['cell_temperature_c']*10)),
            int(round(pcc['frequency_hz']*100)), int(round(pcc['voltage_kv']*100)),
            min(65535, int(round(v['energy_mwh']*100)))]


def handle_pdu(pdu):
    if not pdu: return b'\x80\x03'
    fc = pdu[0]
    if fc in (3, 4) and len(pdu) == 5:
        start, count = struct.unpack('!HH', pdu[1:])
        regs = registers(request_json(FIELD+'/api/state', timeout=3))
        if not 1 <= count <= 125 or start+count > len(regs): return bytes([fc|0x80, 2])
        return bytes([fc, count*2]) + struct.pack(f'!{count}H', *regs[start:start+count])
    if fc == 6 and len(pdu) == 5:
        addr, value = struct.unpack('!HH', pdu[1:])
        if addr == 100 and 0 <= value <= 25000:
            request_json(FIELD+'/api/command', {'action': 'inverter_limit', 'inverter': IDENT, 'limit_kw': value, 'source': 'modbus-inverter'})
        elif addr == 101 and value in (0, 1):
            request_json(FIELD+'/api/command', {'action': 'inverter_breaker', 'inverter': IDENT, 'closed': bool(value), 'source': 'modbus-inverter'})
        else: return bytes([fc|0x80, 3])
        return pdu
    return bytes([fc|0x80, 1])


class TCP(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(7)
        while True:
            try:
                header = recv_exact(self.request, 7)
                tid, proto, length, unit = struct.unpack('!HHHB', header)
                if proto or length < 2 or length > 253: break
                pdu = recv_exact(self.request, length-1)
                try: response = handle_pdu(pdu)
                except Exception: response = bytes([pdu[0]|0x80, 4])
                self.request.sendall(struct.pack('!HHHB', tid, 0, len(response)+1, unit)+response)
            except (OSError, TimeoutError):
                break


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == '__main__':
    print(f'[inverter] {IDENT} listening Modbus/TCP', flush=True)
    with Server(('0.0.0.0', int(os.getenv('MODBUS_PORT','502'))), TCP) as s: s.serve_forever()
