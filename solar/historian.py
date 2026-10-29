"""L3 solar historian: persists the entire authoritative plant state to SQLite."""
import json
import os
import sqlite3
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from common import Handler, request_json, send_json

DB_PATH = os.getenv('DB_PATH','/data/solar.sqlite3')
SOURCE = os.getenv('POLL_URL','http://solar-supervisory-conduit:8080/api/state')


def connect():
    con = sqlite3.connect(DB_PATH, timeout=5)
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('CREATE TABLE IF NOT EXISTS samples (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, '
                'export_mw REAL NOT NULL, irradiance_wm2 REAL NOT NULL, target_mw REAL NOT NULL, state TEXT NOT NULL)')
    return con


def latest(limit=1):
    with connect() as c:
        rs = c.execute('SELECT ts,export_mw,irradiance_wm2,target_mw,state FROM samples ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
    return [{'timestamp':r[0], 'export_mw':r[1], 'irradiance_wm2':r[2], 'target_mw':r[3], 'state':json.loads(r[4])} for r in rs]


def publish_event(info):
    try: request_json(os.getenv('SOC_URL','http://soc-conduit:8080/api/events'),info,timeout=1)
    except Exception: pass


def poll_once():
    sample = request_json(SOURCE, timeout=3)
    if not sample.get('connected') or not sample.get('plant'): return False
    plant = sample['plant']
    with connect() as con:
        con.execute('INSERT INTO samples(ts,export_mw,irradiance_wm2,target_mw,state) VALUES(?,?,?,?,?)',
                    (time.time(),plant['pcc']['export_mw'],plant['weather']['irradiance_wm2'],
                     sample['target_export_mw'],json.dumps(sample,separators=(',',':'))))
        con.execute('DELETE FROM samples WHERE id NOT IN (SELECT id FROM samples ORDER BY id DESC LIMIT 10000)')
    return True


def loop():
    old_state = None
    while True:
        try:
            if poll_once():
                now = latest()[0]['state']['plant']
                marker = now['last_command']['time']
                if marker != old_state and old_state is not None:
                    publish_event({'event':'solar_plant_command', 'severity':'info', 'source':'solar-historian',
                                   'time':time.time(), 'action':now['last_command']['kind']})
                old_state = marker
        except Exception as e: print('[solar-historian] poll error',type(e).__name__,flush=True)
        time.sleep(2)


class API(Handler):
    def do_GET(self):
        path = urlsplit(self.path)
        if path.path == '/api/latest':
            r = latest(1); send_json(self, 200, {'sample':r[0] if r else None})
        elif path.path == '/api/history':
            text = parse_qs(path.query).get('limit',['25'])[0]
            limit = min(120,max(1,int(text))) if text.isdigit() else 25
            samples = latest(limit)
            send_json(self, 200, {'samples': samples})
        elif path.path == '/health': send_json(self, 200, {'ok':True})
        else: send_json(self, 404, {'error':'not_found'})


if __name__ == '__main__':
    with connect(): pass
    threading.Thread(target=loop,daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0', int(os.getenv('PORT','8080'))), API).serve_forever()
