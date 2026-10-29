"""Level 2 solar SCADA: live plant telemetry and token-gated operator dispatch."""
import json,os,threading,time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request,urlopen
from common import JSONHandler,read_json,send_json
PPC=os.getenv('PPC_URL','http://ppc-01:8080')
TOKEN=os.getenv('CONTROL_TOKEN','')
HTML=Path(__file__).with_name('solar_ui').joinpath('index.html').read_bytes()
ASSETS_HTML=Path(__file__).with_name('solar_ui').joinpath('assets.html').read_bytes()
lock=threading.RLock()
latest={'device':'SCADA-01','connected':False,'plant':'SOLARIS ONE','error':'Starting PPC polling',
        'generation_kw':0,'export_kw':0,'inverters':{},'arrays':{},'feeder':{},'alarms':[]}
def poll():
    while True:
        try:
            with urlopen(PPC+'/api/state',timeout=5) as r:sample=json.load(r)
            with lock:latest.clear();latest.update(sample);latest['source']='SCADA-01';latest['scada_time']=time.time()
        except (OSError,ValueError,TimeoutError):
            with lock:latest['connected']=False;latest['error']='PPC communication unavailable'
        time.sleep(2)
class Handler(JSONHandler):
    def do_GET(self):
        if self.path in ('/','/index.html'):
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(HTML)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(HTML)
        elif self.path.startswith('/assets') and self.path.split('?',1)[0] in ('/assets','/assets/'):
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(ASSETS_HTML)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(ASSETS_HTML)
        elif self.path=='/api/state':
            with lock:sample=dict(latest)
            send_json(self,200,sample)
        elif self.path=='/health':
            with lock:online=latest.get('connected',False)
            send_json(self,200 if online else 503,{'ok':online})
        else:send_json(self,404,{'error':'not_found'})
    def do_POST(self):
        if self.path!='/api/control':return send_json(self,404,{'error':'not_found'})
        if not TOKEN or self.headers.get('X-Lab-Control-Token')!=TOKEN:return send_json(self,403,{'error':'operator_token_required'})
        try:
            obj=read_json(self)
            if not isinstance(obj,dict) or not obj or set(obj)-{'export_limit_pct','breaker_closed','relay_action'}:
                raise ValueError('invalid command')
            if 'export_limit_pct' in obj and (type(obj['export_limit_pct']) not in (float,int) or not 0<=obj['export_limit_pct']<=100):
                raise ValueError('invalid limit')
            if 'breaker_closed' in obj and type(obj['breaker_closed']) is not bool:
                raise ValueError('invalid breaker')
            if 'relay_action' in obj and (obj['relay_action'] not in ('test_trip','reset_trip') or len(obj)!=1):
                raise ValueError('invalid relay action')
            req=Request(PPC+'/api/dispatch',data=json.dumps(obj).encode(),method='POST',headers={'Content-Type':'application/json','X-PPC-Token':TOKEN})
            with urlopen(req,timeout=5) as resp:result=json.load(resp)
            send_json(self,200,result)
        except (OSError,ValueError,TimeoutError):send_json(self,503,{'error':'dispatch_failed_or_invalid'})
if __name__=='__main__':
    threading.Thread(target=poll,daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','8080'))),Handler).serve_forever()
