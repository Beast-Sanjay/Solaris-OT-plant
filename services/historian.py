"""Level 3 OT historian: polls SCADA and retains time-series with anomaly notices."""
import json
import os
import sqlite3
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
from common import JSONHandler, send_json

DB = os.getenv('DB_PATH', '/data/historian.sqlite3')


def connect():
    db = sqlite3.connect(DB, timeout=10)
    db.execute('pragma journal_mode=WAL')
    db.execute('create table if not exists samples (ts real primary key, level real, temp real, flow real, pump integer, setpoint integer, connected integer)')
    return db


def rows(limit):
    with connect() as db:
        return [dict(zip(('time','level_pct','temperature_c','flow_lpm','pump_on','setpoint_pct','field_connected'),r)) for r in db.execute('select ts,level,temp,flow,pump,setpoint,connected from samples order by ts desc limit ?', (limit,))]


def emit(event):
    try:
        data = json.dumps(event).encode()
        req = Request(os.environ.get('SOC_URL', 'http://soc-conduit:8080/api/events'), data=data, method='POST', headers={'Content-Type': 'application/json'})
        with urlopen(req, timeout=2): pass
    except (OSError, TimeoutError):
        pass


def poll():
    last_alert = 0
    while True:
        try:
            with urlopen(os.environ['POLL_URL'], timeout=4) as response:
                sample = json.load(response)
            v = sample['values']
            if sample['connected']:
                ts = time.time()
                with connect() as db:
                    db.execute('insert into samples values (?,?,?,?,?,?,?)', (ts, v['level_pct'], v['temperature_c'],v['flow_lpm'],int(v['pump_on']),v['setpoint_pct'],int(v['field_connected'])))
                    # Prevent unlimited growth in continuous operation (>5000 kept).
                    db.execute('delete from samples where ts not in (select ts from samples order by ts desc limit 5000)')
                if (v['level_pct'] > 85 or v['temperature_c'] > 70) and ts - last_alert > 60:
                    emit({'time': ts, 'source': 'historian', 'severity': 'warning', 'event': 'process_outside_thresholds', 'values': v})
                    last_alert = ts
        except (OSError, KeyError, ValueError, TimeoutError):
            pass
        time.sleep(3)


class Handler(JSONHandler):
    def do_GET(self):
        p = urlsplit(self.path)
        if p.path == '/api/latest':
            sample = rows(1)
            send_json(self, 200, {'sample': sample[0] if sample else None, 'count': len(sample)})
        elif p.path == '/api/history':
            limit = min(100, max(1, int(parse_qs(p.query).get('limit', ['20'])[0]) if parse_qs(p.query).get('limit',['20'])[0].isdigit() else 20))
            send_json(self, 200, {'samples': rows(limit)})
        else: send_json(self, 404, {'error': 'not_found'})


if __name__ == '__main__':
    with connect(): pass
    threading.Thread(target=poll, daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0', int(os.getenv('PORT', '8080'))), Handler).serve_forever()
