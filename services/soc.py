"""Tiny SOC log ingest and view; NOT Malcolm or Elastic SIEM."""
import json
import os
import sqlite3
import time
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
from common import JSONHandler, send_json, read_json
DB = os.getenv('DB_PATH', '/data/soc.sqlite3')
SOC_HTML = Path(__file__).with_name('solar_ui').joinpath('soc.html').read_bytes()


def init():
    with sqlite3.connect(DB) as db:
        db.execute('create table if not exists events (id integer primary key autoincrement, ts real not null, source text not null, severity text not null, event_json text not null)')


class Handler(JSONHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/':
            self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(SOC_HTML))); self.end_headers();self.wfile.write(SOC_HTML)
            return
        if path not in ('/api/events','/health'):return send_json(self,404,{'error':'not_found'})
        if path == '/health':return send_json(self,200,{'ok':True,'role':'SOC event collector'})
        with sqlite3.connect(DB) as db:
            results = [json.loads(v[0]) for v in db.execute('select event_json from events order by id desc limit 100')]
        send_json(self, 200, {'events': results, 'note': 'Lightweight collector. Connect external Malcolm/Elastic separately.'})

    def do_POST(self):
        if self.path != '/api/events': return send_json(self, 404, {'error': 'not_found'})
        try:
            obj = read_json(self)
            if not isinstance(obj, dict): raise ValueError('not object')
            event = {'time': float(obj.get('time', time.time())), 'source': str(obj.get('source','unknown'))[:80],
                     'severity': str(obj.get('severity','info'))[:20], 'event': str(obj.get('event','event'))[:100],
                     'values': obj.get('values', {})}
            with sqlite3.connect(DB) as db:
                db.execute('insert into events (ts,source,severity,event_json) values (?,?,?,?)', (event['time'],event['source'],event['severity'],json.dumps(event)))
            # Optional Elasticsearch mirror. Local SQLite retains events if absent.
            try:
                req = Request(os.environ['SOC_ELASTIC_URL'].rstrip('/') + '/purdue-events/_doc',
                              data=json.dumps(event).encode(), method='POST',
                              headers={'Content-Type':'application/json'})
                with urlopen(req, timeout=1): pass
            except (KeyError, OSError, TimeoutError):
                pass
            return send_json(self, 201, {'ok': True})
        except (ValueError, TypeError, json.JSONDecodeError):
            return send_json(self, 400, {'error': 'invalid_event'})


if __name__ == '__main__':
    init()
    ThreadingHTTPServer(('0.0.0.0', int(os.getenv('PORT', '8080'))), Handler).serve_forever()
