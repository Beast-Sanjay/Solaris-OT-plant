#!/usr/bin/env python3
"""Static network and profile assertions for optional dockurr/windows VMs."""
from pathlib import Path
from ipaddress import ip_address, ip_network
import yaml
root=Path(__file__).resolve().parents[1]
base=yaml.safe_load((root/'compose.yaml').read_text())
windows=yaml.safe_load((root/'compose.windows.yaml').read_text())
profiles={'win-it':'windows-it','win-server':'windows-server','win-ot':'windows-ot'}
subnets={k:ip_network(v['ipam']['config'][0]['subnet']) for k,v in base['networks'].items()}
assert subnets['level4']==ip_network('10.0.0.0/24')
assert subnets['level3']==ip_network('172.18.10.0/24')
for name,profile in profiles.items():
    spec=windows['services'][name]
    assert spec['profiles']==[profile]
    assert spec['image'].startswith('dockurr/windows')
    assert '/dev/kvm' in spec['devices'] and '/dev/net/tun' in spec['devices']
    assert 'NET_ADMIN' in spec['cap_add']
    ns=spec['networks'];assert len(ns)==1
    zone=next(iter(ns))
    assert zone == ('level3' if name=='win-ot' else 'level4')
    assert ip_address(ns[zone]['ipv4_address']) in subnets[zone]
    assert '/custom.iso:ro' in str(spec['volumes'])
    assert '/shared:ro' in str(spec['volumes'])
    assert '/var/run/docker.sock' not in str(spec)
    assert not ('DOMAIN' in spec['environment'])  # interactive join; no AD admin in Docker env
    assert spec['environment']['DNSMASQ_OPTS'].endswith('172.18.10.10' if name=='win-ot' else '10.0.0.10')
    assert spec['environment']['PASSWORD'].startswith('${WINDOWS_')
    assert all(str(p).startswith('127.0.0.1:') for p in spec['ports'])
for service,ip in [('dc01','10.0.0.10'),('ics-dc01','172.18.10.10'),('corp-portal','10.0.0.31'),('it-access','10.0.0.30'),('ot-scada-read','172.18.10.31')]:
    zone='level3' if service in ('ics-dc01','ot-scada-read') else 'level4'
    assert base['services'][service]['networks'][zone]['ipv4_address']==ip
relay=base['services']['ot-scada-read']
assert relay['environment']['ALLOWED_METHODS']=='GET'
assert '/api/control' not in relay['environment']['ALLOWED_PATHS']
# No VM guest has any second L4/L3 NIC; explicit conduits carry read-only telemetry.
print('[PASS] 3 optional Windows KVM guests, 2 independent Samba domains, corporate/OT DNS, no direct L4->OT NIC, restricted web ports')
