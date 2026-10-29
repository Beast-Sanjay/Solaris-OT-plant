"""L3 dispatch order receiving point.  The L2 PPC reads orders only through a GET-only conduit.
This emulates a grid operator's export ceiling, not an external grid connection.
"""
import os,time,threading
from http.server import ThreadingHTTPServer
from common import JSONHandler,read_json,send_json
TOKEN=os.getenv('CONTROL_TOKEN','')
lock=threading.RLock()
state={'device':'GRID-ORDER-01','connected':True,'order_id':'SCHEDULE-0001',
       'export_limit_pct':100.0,'source':'day_ahead_schedule','received_at':time.time(),
       'valid_until':None,'status':'ACTIVE'}
def apply_order(limit,order_id):
    if type(limit) not in (int,float) or not 0<=limit<=100:raise ValueError('bad_limit')
    if not isinstance(order_id,str) or not 1<=len(order_id)<=48 or not all(c.isalnum() or c in '-_' for c in order_id):raise ValueError('bad_id')
    with lock:
        state.update(export_limit_pct=float(limit),order_id=order_id,received_at=time.time(),source='operator_grid_dispatch')
        return dict(state)
HTML='''<!DOCTYPE html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SOLARIS ONE / Grid Dispatch</title><style>body{background:#0b1520;color:#edf7f7;font:16px system-ui;margin:0}header{padding:24px 5vw;border-bottom:1px solid #2b444b;color:#cee97b;font-weight:800;letter-spacing:.13em}main{max-width:760px;margin:54px auto;padding:0 24px}section{padding:28px;border:1px solid #2f5051;background:#142936;border-radius:16px}h1{font-size:31px}small,p{color:#a3baba}input{background:#081922;color:#fff;border:1px solid #43636a;padding:12px;border-radius:8px;margin:8px 0;width:100%}button{border:0;border-radius:9px;padding:13px 19px;background:#c9ee6a;color:#111b1f;font-weight:800;cursor:pointer}output{color:#cbec89;font-size:25px}footer{margin-top:25px;font-size:12px;color:#9ab1b7}</style><header>☀ SOLARIS ONE &nbsp; / &nbsp; GRID SCHEDULING</header><main><p>OT OPERATIONS · PURDUE LEVEL 3</p><h1>Grid export instructions</h1><section><p>Active order: <b id="oid">...</b></p><output id="limit">—</output><p>Export limit takes precedence over the local PPC operator setpoint.</p><label>Grid order ID</label><input id="order" value="GRID-MANUAL-001"><label>Permitted plant export limit (%)</label><input id="cap" type="number" min="0" max="100" value="80"><label>Training control token</label><input id="token" type="password" autocomplete="off" placeholder="CONTROL_TOKEN from .env"><button id="apply">Send grid order</button><p id="msg"></p></section><footer>Simulated utility dispatch only. No actual grid-control communications.</footer></main><script>async function reload(){try{let d=await (await fetch('/api/state')).json();document.getElementById('oid').textContent=d.order_id;document.getElementById('limit').textContent=d.export_limit_pct+'%';}catch(e){}}document.getElementById('apply').onclick=async()=>{let d={order_id:document.getElementById('order').value,export_limit_pct:Number(document.getElementById('cap').value)};try{let r=await fetch('/api/order',{method:'POST',headers:{'Content-Type':'application/json','X-Grid-Token':document.getElementById('token').value},body:JSON.stringify(d)});if(!r.ok)throw Error('HTTP '+r.status);document.getElementById('msg').textContent='Order accepted by simulator';reload()}catch(e){document.getElementById('msg').textContent='Rejected: '+e.message}};reload();setInterval(reload,4000);</script></html>'''.encode('utf-8')
class Handler(JSONHandler):
    def do_GET(self):
        if self.path in ('/','/index.html'):
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(HTML)));self.end_headers();self.wfile.write(HTML);return
        if self.path in ('/api/state','/health'):
            with lock:s=dict(state)
            return send_json(self,200,s)
        send_json(self,404,{'error':'not_found'})
    def do_POST(self):
        if self.path!='/api/order':return send_json(self,404,{'error':'not_found'})
        if not TOKEN or self.headers.get('X-Grid-Token')!=TOKEN:return send_json(self,403,{'error':'token_required'})
        try:
            obj=read_json(self)
            return send_json(self,200,apply_order(obj['export_limit_pct'],obj['order_id']))
        except (ValueError,TypeError,KeyError):return send_json(self,400,{'error':'invalid_order'})
if __name__=='__main__':ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','8080'))),Handler).serve_forever()
