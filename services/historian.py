"""L3 OT historian with persistent per-device live Modbus-derived time series."""
import json
from contextlib import contextmanager
import os
import sqlite3
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
from common import JSONHandler, send_json

DB = os.getenv('DB_PATH', '/data/historian.sqlite3')
COLS = ('time','level_pct','temperature_c','flow_lpm','pump_on','setpoint_pct','field_connected')


def connect():
    db = sqlite3.connect(DB, timeout=10)
    db.execute('pragma journal_mode=WAL')
    db.execute('create table if not exists samples (ts real primary key, level real, temp real, flow real, pump integer, setpoint integer, connected integer)')
    db.execute('''create table if not exists device_samples (
      id integer primary key autoincrement, ts real not null, name text not null,
      level real, temp real, flow real, pump integer, setpoint integer, connected integer)''')
    db.execute('create index if not exists idx_device_samples_name on device_samples(name,ts desc)')
    return db


@contextmanager
def database():
    db = connect()
    try:
        with db:
            yield db
    finally:
        db.close()


def rows(limit):
    with database() as db:
        return [dict(zip(COLS, r)) for r in db.execute('select ts,level,temp,flow,pump,setpoint,connected from samples order by ts desc limit ?', (limit,))]


def device_rows(limit, name=None):
    with database() as db:
        if name:
            data = db.execute('select ts,name,level,temp,flow,pump,setpoint,connected from device_samples where name=? order by id desc limit ?', (name,limit))
        else:
            data = db.execute('select ts,name,level,temp,flow,pump,setpoint,connected from device_samples order by id desc limit ?', (limit,))
        return [dict(zip(('time','device',*COLS[1:]),r)) for r in data]


def latest_devices():
    with database() as db:
        names = [r[0] for r in db.execute('select distinct name from device_samples')]
    return {name: device_rows(1, name)[0] for name in names}


def emit(event):
    try:
        data = json.dumps(event).encode()
        req = Request(os.environ.get('SOC_URL', 'http://soc-conduit:8080/api/events'), data=data, method='POST', headers={'Content-Type':'application/json'})
        with urlopen(req, timeout=2): pass
    except (OSError, TimeoutError):
        pass


def save_snapshot(snapshot, now=None):
    now = now or time.time()
    devices = snapshot.get('devices') or {'plc-demo': snapshot}
    saved = []
    with database() as db:
        for name, detail in devices.items():
            if not detail.get('connected') or not detail.get('values'): continue
            v = detail['values']
            args = (now,name,v['level_pct'],v['temperature_c'],v['flow_lpm'],int(v['pump_on']),v['setpoint_pct'],int(v['field_connected']))
            db.execute('insert into device_samples(ts,name,level,temp,flow,pump,setpoint,connected) values (?,?,?,?,?,?,?,?)',args)
            saved.append((name,v))
            if name == 'plc-demo':
                db.execute('insert or replace into samples values (?,?,?,?,?,?,?)',(now, *args[2:]))
        db.execute('delete from samples where ts not in (select ts from samples order by ts desc limit 5000)')
        db.execute('delete from device_samples where id not in (select id from device_samples order by id desc limit 10000)')
    return saved


def poll():
    last_alert = {}
    last_connected = {}
    while True:
        try:
            with urlopen(os.environ['POLL_URL'],timeout=4) as response:
                snapshot = json.load(response)
            ts = time.time()
            devices = snapshot.get('devices') or {'plc-demo': snapshot}
            for name, d in devices.items():
                good = bool(d.get('connected') and d.get('values',{}).get('field_connected'))
                if name in last_connected and last_connected[name] and not good:
                    emit({'time':ts, 'source':'historian', 'severity':'high', 'event':'controller_offline', 'values':{'device':name}})
                last_connected[name] = good
            for name,v in save_snapshot(snapshot,now=ts):
                if (v['level_pct'] > 85 or v['temperature_c'] > 70) and ts-last_alert.get(name,0)>60:
                    emit({'time':ts,'source':'historian','severity':'warning', 'event':'process_outside_thresholds', 'values':{'device':name,**v}})
                    last_alert[name]=ts
        except (OSError, KeyError, ValueError, TimeoutError):
            pass
        time.sleep(3)


class Handler(JSONHandler):
    def do_GET(self):
        p = urlsplit(self.path)
        q = parse_qs(p.query)
        raw = q.get('limit',['20'])[0]
        limit = min(100, max(1, int(raw) if raw.isdigit() else 20))
        if p.path == '/api/latest':
            result=rows(1)
            send_json(self,200,{'sample':result[0] if result else None,'count':len(result)})
        elif p.path == '/api/history':
            send_json(self,200,{'samples':rows(limit)})
        elif p.path == '/api/devices/latest':
            send_json(self,200,{'devices':latest_devices()})
        elif p.path == '/api/devices/history':
            name=q.get('device',[None])[0]
            if name and (len(name)>80 or not name.replace('-','').replace('_','').isalnum()):
                return send_json(self,400,{'error':'invalid_device'})
            send_json(self,200,{'samples':device_rows(limit,name)})
        else: send_json(self,404,{'error':'not_found'})


if __name__ == '__main__':
    conn=connect()
    conn.close()
    threading.Thread(target=poll,daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','8080'))),Handler).serve_forever()
