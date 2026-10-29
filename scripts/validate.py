#!/usr/bin/env python3
"""Check solar communication conduits, zone segmentation and Compose configuration."""
from pathlib import Path
from ipaddress import ip_network
import yaml
root=Path(__file__).resolve().parents[1]
files=[root/'compose.yaml']
if (root/'compose.mrhotshot.yaml').exists():files.append(root/'compose.mrhotshot.yaml')
services={};networks={}
for p in files:
    obj=yaml.safe_load(p.read_text())
    for name,service in obj['services'].items():
        assert name not in services,f'duplicate {name}'
        services[name]=service
    networks.update(obj.get('networks',{}))
zones={'level0','level1','level2','level3','idmz','level4','soc','web_dmz','wan_sim'}
assert zones.issubset(networks)
subnets=[ip_network(networks[name]['ipam']['config'][0]['subnet']) for name in zones]
for i,a in enumerate(subnets):
    for b in subnets[i+1:]:assert not a.overlaps(b),(a,b)
assert all(networks[z].get('internal',False) for z in zones)
required={'transformer-33kv','transformer-conduit','protection-relay','relay-conduit','grid-dispatch','grid-conduit','maintenance-bot','field-service','public-publisher','met-station','ppc-01','feeder-33kv','scada','historian','dc01','ics-dc01','db01','ca01','corp-portal','jump-server','it-access'}
for i in range(1,5):
    n=f'{i:02d}'
    required.update([f'pv-array-{n}',f'array-conduit-{n}',f'inverter-{n}',f'inverter-conduit-{n}'])
assert required.issubset(services),required-set(services)
allowed={'ot-scada-read','supervisory-conduit','historian-conduit','soc-conduit','jump-entry','it-access','web-entry','feeder-conduit','transformer-conduit','relay-conduit','grid-conduit','control-conduit','public-publisher','public-ops','public-case-conduit'}
allowed.update(f'array-conduit-{i:02d}' for i in range(1,5))
allowed.update(f'inverter-conduit-{i:02d}' for i in range(1,5))
for name,service in services.items():
    ns=service.get('networks',[]);ns=set(ns if isinstance(ns,list) else ns.keys())
    assert ns,f'{name} no network'
    assert len(ns)<=1 or name in allowed,(name,ns)
    assert 'otlab' not in ns,name
    assert not (('level4' in ns) and ('level1' in ns or 'level3' in ns)),name
    assert '/var/run/docker.sock' not in str(service),name
    for p in service.get('ports',[]) or []:assert str(p).startswith('127.0.0.1:'),(name,p)
for i in range(1,5):
    n=f'{i:02d}'
    assert services[f'pv-array-{n}']['networks'].keys()=={'level0'}
    assert services[f'inverter-{n}']['networks'].keys()=={'level1'}
    assert set(services[f'array-conduit-{n}']['networks'])=={'level0','level1'}
    assert set(services[f'inverter-conduit-{n}']['networks'])=={'level1','level2'}
assert services['scada']['networks'].keys()=={'level2'}
assert services['ppc-01']['networks'].keys()=={'level2'}
assert services['feeder-33kv']['networks'].keys()=={'level1'}
assert services['transformer-33kv']['networks'].keys()=={'level1'}
assert services['protection-relay']['networks'].keys()=={'level1'}
assert services['grid-dispatch']['networks'].keys()=={'level3'}
assert services['maintenance-bot']['networks']==['level4']
assert services['grid-conduit']['environment']['ALLOWED_METHODS']=='GET'
assert services['feeder-33kv']['environment']['TRANSFORMER_URL']=='http://transformer-33kv:8080'
assert set(services['supervisory-conduit']['networks'])=={'level2','level3'}
assert services['dc01']['networks']['level4']['ipv4_address']=='10.0.0.10'
assert services['ics-dc01']['networks']['level3']['ipv4_address']=='172.18.10.10'
assert services['historian-conduit']['environment']['ALLOWED_METHODS']=='GET'
assert set(services['public-publisher']['networks'])=={'idmz','web_dmz'}
assert services['web-server']['networks']==['web_dmz']
assert set(services['public-case-conduit']['networks'])=={'idmz','web_dmz'}
assert set(services['public-ops']['networks'])=={'level4','idmz'}
assert services['public-case-conduit']['environment']['CONDUIT_REQUIRE_AUTH_GET']=='true'
assert services['public-case-conduit']['environment']['ALLOWED_PATHS'].find('/api/control')<0
assert services['field-service']['networks']==['level0']
assert '/api/public' not in services['historian-conduit']['environment']['ALLOWED_PATHS']
for name in [*(f'inverter-conduit-{i:02d}' for i in range(1,5)), 'transformer-conduit','feeder-conduit','relay-conduit']:
    assert services[name]['environment']['CONDUIT_AUTH_HEADER']=='X-PPC-Token'
    assert services[name]['environment']['CONDUIT_AUTH_TOKEN']
for i in range(1,5):
    assert services[f'pv-array-{i:02d}']['environment']['STATE_FILE']=='/state/maintenance.json'

assert services['it-access']['environment']['HISTORIAN_URL'].startswith('http://historian-conduit')
if 'fuxa' in services:
    assert {'plc-heating','plc-power','control-conduit','public-publisher','public-ops','public-case-conduit'}.issubset(services)
    assert services['fuxa']['networks']==['level2']
print('[PASS] %d services; 9 isolated zones; 4 live array/inverter chains + transformer/relay/dispatch/field-service/public/maintenance; 0 direct L4->OT networks.'%len(services))
