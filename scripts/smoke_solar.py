#!/usr/bin/env python3
"""Live no-Docker end-to-end test: met -> arrays -> inverter Modbus -> PPC -> feeder -> SCADA -> historian.
Runs all processes on loopback with per-process test ports; not a Docker-network test.
"""
import json,os,subprocess,sys,tempfile,time,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SERVICE=ROOT/'services'
TOKEN='SmokeTestSolarTokenDoNotUseInDeployment'
processes=[]
def launch(script,port,env={}):
    e=os.environ.copy();e.update(env);e['PORT']=str(port)
    p=subprocess.Popen([sys.executable,'-u',str(SERVICE/script)],env=e,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    processes.append((script,p))
    return p
def get(url,timeout=2):
    with urllib.request.urlopen(url,timeout=timeout) as r:return json.load(r)
def post(url,obj,header='X-Lab-Control-Token'):
    req=urllib.request.Request(url,data=json.dumps(obj).encode(),method='POST',headers={'Content-Type':'application/json',header:TOKEN})
    with urllib.request.urlopen(req,timeout=3) as r:return json.load(r)
def ready(url,predicate=None,seconds=28):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        try:
            x=get(url)
            if predicate is None or predicate(x):return x
        except Exception:pass
        time.sleep(.5)
    x=get(url);print('TIMEOUT:',x.get('export_kw'),x.get('export_limit_pct'),x.get('effective_limit_pct'),x.get('alarms'),[(n,d.get('limit_pct'),d.get('active_kw')) for n,d in x.get('inverters',{}).items()],flush=True)
    raise AssertionError('Timed out waiting for '+url)
def main():
    with tempfile.TemporaryDirectory(prefix='solar-smoke-') as tmp:
        launch('solar_weather.py',20100)
        ready('http://127.0.0.1:20100/api/state')
        for i in range(1,5):
            launch('solar_array.py',20100+i,{'ASSET_ID':f'PV-{i:02d}',
                'WEATHER_URL':'http://127.0.0.1:20100','YIELD_FACTOR':str(1-.01*(i-1)),
                'SOILING_PCT':str([.8,7.5,1.5,3][i-1]),'FAILED_STRINGS':str([0,0,2,0][i-1])})
        for i in range(1,5):
            launch('solar_inverter.py',20200+i,{'ASSET_ID':f'INV-{i:02d}',
                'ARRAY_ID':f'PV-{i:02d}', 'FIELD_URL':f'http://127.0.0.1:{20100+i}',
                'MODBUS_PORT':str(20400+i),'CONTROL_TOKEN':TOKEN})
        launch('solar_transformer.py',20501,{'CONTROL_TOKEN':TOKEN})
        launch('solar_feeder.py',20500,{'CONTROL_TOKEN':TOKEN,'TRANSFORMER_URL':'http://127.0.0.1:20501'})
        launch('solar_relay.py',20502,{'CONTROL_TOKEN':TOKEN,'FEEDER_URL':'http://127.0.0.1:20500',
            'TRANSFORMER_URL':'http://127.0.0.1:20501'})
        launch('solar_grid_dispatch.py',20503,{'CONTROL_TOKEN':TOKEN})
        # Exercise the real L1/L2 HTTP and native Modbus conduits, not just direct target URLs.
        for i in range(1,5):
            launch('solar_conduit.py',22300+i,{'TARGET_URL':f'http://127.0.0.1:{20200+i}',
                'TARGET_MODBUS_HOST':'127.0.0.1','TARGET_MODBUS_PORT':str(20400+i),
                'CONDUIT_MODBUS_PORT':str(22400+i),'ALLOWED_PATHS':'/api/state,/api/limit',
                'ALLOWED_METHODS':'GET,POST','CONDUIT_AUTH_TOKEN':TOKEN,'CONDUIT_AUTH_HEADER':'X-PPC-Token',
                'LISTEN_PORT':str(22300+i)})
        for name, target, paths, allow_posts in (
            (22500,20500,'/api/state,/api/breaker',True),
            (22501,20501,'/api/state,/api/input',True),
            (22502,20502,'/api/state,/api/test/trip,/api/reset-trip',True),
            (22503,20503,'/api/state',False)):
            launch('http_relay.py',name,{'TARGET_URL':f'http://127.0.0.1:{target}',
                'ALLOWED_PATHS':paths,'ALLOWED_METHODS':'GET,POST' if allow_posts else 'GET',
                'CONDUIT_AUTH_TOKEN':TOKEN if allow_posts else '', 'CONDUIT_AUTH_HEADER':'X-PPC-Token',
                'LISTEN_PORT':str(name)})
        endpoints=','.join(f'INV-{i:02d}=127.0.0.1:{22300+i}:{22400+i}' for i in range(1,5))
        launch('solar_ppc.py',20600,{'INVERTER_ENDPOINTS':endpoints,
            'FEEDER_URL':'http://127.0.0.1:22500','CONTROL_TOKEN':TOKEN,
            'TRANSFORMER_URL':'http://127.0.0.1:22501',
            'RELAY_URL':'http://127.0.0.1:22502','GRID_URL':'http://127.0.0.1:22503'})
        launch('solar_scada.py',20700,{'PPC_URL':'http://127.0.0.1:20600','CONTROL_TOKEN':TOKEN})
        launch('solar_historian.py',20800,{'POLL_URL':'http://127.0.0.1:20700/api/state',
            'DB_PATH':str(Path(tmp)/'solar_historian.sqlite3'), 'SOC_URL':'http://127.0.0.1:20999/api/events'})
        state=ready('http://127.0.0.1:20700/api/state',lambda o:o.get('online_inverters')==4 and o.get('export_kw',0)>100 and o.get('transformer',{}).get('delivered_kw',0)>0 and o.get('protection_relay',{}).get('connected'),seconds=35)
        assert len(state['inverters'])==4 and len(state['arrays'])==4,state
        assert state['transformer']['delivered_kw']>0 and state['protection_relay']['connected']
        assert state['grid_order']['device']=='GRID-ORDER-01'
        assert 0<state['export_kw']<=state['generation_kw']<=10000,state
        assert all(state['inverters'][f'INV-{i:02d}']['modbus_connected'] for i in range(1,5))
        print('[PASS] weather -> four distinct PV blocks -> Modbus inverters -> transformer -> feeder -> SCADA')
        assert state['arrays']['PV-02']['soiling_pct']>=5
        assert state['arrays']['PV-03']['failed_strings']==2
        print('[PASS] distinct PV-02 soiling and PV-03 open-string simulated faults observable')
        post('http://127.0.0.1:20503/api/order',{'export_limit_pct':40,'order_id':'GRID-TEST-0040'},header='X-Grid-Token')
        grid_reduced=ready('http://127.0.0.1:20700/api/state',
            lambda o:o.get('grid_limit_pct')==40 and o.get('export_kw',99999)<4000,seconds=18)
        assert grid_reduced['effective_limit_pct']==40
        print('[PASS] L3 grid dispatch order -> L2 PPC -> L1 inverter curtailment')
        post('http://127.0.0.1:20503/api/order',{'export_limit_pct':100,'order_id':'GRID-RESTORE'},header='X-Grid-Token')
        ready('http://127.0.0.1:20700/api/state',lambda o:o.get('grid_limit_pct')==100 and o.get('export_kw',0)>2000,seconds=18)
        baseline=state['export_kw']
        post('http://127.0.0.1:20700/api/control',{'export_limit_pct':20})
        constrained=ready('http://127.0.0.1:20700/api/state',lambda o:o.get('export_kw',99999)<=2000+5 and o.get('export_limit_pct')==20,seconds=16)
        assert constrained['export_kw']<baseline,(baseline,constrained['export_kw'])
        assert all(o.get('limit_pct')==20 for o in constrained['inverters'].values())
        print('[PASS] SCADA authenticated dispatch -> PPC -> all inverter caps -> measured feeder reduction')
        post('http://127.0.0.1:20700/api/control',{'breaker_closed':False})
        opened=ready('http://127.0.0.1:20700/api/state',lambda o:bool(o.get('feeder')) and o['feeder'].get('breaker_closed') is False and o['export_kw']==0 and o['generation_kw']<5,seconds=16)
        assert sum(a['dc_kw'] for a in opened['arrays'].values())>1000
        print('[PASS] feeder OPEN forces grid-following inverters to 0 AC; PV arrays retain available DC')
        post('http://127.0.0.1:20700/api/control',{'breaker_closed':True,'export_limit_pct':100})
        restored=ready('http://127.0.0.1:20700/api/state',lambda o:o.get('feeder',{}).get('breaker_closed') is True and o.get('export_kw',0)>2000,seconds=16)
        print('[PASS] plant restored; breaker closed + dispatch reset')
        post('http://127.0.0.1:20700/api/control',{'relay_action':'test_trip'})
        tripped=ready('http://127.0.0.1:20700/api/state',lambda o:o.get('feeder',{}).get('trip_latched') and o.get('export_kw')==0,seconds=18)
        assert tripped['feeder']['trip_reason']=='OPERATOR_TEST_TRIP'
        try:
            post('http://127.0.0.1:20500/api/breaker',{'closed':True},header='X-PPC-Token')
            raise AssertionError('latched breaker closed unexpectedly')
        except urllib.error.HTTPError as ex:assert ex.code==409
        print('[PASS] independent relay test trip -> latched feeder break, PPC cannot bypass it')
        post('http://127.0.0.1:20700/api/control',{'relay_action':'reset_trip'})
        post('http://127.0.0.1:20700/api/control',{'breaker_closed':True})
        ready('http://127.0.0.1:20700/api/state',lambda o:o.get('feeder',{}).get('breaker_closed') and o.get('export_kw',0)>1000,seconds=18)
        print('[PASS] explicit relay reset + operator close restores grid export')
        history=ready('http://127.0.0.1:20800/api/devices/latest',lambda o:all(k in o.get('devices',{}) for k in ('PV-01','PV-04','INV-01','INV-04','FDR-33KV-01','PPC-01','TX-33KV-01','REL-33KV-01','GRID-ORDER-01','MET-01')),seconds=18)
        plant=get('http://127.0.0.1:20800/api/plant/history?limit=10')
        assert len(plant['samples'])>0
        print(f'[PASS] historian persists {len(history["devices"])} operational assets with individual measurements')
        try:
            urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:20700/api/control',data=b'{"export_limit_pct":30}',method='POST',headers={'Content-Type':'application/json'}),timeout=2)
            raise AssertionError('control without token was accepted')
        except urllib.error.HTTPError as ex:assert ex.code==403
        print('[PASS] unauthenticated SCADA writes rejected')
        html=urllib.request.urlopen('http://127.0.0.1:20700/').read().decode()
        assert all(term in html for term in ('SOLARIS ONE','Plant energy flow','PPC-01','FDR-33KV-01','Inverter block monitoring'))
        print('[PASS] working solar SCADA HTML served')
try:
    main()
finally:
    for _,p in reversed(processes):
        if p.poll() is None:p.terminate()
    for name,p in reversed(processes):
        try:p.wait(timeout=3)
        except subprocess.TimeoutExpired:p.kill();p.wait(timeout=2)
        pass
