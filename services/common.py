"""Minimal stdlib HTTP helpers. No exposure beyond dedicated Docker bridges."""
import json
from http.server import BaseHTTPRequestHandler


def send_json(handler, status, obj):
    data = json.dumps(obj, separators=(',', ':')).encode()
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Content-Length', str(len(data)))
    handler.send_header('Cache-Control', 'no-store')
    handler.end_headers()
    handler.wfile.write(data)


def read_json(handler, max_bytes=4096):
    length = int(handler.headers.get('Content-Length', '0'))
    if length < 1 or length > max_bytes:
        raise ValueError('invalid body size')
    return json.loads(handler.rfile.read(length))


class JSONHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Log path and status but never Authorization headers or bodies.
        super().log_message(format, *args)
