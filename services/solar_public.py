"""SOLARIS ONE public portal: historian-only aggregate reporting + persistent enquiries.

No OT command routes. Public endpoints have an explicit allowlist; staff routes
require a separate secret and are NOT exposed by public Nginx. Operations staff
also authenticate via corporate AD to the Level-4 review portal.
"""
import hashlib
from contextlib import contextmanager
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
from urllib.request import urlopen
from common import JSONHandler, read_json, send_json

HIST = os.getenv('HISTORIAN_URL', 'http://historian-conduit:8080')
INTERVAL = max(10, int(os.getenv('PUBLIC_POLL_SECONDS', '30')))
DB = os.getenv('PUBLIC_DB', '/data/public.sqlite3')
ADMIN_TOKEN = os.getenv('PUBLIC_ADMIN_TOKEN', '')
PUBLIC_SALT = os.getenv('PUBLIC_SALT', '')
lock = threading.RLock()
public = {'plant': 'SOLARIS ONE', 'simulation': True, 'online': False,
          'capacity_mw': 10, 'source': 'sanitized_historian', 'updated_at': None,
          'generation_mw': 0, 'export_mw': 0, 'irradiance_w_m2': 0,
          'estimated_co2_avoided_kg_h': 0, 'inverters_online': 0,
          'status': 'WAITING_FOR_HISTORIAN'}
history = []
TYPES = {'site_visit', 'partnership', 'data_request', 'general'}
STATES = {'received', 'under_review', 'responded', 'closed'}
EMAIL_RE = re.compile(r'^[^\s@]{1,64}@[^\s@]{1,190}\.[a-zA-Z]{2,30}$')
REF_RE = re.compile(r'^SOL-[A-Z0-9]{12}$')


@contextmanager
def connect():
    db = sqlite3.connect(DB, timeout=15)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('''CREATE TABLE IF NOT EXISTS enquiries (
      reference TEXT PRIMARY KEY, access_hash TEXT NOT NULL, full_name TEXT NOT NULL,
      email TEXT NOT NULL, category TEXT NOT NULL, message TEXT NOT NULL,
      status TEXT NOT NULL, response TEXT NOT NULL DEFAULT '',
      ip_hash TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS notices (
      id INTEGER PRIMARY KEY, title TEXT NOT NULL, message TEXT NOT NULL,
      severity TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS telemetry (
      sampled_at INTEGER PRIMARY KEY, generation_mw REAL NOT NULL,
      export_mw REAL NOT NULL, irradiation REAL NOT NULL)''')
    try:
        with db:
            yield db
    finally:
        db.close()


def initialize():
    with connect() as db:
        db.execute("DELETE FROM enquiries WHERE created_at < ?", (time.time()-90*86400,))
        db.execute("DELETE FROM telemetry WHERE sampled_at < ?", (time.time()-7*86400,))


def sanitize(sample):
    """An allowlist of aggregate scalar values only (no asset IPs, OT metadata)."""
    def number(key, hi):
        v = float(sample.get(key) or 0)
        if not 0 <= v <= hi * 2:  # Reject invalid and implausible readings.
            raise ValueError('out_of_bounds')
        return round(min(hi, v), 2)
    generation = number('generation_kw', 10000)
    export = number('export_kw', 10000)
    return {'time': float(sample['time']), 'generation_mw': round(generation/1000, 3),
            'export_mw': round(min(export, generation)/1000, 3),
            'irradiance_w_m2': number('irradiance_w_m2', 1300),
            'inverters_online': min(4, max(0, int(sample.get('online_inverters', 0)))),
            'estimated_co2_avoided_kg_h': round(min(export, generation)*0.7, 1),
            'status': 'NORMAL' if not sample.get('alarm_count') else 'PERFORMANCE_REVIEW'}


def update_from_historian(latest, rows, now=None):
    if not latest or not latest.get('time'):
        raise ValueError('no historian data')
    now = now or time.time()
    value = sanitize(latest)
    if now - value['time'] > 120 or value['time'] > now + 30:
        raise ValueError('historian data stale')
    snapshots = [sanitize(row) for row in reversed(rows[:180]) if row.get('time')]
    with lock:
        with connect() as db:
            # Store a sampled snapshot in the DMZ, not the entire internal historian.
            db.execute('INSERT OR REPLACE INTO telemetry VALUES (?,?,?,?)',
                       (int(value['time']), value['generation_mw'], value['export_mw'], value['irradiance_w_m2']))
            db.execute('DELETE FROM telemetry WHERE sampled_at < ?', (now-7*86400,))
        public.update(value, online=True, updated_at=now)
        history[:] = snapshots


