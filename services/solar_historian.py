"""Level 3 SQL historian for live site and per-asset solar telemetry, with SOC events."""
import json,os,sqlite3,threading,time
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs,urlsplit
from urllib.request import Request,urlopen
from common import JSONHandler,send_json
DB=os.getenv('DB_PATH','/data/solar_historian.sqlite3')
def connect():
    db=sqlite3.connect(DB,timeout=10)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS plant_samples(id INTEGER PRIMARY KEY, ts REAL NOT NULL, generation_kw REAL, export_kw REAL, dispatch_kw REAL, irradiance REAL, breaker_closed INTEGER, online_inverters INTEGER, alarm_count INTEGER)')
    db.execute('CREATE TABLE IF NOT EXISTS asset_samples(id INTEGER PRIMARY KEY, ts REAL NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL, power_kw REAL, connected INTEGER, payload TEXT NOT NULL)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_assets ON asset_samples(name,id)')
    return db
@contextmanager
def database():
    db=connect()
    try:
        with db:yield db
    finally:db.close()
def save_snapshot(snapshot,now=None):
    now=now or time.time()
    arrays=snapshot.get('arrays') or {};inverters=snapshot.get('inverters') or {}
    feeder=snapshot.get('feeder') or {}
    avg_irr=round(sum(v.get('irradiance_w_m2',0) for v in arrays.values())/max(1,len(arrays)),1)
    with database() as db:
        db.execute('INSERT INTO plant_samples(ts,generation_kw,export_kw,dispatch_kw,irradiance,breaker_closed,online_inverters,alarm_count) VALUES (?,?,?,?,?,?,?,?)',
            (now,snapshot.get('generation_kw',0),snapshot.get('export_kw',0),snapshot.get('dispatch_kw',0),avg_irr,int(bool(feeder.get('breaker_closed'))),snapshot.get('online_inverters',0),snapshot.get('alarm_count',0)))
        for kind,items in (('pv_array',arrays),('inverter',inverters),
          ('feeder',{'FDR-33KV-01':feeder}),
          ('transformer',{'TX-33KV-01':snapshot.get('transformer') or {}}),
          ('protection_relay',{'REL-33KV-01':snapshot.get('protection_relay') or {}}),
          ('grid_dispatch',{'GRID-ORDER-01':snapshot.get('grid_order') or {}}),
          ('weather',{'MET-01':snapshot.get('weather') or {}}),
          ('scada',{'SCADA-01':{'device':'SCADA-01','connected':bool(snapshot.get('last_update')),'last_update':snapshot.get('last_update')}}),
          ('ppc',{'PPC-01':snapshot})):
            for name,asset in items.items():
                if not asset:continue
                power=asset.get('active_kw',asset.get('dc_kw',asset.get('export_kw',asset.get('generation_kw',0))))
                # PPC payload trimmed; avoid repeated nested array data.
                item=asset if kind!='ppc' else {'export_limit_pct':snapshot.get('export_limit_pct'), 'generation_kw':snapshot.get('generation_kw'), 'alarm_count':snapshot.get('alarm_count')}
                db.execute('INSERT INTO asset_samples(ts,name,kind,power_kw,connected,payload) VALUES (?,?,?,?,?,?)',
                    (now,name,kind,power,int(bool(asset.get('connected',True))),json.dumps(item,separators=(',',':'))))
        db.execute('DELETE FROM plant_samples WHERE id NOT IN (SELECT id FROM plant_samples ORDER BY id DESC LIMIT 10000)')
        db.execute('DELETE FROM asset_samples WHERE id NOT IN (SELECT id FROM asset_samples ORDER BY id DESC LIMIT 50000)')
def plant_rows(limit):
    with database() as db: rows=db.execute('SELECT ts,generation_kw,export_kw,dispatch_kw,irradiance,breaker_closed,online_inverters,alarm_count FROM plant_samples ORDER BY id DESC LIMIT ?',(limit,)).fetchall()
    return [dict(zip(('time','generation_kw','export_kw','dispatch_kw','irradiance_w_m2','breaker_closed','online_inverters','alarm_count'),r)) for r in rows]
