"""Level 2 solar SCADA user interface: all L1 traffic through the L2/L1 conduit."""
import os
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from common import Handler, body_json, request_json, send_json

PPC = os.getenv('PPC_URL','http://solar-ppc-conduit:8080')
UI = open(os.path.join(os.path.dirname(__file__), 'index.html'), encoding='utf-8').read().encode()


class API(Handler):
    def do_GET(self):
        p = urlsplit(self.path).path
        if p in ('/', '/index.html'):
            self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(UI))); self.end_headers(); self.wfile.write(UI)
        elif p == '/api/state':
            try: send_json(self, 200, request_json(PPC+'/api/state'))
            except (OSError, URLError, TimeoutError): send_json(self, 503, {'error':'PPC_unavailable'})
        else: send_json(self, 404, {'error':'not_found'})

    def do_POST(self):
        if urlsplit(self.path).path != '/api/command': return send_json(self, 404, {'error':'not_found'})
        try: send_json(self, 200, request_json(PPC+'/api/command', body_json(self)))
        except HTTPError as ex:
            try: send_json(self, ex.code, __import__('json').load(ex))
            except ValueError: send_json(self, ex.code, {'error':'invalid_command'})
        except (OSError, URLError, TimeoutError): send_json(self, 503, {'error':'PPC_unavailable'})
        except ValueError as ex: send_json(self, 400, {'error':str(ex)})


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', int(os.getenv('PORT','8080'))), API).serve_forever()
