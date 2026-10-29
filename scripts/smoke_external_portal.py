#!/usr/bin/env python3
"""Live HTTP smoke test of a local portal subprocess with simulated historian.

No Docker / AD required. Tests actual HTTP API persistence, access enforcement,
energy integration and public request-tracking. Does not simulate real AD join.
"""
import json
import os
import socket
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1]

def free_port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]

class Historian(BaseHTTPRequestHandler):
    def do_GET(self):
        t=int(time.time())
        sample={'time':t,'generation_kw':9000,'export_kw':8000,'online_inverters':4,
                'irradiance_w_m2':950,'alarm_count':0,'private_address':'192.168.95.21'}
        obj={'sample':sample} if self.path.endswith('/latest') else {'samples':[sample]}
        b=json.dumps(obj).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)))
        self.end_headers();self.wfile.write(b)
    def log_message(self,*a):pass

def call(url,method='GET',data=None,token=None):
    headers={}
    if data is not None:headers['Content-Type']='application/json'
    if token:headers['X-Public-Admin-Token']=token
    req=Request(url,data=json.dumps(data).encode() if data is not None else None,
                 method=method,headers=headers)
    try:
        with urlopen(req,timeout=4) as resp:return resp.status,json.load(resp)
    except HTTPError as exc:
        return exc.code,json.load(exc)

