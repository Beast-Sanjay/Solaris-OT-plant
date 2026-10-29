"""Enterprise AD-validated, read-only OT historian access across IDMZ.

Lab-only HTTP Basic authentication over loopback publication and internal Docker
bridges. LDAPS uses a self-signed certificate without trust verification. Not suitable for production without TLS, rate-limits and policy engine.
"""
import base64
import json
import os
import ssl
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
from urllib.request import urlopen
from ldap3 import Connection, Server, SIMPLE, Tls
from common import JSONHandler, send_json

DOMAIN = os.getenv('AD_DOMAIN', 'corp.otlab.test')


def verify(username, password):
    if not username or not password or len(username) > 80 or len(password) > 512: return False
    if not all(c.isalnum() or c in '._-' for c in username): return False
    conn = None
    try:
        conn = Connection(Server(os.getenv('AD_HOST', 'dc01'), port=636, use_ssl=True,
                                 tls=Tls(validate=ssl.CERT_NONE), connect_timeout=3),
                          user=username + '@' + DOMAIN, password=password,
                          authentication=SIMPLE, auto_bind=True, receive_timeout=4)
        return conn.bound
    except Exception:
        return False
    finally:
        if conn is not None:
            try: conn.unbind()
            except Exception: pass


class Handler(JSONHandler):
    def do_GET(self):
        route = urlsplit(self.path)
        if route.path not in ('/api/latest', '/api/history', '/api/devices/latest', '/api/devices/history', '/api/plant/latest', '/api/plant/history'):
            return send_json(self, 404, {'error': 'not_found'})
        auth = self.headers.get('Authorization', '')
        try:
            if not auth.startswith('Basic '): raise ValueError('missing basic auth')
            decoded = base64.b64decode(auth[6:], validate=True).decode('utf-8')
            username, password = decoded.split(':', 1)
        except (ValueError, UnicodeError):
            username, password = '', ''
        if not verify(username, password):
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="Corp OT Lab"')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        url = os.environ['HISTORIAN_URL'] + route.path + (('?' + route.query) if route.query else '')
        try:
            with urlopen(url, timeout=5) as reply:
                obj = json.load(reply)
            send_json(self, 200, {'authenticated_user': username, 'historian': obj, 'path': 'L4 -> IDMZ -> L3'})
        except (OSError, ValueError, TimeoutError):
            send_json(self, 503, {'error': 'historian_unavailable'})


if __name__ == '__main__':
    print('[it-access] AD authentication backed by dc01; NOT production-grade TLS', flush=True)
    ThreadingHTTPServer(('0.0.0.0', int(os.getenv('PORT','8080'))), Handler).serve_forever()
