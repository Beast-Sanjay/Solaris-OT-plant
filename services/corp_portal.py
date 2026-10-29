"""Corporate L4 maintenance operations: real PostgreSQL, AD-authenticated workflow.

Live work orders are inserted by the AD-authenticated maintenance bot.
Operations staff approve/close orders and leave an audit record. Closing an order
records administrative completion: physical field repair is performed separately
via the isolated L0 technician console. Lab credentials over HTTP, loopback only.
"""
import base64
import json
import os
import ssl
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
import psycopg
from common import JSONHandler, send_json, read_json


def connect():
    return psycopg.connect(host=os.getenv('DB_HOST','db01'),user=os.getenv('DB_USER','otlab'),
        password=os.environ['DB_PASSWORD'],dbname=os.getenv('DB_NAME','corporate'),connect_timeout=4)


def get_orders():
    with connect() as db:
        with db.cursor() as cur:
            cur.execute('SELECT reference,title,status,created_at::text FROM work_orders ORDER BY id DESC LIMIT 250')
            return [dict(zip(('reference','title','status','created_at'),r)) for r in cur.fetchall()]


def get_audit():
    with connect() as db:
        with db.cursor() as cur:
            cur.execute('SELECT reference,actor,old_status,new_status,note,changed_at::text FROM work_order_events ORDER BY id DESC LIMIT 40')
            return [dict(zip(('reference','actor','old_status','new_status','note','changed_at'),r)) for r in cur.fetchall()]


def verify_ad(header):
    try:
        if not header.startswith('Basic '):return None
        user,secret=base64.b64decode(header[6:],validate=True).decode().split(':',1)
        if not 1<=len(user)<=80 or not all(c.isalnum() or c in '._-' for c in user) or not secret:return None
        from ldap3 import Connection, Server, SIMPLE, Tls
        conn=Connection(Server(os.getenv('AD_HOST','dc01'),port=636,use_ssl=True,
            tls=Tls(validate=ssl.CERT_NONE),connect_timeout=3),
            user=f'{user}@{os.getenv("AD_DOMAIN","corp.otlab.test")}',password=secret,
            authentication=SIMPLE,auto_bind=True,receive_timeout=4)
        ok=conn.bound
        conn.unbind()
        return user if ok else None
    except Exception:return None


def transition(reference,status,actor,note):
    if not isinstance(reference,str) or not 1<=len(reference)<=90 or not all(c.isalnum() or c in '-_' for c in reference):
        raise ValueError('invalid reference')
    if not isinstance(note,str) or len(note)>300:raise ValueError('invalid note')
    with connect() as db:
        with db.cursor() as cur:
            cur.execute('SELECT status FROM work_orders WHERE reference=%s FOR UPDATE',(reference,))
            row=cur.fetchone()
            if row is None:raise LookupError('not found')
            old=row[0]
            if (old,status) not in (('planned','approved'),('approved','closed')):
                raise ValueError('invalid_transition')
            cur.execute('UPDATE work_orders SET status=%s WHERE reference=%s',(status,reference))
            cur.execute('INSERT INTO work_order_events(reference,actor,old_status,new_status,note) VALUES (%s,%s,%s,%s,%s)',
                        (reference,actor,old,status,note))
        return {'ok':True,'reference':reference,'old_status':old,'status':status,'actor':actor}


