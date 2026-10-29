"""Shared stdlib-only HTTP and Modbus helpers for the synthetic solar twin."""
import json
import socket
import struct
from http.server import BaseHTTPRequestHandler
from urllib.request import Request, urlopen


def request_json(url, payload=None, timeout=4):
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(url, data=data, headers={'Content-Type': 'application/json'},
                  method='POST' if data is not None else 'GET')
    with urlopen(req, timeout=timeout) as res:
        return json.load(res)


def send_json(h, code, obj):
    b = json.dumps(obj, separators=(',', ':'), allow_nan=False).encode()
    h.send_response(code)
    h.send_header('Content-Type', 'application/json; charset=utf-8')
    h.send_header('Cache-Control', 'no-store')
    h.send_header('Content-Length', str(len(b)))
    h.end_headers()
    h.wfile.write(b)


def body_json(h):
    n = int(h.headers.get('Content-Length', '0'))
    if n <= 0 or n > 4096:
        raise ValueError('invalid payload size')
    d = json.loads(h.rfile.read(n))
    if not isinstance(d, dict):
        raise ValueError('expected JSON object')
    return d


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        return


def recv_exact(s, n):
    buf = bytearray()
    while len(buf) < n:
        packet = s.recv(n-len(buf))
        if not packet:
            raise OSError('connection closed')
        buf.extend(packet)
    return bytes(buf)


def modbus_request(host, port, pdu, unit=1, timeout=3):
    with socket.create_connection((host, int(port)), timeout=timeout) as s:
        s.settimeout(timeout)
        s.sendall(struct.pack('!HHHB', 21, 0, len(pdu)+1, unit) + pdu)
        hdr = recv_exact(s, 7)
        tid, proto, length, uid = struct.unpack('!HHHB', hdr)
        if (tid, proto, uid) != (21, 0, unit) or not 2 <= length <= 253:
            raise ValueError('invalid MBAP header')
        response = recv_exact(s, length-1)
        if response[0] & 0x80:
            raise ValueError(f'Modbus exception {response[1]}')
        if response[0] != pdu[0]:
            raise ValueError('wrong Modbus function')
        return response


def read_regs(host, port=502, start=0, count=10):
    pdu = modbus_request(host, port, struct.pack('!BHH', 3, start, count))
    if pdu[1] != count*2 or len(pdu) != 2+count*2:
        raise ValueError('register read size')
    return list(struct.unpack(f'!{count}H', pdu[2:]))


def write_reg(host, addr, val, port=502):
    req = struct.pack('!BHH', 6, addr, int(val))
    if modbus_request(host, port, req) != req:
        raise ValueError('write not acknowledged')
