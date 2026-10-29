"""Corporate Level-4 AD-authenticated public engagement operations console.

This service connects only to L4 and IDMZ. A narrow authenticated conduit in
IDMZ bridges to the public-service backend; no OT routes are reachable.
"""
import json
import os
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
from common import JSONHandler, send_json, read_json
from corp_portal import verify_ad

UPSTREAM = os.getenv('PUBLIC_OPS_URL', 'http://public-case-conduit:8080')
TOKEN = os.getenv('PUBLIC_ADMIN_TOKEN','')
HTML = Path(__file__).with_name('solar_ui').joinpath('public_ops.html').read_bytes()
ROUTES = {
    ('GET','/api/cases'):'/api/internal/enquiries',
    ('GET','/api/notices'):'/api/public/notices',
    ('POST','/api/cases/update'):'/api/internal/enquiries/update',
    ('POST','/api/notices/new'):'/api/internal/announcements',
    ('POST','/api/notices/close'):'/api/internal/announcements/close',
}

class Handler(JSONHandler):
    def do_GET(self):self.handle_http('GET')
    def do_POST(self):self.handle_http('POST')
    def handle_http(self,method):
        p=urlsplit(self.path).path
        if method=='GET' and p in ('/','/index.html'):
            self.send_response(200)
            self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(HTML)))
            self.send_header('X-Frame-Options','DENY')
            self.end_headers();return self.wfile.write(HTML)
        path=ROUTES.get((method,p))
        if not path:return send_json(self,404,{'error':'not_found'})
        user=verify_ad(self.headers.get('Authorization',''))
        if not user:
            self.send_response(401);self.send_header('WWW-Authenticate','Basic realm="SOLARIS corporate AD"')
            self.send_header('Content-Length','0');self.end_headers();return
        try:
            body=json.dumps(read_json(self,2048)).encode() if method=='POST' else None
            req=Request(UPSTREAM+path,data=body,method=method,
                headers={'Content-Type':'application/json','X-Public-Admin-Token':TOKEN})
            try:
                with urlopen(req,timeout=6) as r:
                    status=r.status;response=r.read(300000)
            except HTTPError as exc:
                status=exc.code;response=exc.read(300000)
            if len(response)>=300000:return send_json(self,502,{'error':'response_too_large'})
            self.send_response(status);self.send_header('Content-Type','application/json')
            self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(response)))
            self.end_headers();self.wfile.write(response)
        except ValueError:return send_json(self,400,{'error':'invalid_body'})
        except (OSError,URLError,TimeoutError):return send_json(self,503,{'error':'public_support_service_unavailable'})

if __name__=='__main__':
    if not TOKEN:raise SystemExit('PUBLIC_ADMIN_TOKEN required')
    ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','8080'))),Handler).serve_forever()
