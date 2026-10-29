"""L0 local field-service tablet. Repairs change measured PV output via private L0 APIs.
No direct access from IT, OT SCADA, DMZ, or public website. Localhost test console only.
"""
import hmac
import json
import os
import sqlite3
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from common import JSONHandler, read_json, send_json

TOKEN = os.getenv('CONTROL_TOKEN', '')
DB = os.getenv('FIELD_DB', '/data/service_log.sqlite3')
ASSETS = {f'PV-{i:02d}': f'http://pv-array-{i:02d}:8080' for i in range(1, 5)}
if os.getenv('FIELD_ASSETS'):
    # Only for the standalone loopback smoke test; production has fixed endpoints.
    ASSETS = dict(x.split('=', 1) for x in os.environ['FIELD_ASSETS'].split(','))
PAGE = Path(__file__).with_name('solar_ui').joinpath('field.html').read_bytes()


def db_conn():
    db = sqlite3.connect(DB, timeout=10)
    db.execute('''CREATE TABLE IF NOT EXISTS repairs (id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL NOT NULL, asset TEXT NOT NULL, action TEXT NOT NULL, value TEXT,
        result TEXT NOT NULL, operator TEXT NOT NULL)''')
    return db


def live():
    devices = {}
    for name, base in ASSETS.items():
        try:
            with urlopen(base + '/api/state', timeout=2) as resp: devices[name] = json.load(resp)
        except (OSError, ValueError, TimeoutError):devices[name] = {'device': name, 'connected': False}
    return devices


def perform(asset, action, value, operator):
    if asset not in ASSETS or action not in ('clean','repair_strings','inject_soiling','disconnect_strings'):
        raise ValueError('invalid asset or action')
    if not isinstance(operator,str) or not 1 <= len(operator) <= 40 or not all(c.isalnum() or c in ' -_' for c in operator):
        raise ValueError('invalid operator')
    payload = json.dumps({'action': action, 'value': value}).encode()
    req = Request(ASSETS[asset]+'/api/service', data=payload, method='POST',
                  headers={'Content-Type':'application/json', 'X-Field-Token': TOKEN})
    with urlopen(req, timeout=4) as resp: result=json.load(resp)
    with db_conn() as db:
        db.execute('INSERT INTO repairs(ts,asset,action,value,result,operator) VALUES(?,?,?,?,?,?)',
                   (time.time(),asset,action,json.dumps(value),json.dumps(result),operator))
    return result


class Handler(JSONHandler):
    def do_GET(self):
        if self.path in ('/','/index.html'):
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(PAGE)));self.end_headers();self.wfile.write(PAGE)
        elif self.path=='/api/assets':send_json(self,200,{'assets':live(),'simulation':True})
        elif self.path=='/api/repairs':
            with db_conn() as db: rows=db.execute('SELECT ts,asset,action,operator FROM repairs ORDER BY id DESC LIMIT 40').fetchall()
            send_json(self,200,{'repairs':[dict(zip(('time','asset','action','operator'),row)) for row in rows]})
        elif self.path=='/health':send_json(self,200,{'ok':True,'role':'L0-field-service'})
        else:send_json(self,404,{'error':'not_found'})
    def do_POST(self):
        if self.path!='/api/service':return send_json(self,404,{'error':'not_found'})
        supplied=self.headers.get('X-Lab-Control-Token','')
        if not TOKEN or not supplied or not hmac.compare_digest(TOKEN,supplied):
            return send_json(self,403,{'error':'field_service_token_required'})
        try:
            obj=read_json(self)
            result=perform(obj['asset'],obj['action'],obj.get('value'),obj.get('operator',''))
            return send_json(self,200,result)
        except (ValueError,KeyError,TypeError):return send_json(self,400,{'error':'invalid_service_request'})
        except (OSError,TimeoutError):return send_json(self,503,{'error':'field_asset_unavailable'})


if __name__=='__main__':
    with db_conn():pass
    ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','8080'))),Handler).serve_forever()