HTML='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SOLARIS ONE · Maintenance Center</title><style>*{box-sizing:border-box}body{background:#091b29;color:#eaf5fa;margin:0;font:14px system-ui}header{padding:24px 6vw;border-bottom:1px solid #355264;display:flex;justify-content:space-between}header b{font-size:20px;letter-spacing:.13em}header small{color:#d1eb84}main{max-width:1240px;margin:40px auto;padding:0 20px}h1{font-size:36px;margin:5px 0}.muted{color:#aac0ce}.panel{background:#102837;border:1px solid #315167;border-radius:15px;padding:22px;margin:15px 0;overflow:auto}table{border-collapse:collapse;width:100%}td,th{padding:15px;text-align:left;border-bottom:1px solid #335166}th{color:#9abcc8;text-transform:uppercase;font-size:11px}input{background:#071825;color:white;border:1px solid #537383;border-radius:7px;padding:11px;margin:5px;max-width:270px}button{background:#cfe979;border:0;padding:9px 14px;border-radius:7px;cursor:pointer;font-weight:700;margin:3px}button:disabled{opacity:.3;cursor:default}.state{color:#d7f08d}.muted2{font-size:12px;color:#91aebd}#msg{min-height:24px;color:#cfe979}</style><header><b>☀ SOLARIS ONE</b><small>ENTERPRISE MAINTENANCE · PURDUE L4</small></header><main><div class="muted">AD authenticated actions / PostgreSQL persisted</div><h1>Asset maintenance operations</h1><p class="muted">Faults discovered from the plant historian create work orders. Corporate staff approve and close them after field verification; no commands are sent to PV devices from this portal.</p><section class="panel"><h2>Corporate AD sign-in for changes</h2><input id="user" placeholder="CORP username" value="analyst" autocomplete="username"><input id="pass" placeholder="AD password" type="password" autocomplete="current-password"><input id="note" placeholder="Change note (optional)"><p id="msg" aria-live="polite"></p></section><section class="panel"><h2>Live PostgreSQL work orders</h2><table><thead><tr><th>Reference</th><th>Maintenance job</th><th>Status</th><th>Actions</th></tr></thead><tbody id="orders"></tbody></table></section><section class="panel"><h2>Recent approvals and completions</h2><table><thead><tr><th>Reference</th><th>Actor</th><th>Change</th><th>Time</th></tr></thead><tbody id="audit"></tbody></table></section><p class="muted2">Corporate IT / CORP.OTLAB.TEST · Simulated plant data · Train on isolated loopback only</p></main><script>const $=id=>document.getElementById(id);async function reload(){try{let data=await(await fetch('/api/workorders',{cache:'no-store'})).json();$('orders').replaceChildren();for(let item of data.orders){let tr=document.createElement('tr');for(let key of ['reference','title','status']){let td=document.createElement('td');td.textContent=item[key];tr.append(td)}let act=document.createElement('td');let b=document.createElement('button');b.textContent=item.status==='planned'?'Approve':item.status==='approved'?'Close':'Completed';b.disabled=item.status==='closed';b.onclick=()=>change(item.reference,item.status==='planned'?'approved':'closed');act.append(b);tr.append(act);$('orders').append(tr)}let history=await(await fetch('/api/workorders/audit',{cache:'no-store'})).json();$('audit').replaceChildren();for(let event of history.events){let tr=document.createElement('tr');for(let value of [event.reference,event.actor,event.old_status+' → '+event.new_status,event.changed_at]){let td=document.createElement('td');td.textContent=value;tr.append(td)}$('audit').append(tr)}}catch(e){$('msg').textContent='Database not reachable: '+e}}async function change(ref,status){try{let r=await fetch('/api/workorders/status',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Basic '+btoa($('user').value+':'+$('pass').value)},body:JSON.stringify({reference:ref,status,note:$('note').value})});let d=await r.json();$('msg').textContent=r.ok?ref+' updated to '+status:'Change denied: '+(d.error||r.status);await reload()}catch(e){$('msg').textContent=e.message}}reload();setInterval(reload,12000);</script></html>'''.encode()

class Handler(JSONHandler):
    def do_GET(self):
        route=urlsplit(self.path).path
        if route in ('/','/index.html'):
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(HTML)));self.end_headers();self.wfile.write(HTML);return
        if route not in ('/api/workorders','/api/workorders/audit','/health'):
            return send_json(self,404,{'error':'not_found'})
        try:
            if route=='/health':return send_json(self,200,{'ok':True,'db':'db01','orders':len(get_orders())})
            if route=='/api/workorders/audit':return send_json(self,200,{'events':get_audit()})
            return send_json(self,200,{'orders':get_orders(),'database':'db01'})
        except (psycopg.Error,OSError):return send_json(self,503,{'error':'db01_unavailable'})
    def do_POST(self):
        if self.path!='/api/workorders/status':return send_json(self,404,{'error':'not_found'})
        user=verify_ad(self.headers.get('Authorization',''))
        if not user:return send_json(self,401,{'error':'corporate_ad_credentials_required'})
        try:
            obj=read_json(self)
            if not isinstance(obj,dict) or set(obj)-{'reference','status','note'}:raise ValueError()
            return send_json(self,200,transition(obj['reference'],obj['status'],user,obj.get('note','')))
        except LookupError:return send_json(self,404,{'error':'work_order_not_found'})
        except (ValueError,TypeError,KeyError):return send_json(self,409,{'error':'invalid_work_order_transition'})
        except (psycopg.Error,OSError):return send_json(self,503,{'error':'db01_unavailable'})

if __name__=='__main__':
    ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','8080'))),Handler).serve_forever()
