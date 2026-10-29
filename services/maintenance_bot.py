"""L4 maintenance planner: read ONLY AD-gated historian summaries and create SQL work orders.
No direct access to OT networks, controllers, or control commands.
"""
import base64,json,os,time,threading
from http.server import ThreadingHTTPServer
from urllib.request import Request,urlopen
import psycopg
from common import JSONHandler,send_json
HIST=os.getenv('HISTORIAN_URL','http://it-access:8080/api/devices/latest')
USERNAME=os.getenv('AD_USER','analyst');PASSWORD=os.getenv('AD_PASSWORD','')
DB_HOST=os.getenv('DB_HOST','db01');DB_PASS=os.getenv('DB_PASSWORD','')
state={'device':'MAINT-BOT-01','status':'STARTING','last_sync':None,'last_error':None,'new_work_orders':0,'observed_assets':0}
lock=threading.RLock()
def proposals(devices):
    """Specific, reproducible inspection work orders tied to live measured faults."""
    items=[]
    for name,entry in sorted(devices.items()):
        v=entry.get('values') or {};kind=entry.get('kind')
        if kind=='pv_array':
            if v.get('failed_strings',0):items.append((f'AUTO-{name}-STRINGS',f'{name}: inspect {v["failed_strings"]} failed PV strings'))
            if v.get('soiling_pct',0)>=5:items.append((f'AUTO-{name}-SOILING',f'{name}: schedule cleaning; soiling {v["soiling_pct"]}%'))
        elif kind=='inverter' and not entry.get('connected'):
            items.append((f'AUTO-{name}-COMMS',f'{name}: investigate inverter Modbus communication loss'))
        elif kind=='feeder' and v.get('trip_latched'):
            items.append((f'AUTO-{name}-TRIP',f'{name}: investigate latched breaker trip: {v.get("trip_reason")}'))
        elif kind=='transformer' and v.get('winding_c',0)>=78:
            items.append((f'AUTO-{name}-THERMAL',f'{name}: transformer winding temperature {v["winding_c"]} C'))
        elif kind=='protection_relay' and v.get('trip_latched'):
            items.append((f'AUTO-{name}-RELAY',f'{name}: review protection relay trip and feeder events'))
    return items
def sync_once():
    if not PASSWORD or not DB_PASS:raise ValueError('missing AD/DB credentials')
    auth=base64.b64encode(f'{USERNAME}:{PASSWORD}'.encode()).decode()
    req=Request(HIST,headers={'Authorization':'Basic '+auth})
    with urlopen(req,timeout=10) as resp:data=json.load(resp)
    devices=data.get('historian',data).get('devices')
    if not isinstance(devices,dict):raise ValueError('no historian devices')
    orders=proposals(devices)
    inserted=0
    with psycopg.connect(host=DB_HOST,user='otlab',password=DB_PASS,dbname='corporate',connect_timeout=5) as db:
        with db.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS work_orders (
                id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('planned','approved','closed')),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
            for reference,title in orders:
                cur.execute("""INSERT INTO work_orders(reference,title,status) VALUES(%s,%s,'planned')
                    ON CONFLICT(reference) DO UPDATE SET title=excluded.title
                    WHERE work_orders.status!='closed' RETURNING id""",(reference,title))
                if cur.fetchone():inserted+=1
    with lock:state.update(status='RUNNING',last_sync=time.time(),last_error=None,
        new_work_orders=inserted,observed_assets=len(devices))
    return inserted
def run():
    while True:
        try:sync_once()
        except (OSError,ValueError,KeyError,psycopg.Error) as exc:
            with lock:state.update(status='DEGRADED',last_error=type(exc).__name__)
            print('maintenance sync:',type(exc).__name__,flush=True)
        time.sleep(15)
class Handler(JSONHandler):
    def do_GET(self):
        if self.path in ('/api/state','/health'):
            with lock:record=dict(state)
            return send_json(self,200 if record['status']=='RUNNING' else 503,record)
        send_json(self,404,{'error':'not_found'})
if __name__=='__main__':
    threading.Thread(target=run,daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','8080'))),Handler).serve_forever()
