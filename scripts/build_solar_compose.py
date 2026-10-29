#!/usr/bin/env python3
"""Build solar-first Compose from previous project while retaining AD/IT/SOC zones."""
import yaml
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'compose.yaml'
doc=yaml.safe_load(p.read_text());old=doc['services']
for name in ('field-sim','field-sim-b','field-conduit','field-conduit-b','plc-demo','plc-secondary','control-conduit','scada','supervisory-conduit','historian'):
    old.pop(name,None)
py=lambda script,nets,env={},extra={}: {'image':'python:3.12-slim','working_dir':'/app','volumes':['./services:/app:ro'],'restart':'unless-stopped','command':['python','-u','/app/'+script], 'networks':nets,'environment':env, **extra}
old['met-station']=py('solar_weather.py',{'level0':{'ipv4_address':'192.168.96.5'}})
for i in range(1,5):
    id=f'{i:02d}'
    old[f'pv-array-{id}']=py('solar_array.py',{'level0':{'ipv4_address':f'192.168.96.{20+i}'}},
       {'ASSET_ID':f'PV-{id}','STRINGS':'36','DC_KWP':'2800','YIELD_FACTOR':str(round(1-.01*(i-1),3)),
        'WEATHER_URL':'http://met-station:8080'})
    old[f'array-conduit-{id}']=py('http_relay.py',['level0','level1'],{
        'LISTEN_PORT':'8080','TARGET_URL':f'http://pv-array-{id}:8080',
        'ALLOWED_PATHS':'/api/state','ALLOWED_METHODS':'GET'}, {'sysctls':['net.ipv4.ip_forward=0']})
    old[f'inverter-{id}']=py('solar_inverter.py',{'level1':{'ipv4_address':f'192.168.95.{20+i}'}},
        {'ASSET_ID':f'INV-{id}','ARRAY_ID':f'PV-{id}',
         'FIELD_URL':f'http://array-conduit-{id}:8080','AC_KW':'2500',
         'CONTROL_TOKEN':'${CONTROL_TOKEN:?Run scripts/init_env.py}'})
    old[f'inverter-conduit-{id}']=py('solar_conduit.py',['level1','level2'],{
        'TARGET_URL':f'http://inverter-{id}:8080','TARGET_MODBUS_HOST':f'inverter-{id}',
        'ALLOWED_PATHS':'/api/state,/api/limit','ALLOWED_METHODS':'GET,POST',
        'LISTEN_PORT':'8080'}, {'sysctls':['net.ipv4.ip_forward=0']})
old['feeder-33kv']=py('solar_feeder.py',{'level1':{'ipv4_address':'192.168.95.80'}},
     {'CONTROL_TOKEN':'${CONTROL_TOKEN:?Run scripts/init_env.py}'})
old['feeder-conduit']=py('http_relay.py',['level1','level2'],{
    'LISTEN_PORT':'8080','TARGET_URL':'http://feeder-33kv:8080',
    'ALLOWED_PATHS':'/api/state,/api/feed,/api/breaker','ALLOWED_METHODS':'GET,POST'},
    {'sysctls':['net.ipv4.ip_forward=0']})
old['ppc-01']=py('solar_ppc.py',{'level2':{'ipv4_address':'172.18.20.25'}},
     {'CONTROL_TOKEN':'${CONTROL_TOKEN:?Run scripts/init_env.py}'})
old['scada']=py('solar_scada.py',{'level2':{'ipv4_address':'172.18.20.30'}},
     {'CONTROL_TOKEN':'${CONTROL_TOKEN:?Run scripts/init_env.py}'},
     {'ports':['127.0.0.1:1882:8080']})
old['supervisory-conduit']=py('http_relay.py',['level2','level3'],{
    'LISTEN_PORT':'8080','TARGET_URL':'http://scada:8080','ALLOWED_PATHS':'/api/state','ALLOWED_METHODS':'GET'},
    {'sysctls':['net.ipv4.ip_forward=0']})
old['historian']=py('solar_historian.py',['level3'],{
    'POLL_URL':'http://supervisory-conduit:8080/api/state',
    'SOC_URL':'http://soc-conduit:8080/api/events','DB_PATH':'/data/solar_historian.sqlite3','PORT':'8080'},
    {'volumes':['./services:/app:ro','historian_data:/data']})
old['historian-conduit']['environment']['ALLOWED_PATHS']='/api/latest,/api/history,/api/plant/latest,/api/plant/history,/api/devices/latest,/api/devices/history'
old['web-server']['volumes']=['./docs/web/index.html:/usr/share/nginx/html/index.html:ro',
    './docs/web/style.css:/usr/share/nginx/html/style.css:ro',
    './docs/web/app.js:/usr/share/nginx/html/app.js:ro',
    './docs/web/nginx.conf:/etc/nginx/conf.d/default.conf:ro']
# All services stay isolated in separate networks. Replace old Aqua lab with Solar first mode.
header='''# SOLARIS ONE — 10 MWac solar PV plant cyber range.
# Live chain: MET -> four PV arrays L0 -> four inverters L1 (Modbus)
# -> PPC L2 -> 33kV feeder L1 -> SCADA L2 -> historian L3 -> AD-gated IT L4.
# All Docker networks are internal; only local web dashboard and management ports published.
# This is SIMULATED data and a demonstrator register map, not certified SunSpec or a grid model.
'''
p.write_text(header+yaml.safe_dump(doc,sort_keys=False))
