"""L1 independent 0.69/33 kV transformer (plant training model, not a power-flow solver).
The PPC sends its AC bus estimate to this device; the feeder *reads the transformer*,
not the PPC, so losing the transformer or its telemetry affects grid export.
"""
import os,threading,time
from http.server import ThreadingHTTPServer
from common import JSONHandler,send_json,read_json
TOKEN=os.getenv('CONTROL_TOKEN','')
lock=threading.RLock()
state={'device':'TX-33KV-01','connected':False,'lv_kv':0.69,'hv_kv':33.0,
       'rated_kva':11000,'incoming_kw':0.0,'delivered_kw':0.0,'loss_kw':0.0,
       'load_pct':0.0,'winding_c':34.0,'oil_c':32.0,'status':'STARTING','last_update':0}
def update_input(kw,now=None):
    if type(kw) not in (int,float) or not 0<=kw<=10500:raise ValueError('invalid_kw')
    now=time.time() if now is None else now
    with lock:
        load=kw/11000
        efficiency=max(0.95,0.993-0.010*load*load)
        delivered=round(kw*efficiency,2)
        state.update(connected=True,incoming_kw=round(kw,2),delivered_kw=delivered,
            loss_kw=round(kw-delivered,2),load_pct=round(load*100,2),
            winding_c=round(34+50*load*load,1),oil_c=round(32+36*load*load,1),
            status='HIGH_TEMPERATURE' if 34+50*load*load>=78 else ('ENERGIZED' if kw>0 else 'STANDBY'),last_update=now)
        return dict(state)
class Handler(JSONHandler):
    def do_GET(self):
        if self.path=='/api/state':
            with lock:s=dict(state)
            return send_json(self,200,s)
        if self.path=='/health':return send_json(self,200,{'ok':True,'role':'step_up_transformer'})
        return send_json(self,404,{'error':'not_found'})
    def do_POST(self):
        if self.path!='/api/input':return send_json(self,404,{'error':'not_found'})
        if not TOKEN or self.headers.get('X-PPC-Token')!=TOKEN:return send_json(self,403,{'error':'token_required'})
        try:return send_json(self,200,update_input(read_json(self)['incoming_kw']))
        except (ValueError,TypeError,KeyError):return send_json(self,400,{'error':'invalid_input'})
if __name__=='__main__':ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','8080'))),Handler).serve_forever()
