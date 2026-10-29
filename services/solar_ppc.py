"""Level 2 plant power controller: surveys four L1 inverter Modbus endpoints,
dispatches per-inverter export caps and reports measured production to feeder.
All commands apply to *simulation only*. Not a grid-following controls model.
"""
import json,os,socket,struct,threading,time
from http.server import ThreadingHTTPServer
from urllib.request import Request,urlopen
from common import JSONHandler,read_json,send_json
TOKEN=os.getenv('CONTROL_TOKEN','')
def inverter_endpoints():
    raw=os.getenv('INVERTER_ENDPOINTS','')
    if raw:
        # name=host:http_port:modbus_port, ...
        result=[]
        for item in raw.split(','):
            name,dest=item.split('=',1)
            host,http_port,modbus_port=dest.rsplit(':',2)
            result.append((name,host,int(http_port),int(modbus_port)))
        return result
    return [('INV-%02d'%i,'inverter-conduit-%02d'%i,8080,15020) for i in range(1,5)]
ENDPOINTS=inverter_endpoints()
FEEDER=os.getenv('FEEDER_URL','http://feeder-conduit:8080')
TRANSFORMER=os.getenv('TRANSFORMER_URL','')
RELAY=os.getenv('RELAY_URL','')
GRID=os.getenv('GRID_URL','')
lock=threading.RLock()
state={'device':'PPC-01','plant':'SOLARIS ONE','rated_ac_kw':10000,
       'export_limit_pct':100.,'generation_kw':0,'export_kw':0,
       'dispatch_kw':0,'plant_power_factor':0.995,'inverters':{},'arrays':{},
       'feeder':{},'transformer':{},'protection_relay':{},'grid_order':{},'grid_limit_pct':100.,'effective_limit_pct':100.,'weather':{},'online_inverters':0,'alarm_count':0,'last_update':None,
       'connected':False,'simulation':True}
def get_json(url, timeout=2):
    with urlopen(url,timeout=timeout) as r:return json.load(r)
def post_json(url,data):
    payload=json.dumps(data).encode()
    req=Request(url,data=payload,method='POST',headers={'Content-Type':'application/json','X-PPC-Token':TOKEN})
    with urlopen(req,timeout=2) as r:return json.load(r)
def read_modbus(host,port=15020):
    with socket.create_connection((host,port),timeout=3) as sock:
        sock.settimeout(3)
        sock.sendall(struct.pack('!HHHBBHH',33,0,6,1,3,0,12))
        def recv(n):
            out=bytearray()
            while len(out)<n:
                x=sock.recv(n-len(out))
                if not x:raise OSError('closed')
                out.extend(x)
            return bytes(out)
        hdr=recv(7);tid,proto,length,unit=struct.unpack('!HHHB',hdr)
        if tid!=33 or proto!=0 or length!=27:raise OSError('invalid_modbus_header')
        data=recv(26)
        if data[:2]!=bytes([3,24]):raise OSError('invalid_modbus_payload')
        return struct.unpack('!12H',data[2:])
def compute_targets(limit_pct, inverters):
    """Fair plant-level upper-limit allocation; each inverter independently capped."""
    max_cap=2500.0
    # A plant 75% export limit is 7.5MW; equal inverter limit 75%.
    return {name:round(limit_pct,2) for name in inverters}
