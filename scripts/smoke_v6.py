#!/usr/bin/env python3
"""Additional V6 loopback smoke: authenticated conduit, field repair, public publisher.
Does NOT require Docker and never connects to physical OT devices.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

SERVICES=Path(__file__).resolve().parents[1]/'services'
TOKEN='SimulationLocalSmokeDoNotReuse'
processes=[]


def run(script,port,env=None):
    e=os.environ.copy();e.update(env or {});e['PORT']=str(port);e['LISTEN_PORT']=str(port)
    p=subprocess.Popen([sys.executable,'-u',str(SERVICES/script)],env=e,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    processes.append(p)
    return p


def get(port,path='/api/state'):
    with urlopen(f'http://127.0.0.1:{port}{path}',timeout=2) as r:return json.load(r)


def post(port,path,obj,header='X-Lab-Control-Token',token=TOKEN):
    req=Request(f'http://127.0.0.1:{port}{path}',data=json.dumps(obj).encode(),method='POST',
        headers={'Content-Type':'application/json',header:token} if token else {'Content-Type':'application/json'})
    with urlopen(req,timeout=3) as r:return json.load(r)


def wait(fn,seconds=25):
    end=time.monotonic()+seconds;error=None
    while time.monotonic()<end:
        try:
            value=fn()
            if value:return value
        except (OSError,ValueError,KeyError,AssertionError) as e:error=e
        time.sleep(.4)
    raise AssertionError(f'Check failed: {fn}: {error}')


class HistorianStub(BaseHTTPRequestHandler):
    def do_GET(self):
        ts=time.time()-10
        sample={'time':ts,'generation_kw':5000,'export_kw':4900,'irradiance_w_m2':880,
                'online_inverters':4,'alarm_count':0,'secret_control_token':'DO_NOT_PUBLISH',
                'controller_ip':'192.168.95.21'}
        payload={'sample':sample} if '/latest' in self.path else {'samples':[sample]*4}
        body=json.dumps(payload).encode()
        self.send_response(200);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def log_message(self,*_):pass


def main():
    with tempfile.TemporaryDirectory(prefix='solaris-v6-smoke-') as directory:
        state_file=Path(directory)/'pv_state.json'
        run('solar_weather.py',22100)
        run('solar_array.py',22101,{'ASSET_ID':'PV-02','WEATHER_URL':'http://127.0.0.1:22100',
            'CONTROL_TOKEN':TOKEN,'SOILING_PCT':'9','FAILED_STRINGS':'2','STATE_FILE':str(state_file)})
        run('solar_inverter.py',22102,{'ASSET_ID':'INV-02','ARRAY_ID':'PV-02',
            'FIELD_URL':'http://127.0.0.1:22101','MODBUS_PORT':'22103','CONTROL_TOKEN':TOKEN})
        run('http_relay.py',22104,{'TARGET_URL':'http://127.0.0.1:22102',
            'ALLOWED_PATHS':'/api/state,/api/limit', 'ALLOWED_METHODS':'GET,POST',
            'CONDUIT_AUTH_TOKEN':TOKEN,'CONDUIT_AUTH_HEADER':'X-PPC-Token'})
        run('solar_field_service.py',22105,{'FIELD_ASSETS':'PV-02=http://127.0.0.1:22101',
            'CONTROL_TOKEN':TOKEN,'FIELD_DB':str(Path(directory)/'field.sqlite3')})
        pv=wait(lambda: (s if (s:=get(22101)).get('connected') else None))
        before=pv['dc_kw']
        wait(lambda:get(22102) if get(22102)['connected'] else None)
        try:
            post(22104,'/api/limit',{'limit_pct':20},header='X-PPC-Token',token='wrong')
            raise AssertionError('conduit accepted bad credentials')
        except HTTPError as e:assert e.code==403
        assert post(22104,'/api/limit',{'limit_pct':20},header='X-PPC-Token')['limit_pct']==20
        assert wait(lambda:get(22102) if get(22102)['limit_pct']==20 else None)
        assert get(22104)['device']=='INV-02'
        print('[PASS] cross-zone relay GET + authenticated POST; wrong token rejected')
        try:
            post(22105,'/api/service',{'asset':'PV-02','action':'clean','operator':'tech-01'},token='wrong')
            raise AssertionError('field service accepted bad credentials')
        except HTTPError as e:assert e.code==403
        post(22105,'/api/service',{'asset':'PV-02','action':'clean','operator':'tech-01'})
        post(22105,'/api/service',{'asset':'PV-02','action':'repair_strings','operator':'tech-01'})
        post(22104,'/api/limit',{'limit_pct':100},header='X-PPC-Token')
        repaired=wait(lambda: (s if (s:=get(22101)).get('failed_strings')==0 and s['soiling_pct']<1 and s['dc_kw']>before+50 else None))
        inv=wait(lambda: (s if (s:=get(22102)).get('limit_pct')==100 and s['active_kw']>before*.9 else None))
        assert state_file.exists() and len(get(22105,'/api/repairs')['repairs'])==2
        print('[PASS] field technician: repair updates PV output, inverter generation, persistent device state and audit')
        stub=ThreadingHTTPServer(('127.0.0.1',22106),HistorianStub)
        thread=threading.Thread(target=stub.serve_forever,daemon=True);thread.start()
        try:
            run('solar_public.py',22107,{'HISTORIAN_URL':'http://127.0.0.1:22106',
                'PUBLIC_POLL_SECONDS':'10','PUBLIC_DB':str(Path(directory)/'public.sqlite3'),
                'PUBLIC_SALT':'smoke-only-salt','PUBLIC_ADMIN_TOKEN':'smoke-only-admin'})
            pub=wait(lambda: (p if (p:=get(22107,'/api/public')).get('online') else None))
            assert pub['export_mw']==4.9 and pub['generation_mw']==5
            assert 'secret_control_token' not in pub and 'controller_ip' not in pub
            hist=get(22107,'/api/public/history')
            assert len(hist['samples'])==4 and all('controller_ip' not in x for x in hist['samples'])
            print('[PASS] historian -> sanitized public publisher; no internal addresses or credentials exposed')
        finally:
            stub.shutdown();stub.server_close()
    print('[PASS] SOLARIS ONE v6 independent functional extensions')

if __name__=='__main__':
    try:main()
    finally:
        for p in reversed(processes):
            if p.poll() is None:p.terminate()
        for p in reversed(processes):
            try:p.wait(timeout=3)
            except subprocess.TimeoutExpired:p.kill();p.wait(timeout=2)
