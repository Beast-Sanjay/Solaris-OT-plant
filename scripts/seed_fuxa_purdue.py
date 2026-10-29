#!/usr/bin/env python3
"""Seed upstream FUXA with *both* PLCs traversing the L2->L1 protocol conduit."""
from pathlib import Path
import importlib.util

root = Path(__file__).resolve().parents[1]
source = root / 'upstream/scripts/seed_fuxa_hmi.py'
if not source.exists():
    raise SystemExit('Missing upstream seed script. Run scripts/setup.sh first.')
spec = importlib.util.spec_from_file_location('mrhotshot_fuxa_seed', source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
_original = module.build_project

def build_purdue_project():
    project = _original()
    # FUXA heating :502 -> control-conduit :502; substation :15022 -> :502 L1
    project['devices']['HS1']['property']['address'] = 'plc-heating:502'
    project['devices']['PS2']['property']['address'] = 'plc-power:15022'
    return project

module.build_project = build_purdue_project

if __name__ == '__main__':
    module.main()