def poll():
    last_dispatch={};last_feeder=None
    while True:
        with lock:limit=state['export_limit_pct'];closed=state.get('requested_breaker_closed',True)
        grid={};grid_limit=100.
        if GRID:
            try:
                grid=get_json(GRID+'/api/state')
                grid_limit=float(grid['export_limit_pct'])
                if not 0<=grid_limit<=100:raise ValueError('grid_limit_invalid')
            except (OSError,ValueError,KeyError,TimeoutError):
                # Freeze at zero on loss of a dispatch constraint, rather than silently export unrestricted.
                grid={'device':'GRID-ORDER-01','connected':False,'status':'COMMUNICATION_LOSS'}
                grid_limit=0.
        effective_limit=min(limit,grid_limit) if closed else 0.0  # grid-following PV cannot sustain output into an open feeder
        readings={};arrays={};errors=[]
        for name,host,http_port,modbus_port in ENDPOINTS:
            try:
                registers=read_modbus(host,modbus_port) # REAL Modbus frame through a dual-homed L1/L2 conduit
                details=get_json(f'http://{host}:{http_port}/api/state')
                details['modbus_kw']=registers[0]/10
                details['modbus_connected']=bool(registers[8])
                readings[name]=details
                arrays[details['array']]={'device':details['array'],'dc_kw':details['available_dc_kw'],
                    'irradiance_w_m2':details['irradiance_w_m2'],'module_c':details['module_c'],
                    'dc_voltage_v':details['dc_voltage_v'],'dc_current_a':details['dc_current_a'],
                    'connected':details['array_connected'],
                    'soiling_pct':details.get('soiling_pct',0),'failed_strings':details.get('failed_strings',0),
                    'active_strings':details.get('active_strings',0),'strings':details.get('strings',0)}
                if not details['connected']:errors.append(name+' offline')
                if last_dispatch.get(name)!=effective_limit or abs(details.get('limit_pct',-1)-effective_limit)>0.01:
                    post_json(f'http://{host}:{http_port}/api/limit',{'limit_pct':effective_limit})
                    last_dispatch[name]=effective_limit
            except (OSError,ValueError,KeyError,TimeoutError) as e:
                readings[name]={'device':name,'connected':False,'status':'COMMUNICATION_LOSS','active_kw':0,'error':type(e).__name__}
                errors.append(name+' offline')
        total=round(sum(v.get('active_kw',0) for v in readings.values() if v.get('connected')),2)
        weather={}
        if arrays:
            weather={'device':'MET-01','connected':all(x.get('connected',False) for x in arrays.values()),
                'irradiance_w_m2':round(sum(x.get('irradiance_w_m2',0) for x in arrays.values())/len(arrays),1),
                'module_c':round(sum(x.get('module_c',0) for x in arrays.values())/len(arrays),1),
                'source':'array_relayed_measurements'}
        transformer={};relay={};feeder={}
        if TRANSFORMER:
            try:
                post_json(TRANSFORMER+'/api/input',{'incoming_kw':total})
                transformer=get_json(TRANSFORMER+'/api/state')
                if transformer.get('status')=='HIGH_TEMPERATURE':errors.append('Transformer hot')
            except (OSError,ValueError,KeyError,TimeoutError):errors.append('Transformer communications lost')
        if RELAY:
            try:
                relay=get_json(RELAY+'/api/state')
                if relay.get('trip_latched'):
                    closed=False
                    errors.append('Protection relay trip latched')
                elif not relay.get('connected'):errors.append('Protection relay communications lost')
            except (OSError,ValueError,KeyError,TimeoutError):
                errors.append('Protection relay communications lost')
        try:
            live_feeder=get_json(FEEDER+'/api/state')
            if live_feeder.get('trip_latched'):
                closed=False
                if 'Protection relay trip latched' not in errors:errors.append('Protection relay trip latched')
            if last_feeder is None or last_feeder!=closed or live_feeder.get('breaker_closed')!=closed:
                post_json(FEEDER+'/api/breaker',{'closed':closed});last_feeder=closed
            if not TRANSFORMER:post_json(FEEDER+'/api/feed',{'incoming_kw':total})
            feeder=get_json(FEEDER+'/api/state')
            if not feeder.get('breaker_closed'):errors.append('Feeder breaker open')
        except (OSError,ValueError,KeyError,TimeoutError):
            errors.append('Feeder communications lost')
        with lock:
            online_count=sum(bool(v.get('connected')) for v in readings.values())
            state.update(generation_kw=total,export_kw=feeder.get('export_kw',0),
                dispatch_kw=round(10000*effective_limit/100,1),inverters=readings,arrays=arrays,feeder=feeder,
                transformer=transformer,protection_relay=relay,grid_order=grid,grid_limit_pct=grid_limit,
                effective_limit_pct=effective_limit,weather=weather,
                online_inverters=online_count,
                alarm_count=len(errors),alarms=errors,last_update=time.time(),connected=bool(feeder) and online_count==4)
        time.sleep(2)
class Handler(JSONHandler):
    def do_GET(self):
        if self.path=='/api/state':
            with lock:s=dict(state)
            send_json(self,200,s)
        elif self.path=='/health':
            with lock:ok=state['online_inverters']==4 and bool(state['feeder'])
            send_json(self,200 if ok else 503,{'ok':ok,'online_inverters':state['online_inverters']})
        else:send_json(self,404,{'error':'not_found'})
    def do_POST(self):
        if self.path!='/api/dispatch':return send_json(self,404,{'error':'not_found'})
        if not TOKEN or self.headers.get('X-PPC-Token')!=TOKEN:return send_json(self,403,{'error':'unauthorized'})
        try:
            req=read_json(self)
            if not isinstance(req,dict) or not req or set(req)-{'export_limit_pct','breaker_closed','relay_action'}:
                raise ValueError('unsupported dispatch')
            if 'relay_action' in req:
                action=req['relay_action']
                if action not in ('test_trip','reset_trip') or len(req)!=1 or not RELAY:raise ValueError('relay action unavailable')
                endpoint='/api/test/trip' if action=='test_trip' else '/api/reset-trip'
                result=post_json(RELAY+endpoint,{'confirm':True})
                if action=='test_trip':
                    with lock:state['requested_breaker_closed']=False
                return send_json(self,200,{'ok':True,'relay':result})
            if 'export_limit_pct' in req:
                limit=req['export_limit_pct']
                if type(limit) not in (int,float) or not 0<=limit<=100:raise ValueError()
                with lock:state['export_limit_pct']=float(limit)
            if 'breaker_closed' in req:
                if type(req['breaker_closed']) is not bool:raise ValueError()
                with lock:state['requested_breaker_closed']=req['breaker_closed']
            with lock:s={'export_limit_pct':state['export_limit_pct'],'breaker_closed':state.get('requested_breaker_closed',True)}
            send_json(self,200,{'ok':True,'dispatch':s})
        except (ValueError,TypeError):send_json(self,400,{'error':'invalid_setpoint'})
if __name__=='__main__':
    threading.Thread(target=poll,daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','8080'))),Handler).serve_forever()
