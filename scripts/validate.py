#!/usr/bin/env python3
"""Non-Docker static assertions for topology and generated integration."""
from pathlib import Path
from ipaddress import ip_network
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
files = [ROOT / 'compose.yaml']
if (ROOT / 'compose.mrhotshot.yaml').exists(): files.append(ROOT / 'compose.mrhotshot.yaml')
if (ROOT / 'compose.solar.yaml').exists(): files.append(ROOT / 'compose.solar.yaml')
services = {}
networks = {}
for file in files:
    obj = yaml.safe_load(file.read_text())
    assert isinstance(obj.get('services'), dict), file
    for name, service in obj['services'].items():
        assert name not in services, f'duplicate {name}'
        services[name] = service
    networks.update(obj.get('networks', {}))

expected = {'level4', 'idmz', 'level3', 'level2', 'level1', 'level0', 'soc', 'web_dmz', 'wan_sim'}
assert expected.issubset(networks), 'missing zone'
cidrs = [ip_network(net['ipam']['config'][0]['subnet']) for net in networks.values()]
for i, a in enumerate(cidrs):
    for b in cidrs[i+1:]:
        assert not a.overlaps(b), f'overlapping {a} / {b}'
assert all(networks[name].get('internal', False) for name in expected), 'Internet isolation missing'
allowed_multi = {'field-conduit', 'control-conduit', 'supervisory-conduit', 'historian-conduit',
                 'soc-conduit', 'jump-entry', 'it-access', 'web-entry', 'solar-field-conduit', 'solar-ppc-conduit', 'solar-supervisory-conduit', 'solar-historian-conduit', 'solar-it-access'}
for name, service in services.items():
    ns = service.get('networks', [])
    ns = set(ns.keys()) if isinstance(ns, dict) else set(ns)
    assert len(ns) >= 1, f'{name} without networks'
    assert not (len(ns) > 1 and name not in allowed_multi), f'unexpected dual-homed service {name}'
    assert 'otlab' not in ns, f'bypass backbone on {name}'
    assert not (('level4' in ns) and ('level1' in ns)), f'unsafe L4-to-L1 {name}'
    assert not (('level4' in ns) and ('level3' in ns)), f'unsafe L4-to-L3 {name}'
    assert not ('/var/run/docker.sock' in str(service)), f'docker socket in {name}'
    for pub in service.get('ports', []) or []:
        assert str(pub).startswith('127.0.0.1:'), f'non-loopback published port: {name} -> {pub}'

if 'plc-heating' in services:
    assert {'plc-water', 'plc-heating', 'sis', 'fuxa'}.issubset(services)
    assert 'ports' not in services['plc-heating']
    assert services['fuxa']['networks'] == ['level2']
assert services['dc01']['networks']['level4']['ipv4_address'] == '10.0.0.10'
assert services['ics-dc01']['networks']['level3']['ipv4_address'] == '172.18.10.10'
assert services['it-access']['environment']['HISTORIAN_URL'].startswith('http://historian-conduit')
assert {'solar-physics','solar-inverter-01','solar-inverter-02','solar-inverter-03','solar-inverter-04','solar-ppc','solar-scada','solar-historian','solar-it-access'}.issubset(services)
assert services['solar-physics']['networks']['level0']['ipv4_address'] == '192.168.96.50'
assert services['solar-ppc']['networks'] == ['level1']
assert services['solar-scada']['networks'] == ['level2']
assert services['solar-it-access']['networks'] == ['level4', 'idmz']
print(f'[PASS] {len(services)} services, {len(expected)} isolated zones, 0 generic routers, loopback-only publications.')
