"""L1 protection relay: observes feeder/transformer and independently trips its breaker.
Illustrative 50/51/27/59/81 checks and manually triggered *test* trip.
No vendor relay or certified protection timing is modelled. Trip is latched at feeder.
"""
import json,os,threading,time
from http.server import ThreadingHTTPServer
from urllib.request import Request,urlopen
from common import JSONHandler,read_json,send_json
TOKEN=os.getenv('CONTROL_TOKEN','')
FEEDER=os.getenv('FEEDER_URL','http://feeder-33kv:8080')
TX=os.getenv('TRANSFORMER_URL','http://transformer-33kv:8080')
lock=threading.RLock()
state={'device':'REL-33KV-01','connected':False,'status':'STARTING','trip_count':0,
       'trip_latched':False,'trip_reason':None,'breaker_closed':True,'measured_current_a':0,
       'frequency_hz':50.0,'voltage_kv':33.0,'winding_c':0,'last_update':0}
def call(path,payload):
    req=Request(FEEDER+path,data=json.dumps(payload).encode(),method='POST',headers={'Content-Type':'application/json','X-Relay-Token':TOKEN})
    with urlopen(req,timeout=3) as r:return json.load(r)
def trip(reason):
    result=call('/api/trip',{'reason':reason})
    with lock:state.update(trip_latched=True,trip_reason=reason,breaker_closed=False,status='TRIPPED',trip_count=state['trip_count']+1)
    return result
def reset():
    result=call('/api/reset',{})
    with lock:state.update(trip_latched=False,trip_reason=None,breaker_closed=False,status='RESET_READY')
    return result
def poll():
    while True:
        try:
            with urlopen(FEEDER+'/api/state',timeout=3) as r:f=json.load(r)
            with urlopen(TX+'/api/state',timeout=3) as r:t=json.load(r)
            current=float(f.get('line_current_a',0));volt=float(f.get('line_voltage_kv',33));freq=float(f.get('frequency_hz',50))
            winding=float(t.get('winding_c',0));reason=None
            if f.get('breaker_closed'):
                if current>220:reason='50_51_OVERCURRENT'
                elif volt<29.7 or volt>36.3:reason='27_59_VOLTAGE'
                elif freq<49.0 or freq>51.0:reason='81_FREQUENCY'
                elif winding>88:reason='TRANSFORMER_OVERHEAT'
            if reason and not f.get('trip_latched'):trip(reason)
            with lock:state.update(connected=True,breaker_closed=f['breaker_closed'],trip_latched=f.get('trip_latched',False),
                trip_reason=f.get('trip_reason'),measured_current_a=current,frequency_hz=freq,voltage_kv=volt,
                winding_c=winding,last_update=time.time(),status='TRIPPED' if f.get('trip_latched') else 'MONITORING')
        except (OSError,ValueError,TimeoutError,KeyError):
            with lock:state.update(connected=False,status='COMMUNICATION_LOSS')
        time.sleep(2)
class Handler(JSONHandler):
    def do_GET(self):
        if self.path in ('/api/state','/health'):
            with lock:s=dict(state)
            return send_json(self,200,s)
        return send_json(self,404,{'error':'not_found'})
    def do_POST(self):
        if self.path not in ('/api/test/trip','/api/reset-trip'):return send_json(self,404,{'error':'not_found'})
        if not TOKEN or self.headers.get('X-PPC-Token')!=TOKEN:return send_json(self,403,{'error':'token_required'})
        try:
            if self.path=='/api/test/trip':
                obj=read_json(self)
                if obj.get('confirm') is not True:raise ValueError('confirmation_required')
                result=trip('OPERATOR_TEST_TRIP')
            else:
                obj=read_json(self)
                if obj.get('confirm') is not True:raise ValueError('confirmation_required')
                result=reset()
            send_json(self,200,result)
        except (OSError,ValueError,TypeError,TimeoutError):send_json(self,409,{'error':'relay_command_failed'})
if __name__=='__main__':
    threading.Thread(target=poll,daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','8080'))),Handler).serve_forever()
