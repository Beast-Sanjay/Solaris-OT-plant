"""L1 feeder breaker/revenue meter. Receives energy *from transformer*, not PPC.
Independent protection relay latches faults. Operator close cannot bypass a relay trip.
"""
import os,threading,time,json
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
from common import JSONHandler,read_json,send_json
TOKEN=os.getenv('CONTROL_TOKEN','')
TRANSFORMER_URL=os.getenv('TRANSFORMER_URL','')
lock=threading.RLock()
state={'device':'FDR-33KV-01','breaker_closed':True,'trip_latched':False,'trip_reason':None,
       'incoming_kw':0,'export_kw':0,'line_voltage_kv':33.0,'frequency_hz':50.,'line_current_a':0,
       'reactive_kvar':0,'export_kwh':0,'transformer_efficiency_pct':100.,
       'last_update':0,'connected':False,'status':'STARTING'}
def snapshot():
    with lock:return {k:v for k,v in state.items() if not k.startswith('_')}
def measure(kw,now=None):
    if type(kw) not in (int,float) or not 0<=kw<=15000:raise ValueError('invalid incoming power')
    now=time.monotonic() if now is None else now
    with lock:
        last=state.get('_mono',now);dt=max(0,min(5,now-last));state['_mono']=now
        export=round(kw,2) if state['breaker_closed'] else 0
        state.update(incoming_kw=round(kw,2),export_kw=export,
            line_current_a=round(export*1000/(1.732*33000*0.995),2),reactive_kvar=round(export*0.1004,2),
            export_kwh=round(state['export_kwh']+export*dt/3600,3),last_update=time.time(),connected=True,
            status=('PROTECTION_TRIP' if state['trip_latched'] else 'BREAKER_OPEN' if not state['breaker_closed'] else 'EXPORTING' if export>0 else 'STANDBY'))
        return snapshot()
def poll_transformer():
    while True:
        try:
            with urlopen(TRANSFORMER_URL+'/api/state',timeout=3) as r:tx=json.load(r)
            if not tx.get('connected'):raise ValueError('tx offline')
            measure(float(tx['delivered_kw']))
            with lock:state['transformer_efficiency_pct']=round(100*tx['delivered_kw']/tx['incoming_kw'],2) if tx['incoming_kw'] else 100.
        except (OSError,ValueError,KeyError,TimeoutError):
            with lock:state.update(connected=False,export_kw=0,line_current_a=0,status='TRANSFORMER_TELEMETRY_LOST')
        time.sleep(2)
class Handler(JSONHandler):
    def do_GET(self):
        if self.path=='/api/state':return send_json(self,200,snapshot())
        if self.path=='/health':return send_json(self,200 if snapshot()['connected'] else 503,{'ok':snapshot()['connected']})
        return send_json(self,404,{'error':'not_found'})
    def do_POST(self):
        if self.path not in ('/api/feed','/api/breaker','/api/trip','/api/reset'):return send_json(self,404,{'error':'not_found'})
        is_relay=self.path in ('/api/trip','/api/reset')
        if not TOKEN or self.headers.get('X-Relay-Token' if is_relay else 'X-PPC-Token')!=TOKEN:
            return send_json(self,403,{'error':'unauthorized'})
        try:
            obj=read_json(self)
            if self.path=='/api/feed':
                if TRANSFORMER_URL:return send_json(self,409,{'error':'feeder_input_owned_by_transformer'})
                return send_json(self,200,measure(obj['incoming_kw']))
            with lock:
                if self.path=='/api/trip':
                    reason=obj.get('reason','PROTECTION_TRIP')
                    if not isinstance(reason,str) or not 1<=len(reason)<=80:raise ValueError('bad_reason')
                    state.update(breaker_closed=False,trip_latched=True,trip_reason=reason,export_kw=0,line_current_a=0,status='PROTECTION_TRIP')
                elif self.path=='/api/reset':
                    state.update(trip_latched=False,trip_reason=None,status='RESET_READY')
                else:
                    closed=obj.get('closed')
                    if type(closed) is not bool:raise ValueError('closed must be bool')
                    if closed and state['trip_latched']:return send_json(self,409,{'error':'relay_trip_latched'})
                    state.update(breaker_closed=closed,export_kw=state['export_kw'] if closed else 0,
                        status='STANDBY' if closed else 'BREAKER_OPEN')
                return send_json(self,200,snapshot())
        except (ValueError,TypeError,KeyError):return send_json(self,400,{'error':'invalid_request'})
if __name__=='__main__':
    if TRANSFORMER_URL:threading.Thread(target=poll_transformer,daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','8080'))),Handler).serve_forever()
