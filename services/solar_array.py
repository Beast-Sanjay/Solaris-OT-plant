"""L0 2.8 MWp photovoltaic array block: string current, voltage and available DC power."""
import json, os, threading, time, hmac
from pathlib import Path
from urllib.request import urlopen
from http.server import ThreadingHTTPServer
from common import JSONHandler, send_json, read_json
NAME=os.getenv('ASSET_ID','PV-01')
STRINGS=int(os.getenv('STRINGS','36'))
RATED=float(os.getenv('DC_KWP','2800'))
BIAS=float(os.getenv('YIELD_FACTOR','1'))
SOILING=float(os.getenv('SOILING_PCT','1.0'))
FAILED_STRINGS=int(os.getenv('FAILED_STRINGS','0'))
assert 0<=SOILING<=50 and 0<=FAILED_STRINGS<STRINGS
lock=threading.RLock()
SERVICE_TOKEN=os.getenv('CONTROL_TOKEN','')
STATE_FILE=os.getenv('STATE_FILE','')
if STATE_FILE and Path(STATE_FILE).exists():
    try:
        persisted=json.loads(Path(STATE_FILE).read_text())
        if 0 <= float(persisted['soiling_pct']) <= 50: SOILING=float(persisted['soiling_pct'])
        if 0 <= int(persisted['failed_strings']) < STRINGS: FAILED_STRINGS=int(persisted['failed_strings'])
    except (OSError,ValueError,KeyError,TypeError):pass

def service(action, value=None):
    # Only illustrative physical-maintenance operations. Not remote PLC control.
    with lock:
        current_soiling=float(state['soiling_pct']); current_failed=int(state['failed_strings'])
        if action=='clean': current_soiling=0.5
        elif action=='repair_strings':current_failed=0
        elif action=='inject_soiling':
            if type(value) not in (int,float) or not 0<=value<=50:raise ValueError('soiling range')
            current_soiling=float(value)
        elif action=='disconnect_strings':
            if type(value) is not int or not 0<=value<STRINGS:raise ValueError('string range')
            current_failed=int(value)
        else:raise ValueError('invalid service action')
        # Save first so an unwritable mounted volume does not report false success.
        if STATE_FILE:
            path=Path(STATE_FILE);path.parent.mkdir(parents=True,exist_ok=True)
            tmp=path.with_suffix('.tmp')
            tmp.write_text(json.dumps({'soiling_pct':current_soiling,'failed_strings':current_failed}))
            tmp.replace(path)
        state.update(soiling_pct=current_soiling,failed_strings=current_failed,
                     active_strings=STRINGS-current_failed,last_service_at=time.time(),last_service_action=action)
        return {'ok':True,'device':NAME,'action':action,'soiling_pct':current_soiling,'failed_strings':current_failed}

state={'device':NAME,'connected':False,'measured_at':0,'dc_kw':0,'dc_voltage_v':0,'dc_current_a':0,
       'strings':STRINGS,'active_strings':STRINGS-FAILED_STRINGS,'failed_strings':FAILED_STRINGS,
       'soiling_pct':SOILING,'last_service_at':None,'last_service_action':None,'string_current_a':0,'irradiance_w_m2':0,'module_c':0,'ambient_c':0,'loss_pct':0,'dc_kwp':RATED}
def poll():
    while True:
        try:
            with urlopen(os.getenv('WEATHER_URL','http://met-station:8080')+'/api/state',timeout=3) as r: w=json.load(r)
            irradiance=max(0,float(w['irradiance_w_m2']))
            module_c=float(w['module_c'])
            temp_factor=max(0.75,1-0.0035*(module_c-25))
            with lock: soiling=state['soiling_pct']; failed=state['failed_strings']
            loss=0.024+(1-BIAS)+soiling/100
            active_fraction=(STRINGS-failed)/STRINGS
            dc_kw=round(RATED*irradiance/1000*temp_factor*(1-loss)*active_fraction,2)
            voltage=round(1050*(1-0.0021*(module_c-25)),1)
            amps=round(dc_kw*1000/voltage,2) if voltage else 0
            with lock: state.update(connected=True,measured_at=time.time(),dc_kw=dc_kw,
                dc_voltage_v=voltage,dc_current_a=amps,string_current_a=round(amps/max(1,STRINGS-failed),2),
                irradiance_w_m2=irradiance,module_c=module_c,ambient_c=float(w['ambient_c']),loss_pct=round(loss*100,2))
        except (OSError,ValueError,KeyError,TimeoutError):
            with lock: state['connected']=False
        time.sleep(2)
class Handler(JSONHandler):
    def do_GET(self):
        if self.path=='/api/state':
            with lock: snap=dict(state)
            send_json(self,200,snap)
        elif self.path=='/health':
            with lock: ready=state['connected']
            send_json(self,200 if ready else 503,{'ok':ready,'device':NAME})
        else: send_json(self,404,{'error':'not_found'})
    def do_POST(self):
        if self.path!='/api/service':return send_json(self,404,{'error':'not_found'})
        supplied=self.headers.get('X-Field-Token','')
        if not SERVICE_TOKEN or not supplied or not hmac.compare_digest(SERVICE_TOKEN,supplied):
            return send_json(self,403,{'error':'field_authorization_required'})
        try:
            obj=read_json(self)
            if not isinstance(obj,dict) or set(obj)-{'action','value'}:raise ValueError('invalid payload')
            return send_json(self,200,service(obj['action'],obj.get('value')))
        except (ValueError,TypeError,KeyError):return send_json(self,400,{'error':'invalid_service'})
        except OSError:return send_json(self,503,{'error':'persistence_unavailable'})
if __name__=='__main__':
    threading.Thread(target=poll,daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','8080'))),Handler).serve_forever()
