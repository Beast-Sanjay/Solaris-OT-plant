#!/usr/bin/env python3
"""Generate an upstream-independent Compose overlay for existing mrhOTshOT targets.

No upstream files are modified. The integration copies original service definitions
for PLC fleet, SIS and FUXA, removes their universal network/host ports, and places
all control devices at Purdue L1 and FUXA at L2. This intentionally does not run the
upstream attack dashboard/Caldera: they require its flat otlab backbone.
"""
from pathlib import Path
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'upstream/docker/docker-compose.yml'
OUTPUT = ROOT / 'compose.mrhotshot.yaml'
PLC_NAMES = ('plc-water', 'plc-power', 'plc-gas', 'plc-centrifuge', 'plc-hvac',
             'plc-boiler', 'plc-heating', 'plc-dnp3', 'plc-sensors',
             'plc-vehicle', 'plc-signals', 'sis')


def build(source):
    services = source['services']
    generated = {}
    for name in PLC_NAMES + ('fuxa',):
        if name not in services:
            raise ValueError(f'Upstream service {name!r} not found: inspect repository version')
        entry = dict(services[name])
        entry.pop('ports', None)  # Never expose industrial protocols to host
        entry.pop('deploy', None)
        entry.pop('container_name', None)
        entry.pop('depends_on', None)  # Set after service selection
        entry['networks'] = ['level2' if name == 'fuxa' else 'level1']
        entry['restart'] = 'unless-stopped'
        if 'build' in entry:
            build_info = dict(entry['build'])
            build_info['context'] = './upstream'
            entry['build'] = build_info
        if name == 'fuxa':
            # Loopback-only UI access. HMI seeds using upstream seed script.
            entry['ports'] = ['127.0.0.1:1881:1881']
        if name in ('plc-heating', 'plc-power'):
            # L1 DNS alias differs from FUXA's required L2 hostname. The L2 alias
            # 'plc-heating' belongs only to the TCP conduit.
            entry['networks'] = {'level1': {'aliases': [name + '-l1']}}
        generated[name] = entry
    generated['sis']['depends_on'] = ['plc-water']
    # Optional legacy Modbus-to-FUXA bridge, only installed with upstream overlay.
    # Does NOT connect to the solar PPC; original fleet represents independent demo systems.
    generated['control-conduit'] = {
        'image': 'python:3.12-slim',
        'working_dir': '/app',
        'volumes': ['./services:/app:ro'],
        'command': ['python', '-u', '/app/tcp_relay.py'],
        'environment': {'TCP_RELAYS': '502=plc-heating-l1:502,15022=plc-power-l1:502'},
        'sysctls': ['net.ipv4.ip_forward=0'],
        'networks': {'level1': {}, 'level2': {'aliases': ['plc-heating', 'plc-power']}},
        'restart': 'unless-stopped'
    }
    # Original FUXA named volume is fully managed here, no host paths inherited.
    return {'services': generated, 'volumes': {'fuxa_data': {}}}


def main():
    if not SOURCE.exists():
        raise SystemExit('Missing upstream. Run scripts/setup.sh (or clone upstream into ./upstream).')
    original = yaml.safe_load(SOURCE.read_text())
    overlay = build(original)
    OUTPUT.write_text('# AUTO-GENERATED: source upstream/docker/docker-compose.yml; Apache-2.0.\n'
                      + '# No shared otlab NIC and no host-published OT protocol ports.\n'
                      + yaml.safe_dump(overlay, sort_keys=False))
    print(f'[OK] Generated {OUTPUT} with {len(overlay["services"])} original mrhOTshOT services')

if __name__ == '__main__': main()