def asset_rows(limit,name=None):
    with database() as db:
        sql='SELECT ts,name,kind,power_kw,connected,payload FROM asset_samples'
        args=(limit,)
        if name:sql+=' WHERE name=?';args=(name,limit)
        rows=db.execute(sql+' ORDER BY id DESC LIMIT ?',args).fetchall()
    return [{'time':r[0],'device':r[1],'kind':r[2],'power_kw':r[3],'connected':bool(r[4]),'values':json.loads(r[5])} for r in rows]
def latest_devices():
    with database() as db:names=[r[0] for r in db.execute('SELECT DISTINCT name FROM asset_samples')]
    return {n:asset_rows(1,n)[0] for n in names}
def emit(name,event,severity='warning'):
    try:
        payload=json.dumps({'time':time.time(),'source':'solar-historian','event':event,'severity':severity,'values':{'asset':name}}).encode()
        req=Request(os.getenv('SOC_URL','http://soc-conduit:8080/api/events'),data=payload,method='POST',headers={'Content-Type':'application/json'})
        with urlopen(req,timeout=2):pass
    except (OSError,TimeoutError):pass
def poll():
    last_alarm={};last_status={}
    while True:
        try:
            with urlopen(os.environ['POLL_URL'],timeout=4) as r:sample=json.load(r)
            if sample.get('last_update'):
                save_snapshot(sample)
                for name,dev in sample.get('inverters',{}).items():
                    connected=bool(dev.get('connected'))
                    if last_status.get(name,True) and not connected and time.time()-last_alarm.get(name,0)>20:
                        emit(name,'inverter_communication_loss','high');last_alarm[name]=time.time()
                    last_status[name]=connected
                for name,a in sample.get('arrays',{}).items():
                    if a.get('failed_strings',0) and time.time()-last_alarm.get(name+'strings',0)>90:
                        emit(name,'pv_string_failure','medium');last_alarm[name+'strings']=time.time()
                    if a.get('soiling_pct',0)>=5 and time.time()-last_alarm.get(name+'soiling',0)>90:
                        emit(name,'pv_soiling_above_threshold','warning');last_alarm[name+'soiling']=time.time()
                if sample.get('protection_relay',{}).get('trip_latched') and time.time()-last_alarm.get('relay',0)>30:
                    emit('REL-33KV-01','protection_trip_latched','high');last_alarm['relay']=time.time()
                if sample.get('feeder') and not sample['feeder'].get('breaker_closed') and time.time()-last_alarm.get('feeder',0)>30:
                    emit('FDR-33KV-01','feeder_breaker_open','high');last_alarm['feeder']=time.time()
        except (OSError,ValueError,TimeoutError):pass
        time.sleep(3)
class Handler(JSONHandler):
    def do_GET(self):
        p=urlsplit(self.path);q=parse_qs(p.query)
        raw=q.get('limit',['30'])[0];limit=min(200,max(1,int(raw) if raw.isdigit() else 30))
        if p.path in ('/api/latest','/api/plant/latest'):
            data=plant_rows(1);send_json(self,200,{'sample':data[0] if data else None})
        elif p.path in ('/api/history','/api/plant/history'):
            send_json(self,200,{'samples':plant_rows(limit)})
        elif p.path=='/api/devices/latest':send_json(self,200,{'devices':latest_devices()})
        elif p.path=='/api/devices/history':
            name=q.get('device',[None])[0]
            if name and (len(name)>80 or not all(c.isalnum() or c in '-_' for c in name)):
                return send_json(self,400,{'error':'invalid_device'})
            send_json(self,200,{'samples':asset_rows(limit,name)})
        elif p.path=='/health':send_json(self,200,{'ok':True,'last':plant_rows(1)})
        else:send_json(self,404,{'error':'not_found'})
if __name__=='__main__':
    with database():pass
    threading.Thread(target=poll,daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','8080'))),Handler).serve_forever()