def main():
    fake=ThreadingHTTPServer(('127.0.0.1',free_port()),Historian)
    t=threading.Thread(target=fake.serve_forever,daemon=True);t.start()
    port=free_port();addr=f'http://127.0.0.1:{port}';token='not-for-production-'+os.urandom(8).hex()
    with tempfile.TemporaryDirectory() as folder:
        env={**os.environ,'PORT':str(port),'PUBLIC_ADMIN_TOKEN':token,'PUBLIC_SALT':'smoke-salt',
             'PUBLIC_DB':str(Path(folder)/'public.sqlite3'),'PUBLIC_POLL_SECONDS':'10',
             'HISTORIAN_URL':f'http://127.0.0.1:{fake.server_address[1]}'}
        with subprocess.Popen([sys.executable,'-u',str(ROOT/'services/solar_public.py')],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT) as proc:
            try:
                for _ in range(60):
                    try:
                        status,plant=call(addr+'/api/public')
                        if status==200 and plant['online']:break
                    except (OSError,TimeoutError):pass
                    time.sleep(.1)
                else:raise RuntimeError('public historian connection not ready')
                assert plant['export_mw']==8 and 'private_address' not in plant
                assert call(addr+'/api/public/statistics')[0]==200
                assert call(addr+'/api/public/history')[1]['samples']
                assert call(addr+'/api/internal/enquiries')[0]==403
                assert call(addr+'/api/control')[0]==404
                ticket=call(addr+'/api/enquiries','POST',{'full_name':'Visitor Example','email':'visitor@example.com',
                    'category':'site_visit','message':'Please schedule a simulated technical visit.'})
                assert ticket[0]==201,ticket
                ref=ticket[1]['reference'];code=ticket[1]['access_code']
                assert call(addr+'/api/enquiries/track','POST',{'reference':ref,'access_code':'fake'})[0]==404
                assert call(addr+'/api/enquiries/track','POST',{'reference':ref,'access_code':code})[1]['status']=='received'
                r=call(addr+'/api/internal/enquiries',token=token)
                assert r[0]==200 and r[1]['enquiries'][0]['reference']==ref,r
                assert call(addr+'/api/internal/enquiries/update','POST',{'reference':ref,'status':'under_review'},token)[0]==200
                assert call(addr+'/api/internal/enquiries/update','POST',{'reference':ref,'status':'responded',
                         'response':'Virtual visitor session is available.'},token)[0]==200
                tracked=call(addr+'/api/enquiries/track','POST',{'reference':ref,'access_code':code})[1]
                assert tracked['status']=='responded' and 'Virtual visitor' in tracked['response']
                notice=call(addr+'/api/internal/announcements','POST',{'title':'Public plant notice',
                    'message':'This solar plant is a synthetic training installation.','severity':'information'},token)
                assert notice[0]==201,notice
                assert call(addr+'/api/public/notices')[1]['notices'][0]['title']=='Public plant notice'
                assert call(addr+'/api/internal/announcements/close','POST',{'id':notice[1]['id']},token)[0]==200
                assert not call(addr+'/api/public/notices')[1]['notices']
                # Exercise an actual authenticated IDMZ conduit (not merely the policy helper).
                relay_port=free_port()
                relay_env={**os.environ,'TARGET_URL':addr,'LISTEN_PORT':str(relay_port),
                    'ALLOWED_PATHS':'/api/internal/enquiries,/api/internal/enquiries/update,/api/public/notices',
                    'ALLOWED_METHODS':'GET,POST','CONDUIT_AUTH_TOKEN':token,
                    'CONDUIT_AUTH_HEADER':'X-Public-Admin-Token',
                    'CONDUIT_REQUIRE_AUTH_GET':'true','CONDUIT_MAX_RESPONSE_BYTES':'300000'}
                with subprocess.Popen([sys.executable,'-u',str(ROOT/'services/http_relay.py')],
                                      env=relay_env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT) as relay:
                    try:
                        relay_addr=f'http://127.0.0.1:{relay_port}'
                        for _ in range(40):
                            try:
                                if call(relay_addr+'/api/internal/enquiries')[0]==403:break
                            except (OSError,TimeoutError):pass
                            time.sleep(.1)
                        else:raise RuntimeError('relay not ready')
                        assert call(relay_addr+'/api/internal/enquiries',token=token)[0]==200
                        assert call(relay_addr+'/api/internal/enquiries/update','POST',
                                    {'reference':ref,'status':'closed'},token)[0]==200
                        assert call(relay_addr+'/api/control',token=token)[0]==403
                        print('[PASS] Live IDMZ service relay permits token-gated staff only')
                    finally:
                        relay.terminate();relay.communicate(timeout=5)
                if shutil.which('nginx'):
                    site_port=free_port()
                    source=(ROOT/'docs/web/nginx.conf').read_text()
                    site_root=ROOT/'docs/web'
                    conf=source.replace('listen 80;',f'listen 127.0.0.1:{site_port};')
                    conf=conf.replace('root /usr/share/nginx/html;',f'root {site_root};')
                    conf=conf.replace('http://public-publisher:8080',addr)
                    serverconf=Path(folder)/'site.conf';serverconf.write_text(conf)
                    wrapper=Path(folder)/'nginx.conf'
                    wrapper.write_text(f'pid {folder}/nginx.pid; events {{}} http {{ include {serverconf}; }}')
                    subprocess.run(['nginx','-t','-c',str(wrapper)],check=True,
                                   stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
                    with subprocess.Popen(['nginx','-c',str(wrapper),'-g','daemon off;'],
                                          stdout=subprocess.PIPE,stderr=subprocess.PIPE) as nginx:
                        try:
                            base=f'http://127.0.0.1:{site_port}'
                            for _ in range(30):
                                try:
                                    with urlopen(base+'/',timeout=2) as r:
                                        if r.status==200:break
                                except OSError:pass
                                time.sleep(.1)
                            else:raise RuntimeError('Nginx did not start')
                            for static in ('/','/style.css','/app.js'):
                                with urlopen(base+static,timeout=3) as r:assert r.status==200
                            assert call(base+'/api/public')[1]['generation_mw']==9
                            assert call(base+'/api/enquiries','POST',{'full_name':'Second Visitor',
                                'email':'second@example.com','category':'general',
                                'message':'I would like to know about public data.'})[0]==201
                            for forbidden in ('/api/internal/enquiries','/api/control','/api/devices/latest'):
                                try:urlopen(base+forbidden,timeout=2)
                                except HTTPError as err:assert err.code==404,(forbidden,err.code)
                                else:raise AssertionError('public path should be blocked: '+forbidden)
                            print('[PASS] Actual Nginx serves web app, forwards safe APIs, blocks OT/internal routes')
                        finally:
                            nginx.terminate();nginx.communicate(timeout=5)
                print('[PASS] Historian -> sanitized public live power and history')
                print('[PASS] Public analytics endpoint')
                print('[PASS] Enquiry -> persistent case -> private tracking -> staff response')
                print('[PASS] Public notice publish + archive via secret staff API')
                print('[PASS] Anonymous internal access denied and no OT control endpoint')
            finally:
                proc.terminate()
                try:proc.communicate(timeout=6)
                except subprocess.TimeoutExpired:proc.kill();proc.communicate()
                fake.shutdown();fake.server_close()
if __name__=='__main__':main()