def public_statistics(now=None):
    """Observed exported energy; skips telemetry gaps instead of inventing energy."""
    now = now or time.time()
    midnight = datetime.fromtimestamp(now, timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    with connect() as db:
        samples = db.execute('SELECT sampled_at,export_mw,generation_mw FROM telemetry WHERE sampled_at >= ? ORDER BY sampled_at',
                             (midnight-INTERVAL*2,)).fetchall()
    energy = 0.0
    duration = 0
    peak = 0.0
    for i, (t, export, generation) in enumerate(samples):
        if t >= midnight: peak = max(peak, export)
        if i:
            prev_t, prev_export, _ = samples[i-1]
            # Exclude unobserved intervals (plus possible pre-midnight sample).
            if t > midnight and 0 < t-prev_t <= INTERVAL*3:
                seconds = t-max(prev_t, midnight)
                energy += (prev_export+export)/2 * seconds/3600
                duration += seconds
    return {'simulation':True, 'energy_today_mwh':round(energy,3),
            'observed_minutes':round(duration/60,1), 'peak_export_mw':round(peak,3),
            'period_start_utc':datetime.fromtimestamp(midnight, timezone.utc).isoformat(),
            'method':'trapezoidal sampled feeder export; missing intervals excluded',
            'is_estimate':True}


def enquiries_submit(data, ip='local', now=None):
    now = now or time.time()
    if not isinstance(data,dict) or set(data)-{'full_name','email','category','message','website'}:
        raise ValueError('invalid_fields')
    if data.get('website'):raise ValueError('honeypot_triggered')
    name = str(data.get('full_name','')).strip()
    email = str(data.get('email','')).strip().lower()
    category = data.get('category')
    message = str(data.get('message','')).strip()
    if not 2 <= len(name) <= 100 or any(ord(c)<32 for c in name):raise ValueError('invalid_name')
    if not EMAIL_RE.fullmatch(email):raise ValueError('invalid_email')
    if category not in TYPES:raise ValueError('invalid_category')
    if not 10 <= len(message) <= 1200 or any(ord(c)<32 and c not in '\n\t' for c in message):
        raise ValueError('invalid_message')
    iphash = hashlib.sha256((PUBLIC_SALT + str(ip)[:120]).encode()).hexdigest()
    ref = 'SOL-' + secrets.token_hex(6).upper()
    code = secrets.token_urlsafe(18)
    digest = hashlib.sha256(code.encode()).hexdigest()
    with lock:
        with connect() as db:
            if db.execute('SELECT count(*) FROM enquiries WHERE ip_hash=? AND created_at>?',
                          (iphash, now-3600)).fetchone()[0] >= 5:
                raise RuntimeError('rate_limited')
            db.execute('INSERT INTO enquiries(reference,access_hash,full_name,email,category,message,status,ip_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                       (ref,digest,name,email,category,message,'received',iphash,now,now))
    return {'ok':True,'reference':ref,'access_code':code,'status':'received',
            'note':'Save your tracking details; no email is sent by this demonstration lab.'}


def track_enquiry(reference, code):
    if not isinstance(reference,str) or not REF_RE.fullmatch(reference) or not isinstance(code,str) or not 10<=len(code)<=80:
        return None
    with connect() as db:
        row = db.execute('SELECT access_hash,status,response,created_at,updated_at FROM enquiries WHERE reference=?',(reference,)).fetchone()
    if not row or not hmac.compare_digest(row[0],hashlib.sha256(code.encode()).hexdigest()):return None
    return {'reference':reference,'status':row[1],'response':row[2] if row[1] in ('responded','closed') else '',
            'created_at':row[3], 'updated_at':row[4]}


def public_notices():
    with connect() as db:
        rows = db.execute('SELECT id,title,message,severity,created_at FROM notices WHERE active=1 ORDER BY id DESC LIMIT 20').fetchall()
    return [{'id':r[0],'title':r[1],'message':r[2],'severity':r[3],'created_at':r[4]} for r in rows]


def staff_list():
    with connect() as db:
        rows = db.execute('SELECT reference,full_name,email,category,message,status,response,created_at,updated_at FROM enquiries ORDER BY created_at DESC LIMIT 200').fetchall()
    keys = ['reference','full_name','email','category','message','status','response','created_at','updated_at']
    return [dict(zip(keys,r)) for r in rows]


def staff_update(payload, now=None):
    now=now or time.time()
    ref=payload.get('reference');status=payload.get('status');response=payload.get('response','')
    if not isinstance(ref,str) or not REF_RE.fullmatch(ref) or status not in STATES or not isinstance(response,str) or len(response)>1200:
        raise ValueError('invalid_update')
    with lock:
        with connect() as db:
            existing=db.execute('SELECT status FROM enquiries WHERE reference=?',(ref,)).fetchone()
            if not existing:raise LookupError('case_not_found')
            if (existing[0],status) not in {('received','under_review'),('under_review','responded'),('responded','closed'),('under_review','closed')}:
                raise ValueError('invalid_transition')
            if status=='responded' and not response.strip():raise ValueError('response_required')
            db.execute('UPDATE enquiries SET status=?,response=?,updated_at=? WHERE reference=?',(status,response,now,ref))
    return {'ok':True,'reference':ref,'status':status}


def staff_notice(payload, now=None):
    now=now or time.time()
    title=payload.get('title');msg=payload.get('message');severity=payload.get('severity','information')
    if not isinstance(title,str) or not 4<=len(title.strip())<=120 or not isinstance(msg,str) or not 5<=len(msg.strip())<=700 or severity not in {'information','maintenance','notice'}:
        raise ValueError('invalid_notice')
    with connect() as db:
        cursor=db.execute('INSERT INTO notices(title,message,severity,created_at) VALUES(?,?,?,?)',(title.strip(),msg.strip(),severity,now))
        return {'ok':True,'id':cursor.lastrowid}


def staff_notice_close(payload):
    no=payload.get('id')
    if type(no)!=int or no<1:raise ValueError('invalid_id')
    with connect() as db:
        cur=db.execute('UPDATE notices SET active=0 WHERE id=?',(no,))
        if not cur.rowcount:raise LookupError('not_found')
    return {'ok':True,'id':no}


def poll():
    while True:
        try:
            with urlopen(HIST+'/api/plant/latest',timeout=5) as r:latest=json.load(r).get('sample')
            with urlopen(HIST+'/api/plant/history?limit=180',timeout=5) as r:rows=json.load(r).get('samples',[])
            update_from_historian(latest,rows)
        except (OSError,ValueError,KeyError,TypeError,TimeoutError) as exc:
            with lock:public.update(online=False,status='TELEMETRY_UNAVAILABLE')
            print('public publisher:', type(exc).__name__,flush=True)
        time.sleep(INTERVAL)


class Handler(JSONHandler):
    def staff_authorized(self):
        return bool(ADMIN_TOKEN) and hmac.compare_digest(self.headers.get('X-Public-Admin-Token',''),ADMIN_TOKEN)

    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/api/public':
            with lock:data=dict(public)
            return send_json(self,200,data)
        if path=='/api/public/history':
            with lock:data=list(history)
            return send_json(self,200,{'simulation':True,'samples':data})
        if path=='/api/public/statistics':return send_json(self,200,public_statistics())
        if path=='/api/public/notices':return send_json(self,200,{'notices':public_notices()})
        if path=='/api/internal/enquiries':
            if not self.staff_authorized():return send_json(self,403,{'error':'forbidden'})
            return send_json(self,200,{'enquiries':staff_list()})
        if path=='/health':
            with lock:online=public['online']
            return send_json(self,200 if online else 503,{'ok':online,'last_update':public['updated_at'],'db_ready':True})
        return send_json(self,404,{'error':'not_found'})

    def do_POST(self):
        path=urlsplit(self.path).path
        allowed={'/api/enquiries','/api/enquiries/track','/api/internal/enquiries/update','/api/internal/announcements','/api/internal/announcements/close'}
        if path not in allowed:return send_json(self,404,{'error':'not_found'})
        internal=path.startswith('/api/internal/')
        if internal and not self.staff_authorized():return send_json(self,403,{'error':'forbidden'})
        if not internal and self.headers.get('Content-Type','').split(';')[0].strip().lower()!='application/json':
            return send_json(self,415,{'error':'json_required'})
        try:
            obj=read_json(self,2048)
            if not isinstance(obj,dict):raise ValueError('invalid_body')
            if path=='/api/enquiries':
                # X-Real-IP is set by the only public Nginx entry and is NOT used for authentication.
                ip=self.headers.get('X-Real-IP','local')
                result=enquiries_submit(obj,ip)
                return send_json(self,201,result)
            if path=='/api/enquiries/track':
                result=track_enquiry(obj.get('reference'),obj.get('access_code'))
                if not result:return send_json(self,404,{'error':'not_found'})
                return send_json(self,200,result)
            if path=='/api/internal/enquiries/update':return send_json(self,200,staff_update(obj))
            if path=='/api/internal/announcements':return send_json(self,201,staff_notice(obj))
            if path=='/api/internal/announcements/close':return send_json(self,200,staff_notice_close(obj))
        except RuntimeError:
            return send_json(self,429,{'error':'too_many_requests'})
        except LookupError:
            return send_json(self,404,{'error':'not_found'})
        except (ValueError,TypeError,KeyError):
            return send_json(self,400,{'error':'invalid_request'})


if __name__=='__main__':
    if not PUBLIC_SALT or not ADMIN_TOKEN:
        raise SystemExit('Generate PUBLIC_SALT and PUBLIC_ADMIN_TOKEN using scripts/init_env.py')
    initialize()
    threading.Thread(target=poll,daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','8080'))),Handler).serve_forever()
