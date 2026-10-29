#!/usr/bin/env python3
"""Advisory address-overlap checks; prints warnings, never touches host routing."""
import json
from ipaddress import ip_network
from pathlib import Path
import subprocess
import yaml

root = Path(__file__).resolve().parents[1]
config = yaml.safe_load((root/'compose.yaml').read_text())
wanted = {k: ip_network(v['ipam']['config'][0]['subnet']) for k,v in config['networks'].items()}
try:
    all_names=subprocess.check_output(['docker','network','ls','--format','{{.Name}}'], text=True).splitlines()
    for name in all_names:
        details = json.loads(subprocess.check_output(['docker','network','inspect',name], text=True))[0]
        for c in details.get('IPAM',{}).get('Config',[]) or []:
            if not c.get('Subnet'): continue
            subnet=ip_network(c['Subnet'],strict=False)
            if subnet.version==4:
                for zone,target in wanted.items():
                    if subnet.overlaps(target):
                        print(f'[WARN] Docker network {name!r} ({subnet}) overlaps {zone} ({target}).')
except (OSError, subprocess.CalledProcessError, ValueError):
    print('[WARN] Could not inspect existing Docker networks.')
try:
    route=subprocess.check_output(['ip','-4','route','show'],text=True)
    for line in route.splitlines():
        first=line.split()[0]
        if first=='default':continue
        try: network=ip_network(first,strict=False)
        except ValueError:continue
        for zone,target in wanted.items():
            if network.overlaps(target):
                print(f'[WARN] Host route {network} overlaps lab {zone} {target}; use a dedicated lab VM.')
except (OSError, subprocess.CalledProcessError):
    print('[INFO] Host route check unavailable; inspect host routes manually.')
print('[INFO] These checks are advisory. Docker may still reject a conflicting subnet.')
