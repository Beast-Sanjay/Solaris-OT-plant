"""Purdue application conduit. Allowlisted routes, never generic network forwarding.

Control commands require a matching X-PPC-Token at the conduit and propagate
ONLY that verified header to the target. Read-only conduits never forward tokens.
This is a lab shared-secret gate, not production zero-trust/mTLS.
"""
import hmac
import os
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from common import JSONHandler, send_json

TARGET = os.environ['TARGET_URL'].rstrip('/')
PATHS = {p.strip() for p in os.environ['ALLOWED_PATHS'].split(',') if p.strip()}
METHODS = {m.strip().upper() for m in os.environ.get('ALLOWED_METHODS', 'GET').split(',')}
CONTROL_TOKEN = os.getenv('CONDUIT_AUTH_TOKEN', '')
AUTH_HEADER = os.getenv('CONDUIT_AUTH_HEADER', 'X-PPC-Token')
ALLOW_UNAUTH_POST = os.getenv('CONDUIT_ALLOW_UNAUTH_POST') == 'true'
REQUIRE_AUTH_GET = os.getenv('CONDUIT_REQUIRE_AUTH_GET') == 'true'
MAX_RESPONSE = min(300000, max(8192, int(os.getenv('CONDUIT_MAX_RESPONSE_BYTES', '65536'))))


def allowed(method, path):
    return method in METHODS and path in PATHS


def authorized(method, supplied):
    if method == 'GET' and not REQUIRE_AUTH_GET:
        return True
    if ALLOW_UNAUTH_POST and not CONTROL_TOKEN and method == 'POST':
        return True  # explicit single-purpose telemetry collection exception
    return bool(CONTROL_TOKEN) and bool(supplied) and hmac.compare_digest(CONTROL_TOKEN, supplied)


class Handler(JSONHandler):
    def do_GET(self): self.handle_request('GET')
    def do_POST(self): self.handle_request('POST')
    def do_PUT(self): self.handle_request('PUT')
    def do_DELETE(self): self.handle_request('DELETE')

    def handle_request(self, method):
        parts = urlsplit(self.path)
        if not allowed(method, parts.path) or parts.fragment or parts.username or parts.password:
            return send_json(self, 403, {'error': 'conduit_policy_denied'})
        if not authorized(method, self.headers.get(AUTH_HEADER, '')):
            return send_json(self, 403, {'error': 'conduit_authorization_required'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            return send_json(self, 400, {'error': 'invalid_content_length'})
        if length > 8192 or length < 0:
            return send_json(self, 413, {'error': 'payload_too_large'})
        payload = self.rfile.read(length) if method == 'POST' and length else None
        headers = {'Content-Type': 'application/json'}
        if CONTROL_TOKEN and (method != 'GET' or REQUIRE_AUTH_GET):
            headers[AUTH_HEADER] = CONTROL_TOKEN  # verified, single-purpose credential
        request = Request(TARGET + parts.path + (('?' + parts.query) if parts.query else ''),
                          data=payload, method=method, headers=headers)
        try:
            with urlopen(request, timeout=5) as resp:
                data = resp.read(MAX_RESPONSE + 1)
                status = resp.status
                content_type = resp.headers.get('Content-Type', 'application/json')
        except HTTPError as exc:
            data = exc.read(MAX_RESPONSE + 1)
            status = exc.code
            content_type = 'application/json'
        except (URLError, TimeoutError, OSError):
            return send_json(self, 503, {'error': 'upstream_unavailable'})
        if len(data) > MAX_RESPONSE:
            return send_json(self, 502, {'error': 'upstream_response_too_large'})
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', int(os.getenv('LISTEN_PORT', '8080'))), Handler).serve_forever()
