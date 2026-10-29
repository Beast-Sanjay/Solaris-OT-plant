"""Application-level conduit. Exact HTTP path/method allowlist, no IP forwarding."""
import os
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from common import JSONHandler, send_json

TARGET = os.environ['TARGET_URL'].rstrip('/')
PATHS = set(p.strip() for p in os.environ['ALLOWED_PATHS'].split(',') if p.strip())
METHODS = set(m.strip().upper() for m in os.environ.get('ALLOWED_METHODS', 'GET').split(','))


class Handler(JSONHandler):
    def do_GET(self): self.handle_request('GET')
    def do_POST(self): self.handle_request('POST')
    def do_PUT(self): self.handle_request('PUT')
    def do_DELETE(self): self.handle_request('DELETE')

    def handle_request(self, method):
        parts = urlsplit(self.path)
        if parts.path not in PATHS or method not in METHODS or parts.fragment:
            return send_json(self, 403, {'error': 'conduit_policy_denied'})
        length = int(self.headers.get('Content-Length', '0'))
        if length > 8192 or length < 0:
            return send_json(self, 413, {'error': 'payload_too_large'})
        payload = self.rfile.read(length) if method == 'POST' and length else None
        # Deliberately do not proxy authorization, cookies or arbitrary inbound headers.
        request = Request(TARGET + parts.path + (('?' + parts.query) if parts.query else ''),
                          data=payload, method=method,
                          headers={'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=5) as resp:
                data = resp.read(65537)
                status = resp.status
                content_type = resp.headers.get('Content-Type', 'application/json')
        except HTTPError as exc:
            data = exc.read(65537)
            status = exc.code
            content_type = 'application/json'
        except (URLError, TimeoutError, OSError):
            return send_json(self, 503, {'error': 'upstream_unavailable'})
        if len(data) > 65536:
            return send_json(self, 502, {'error': 'upstream_response_too_large'})
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', int(os.getenv('LISTEN_PORT', '8080'))), Handler).serve_forever()
