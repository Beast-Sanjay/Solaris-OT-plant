#!/usr/bin/env python3
"""Create isolated lab credentials without shipping default passwords."""
from pathlib import Path
import secrets
import sys

root = Path(__file__).resolve().parents[1]
path = root / '.env'
keys = ('CORP_AD_ADMIN_PASSWORD', 'CORP_AD_ANALYST_PASSWORD',
        'ICS_AD_ADMIN_PASSWORD', 'ICS_AD_OPERATOR_PASSWORD',
        'JUMP_PASSWORD', 'DB_PASSWORD', 'CA_ENROLL_TOKEN', 'CONTROL_TOKEN',
        'WINDOWS_IT_PASSWORD', 'WINDOWS_SERVER_PASSWORD', 'WINDOWS_OT_PASSWORD',
        'PUBLIC_ADMIN_TOKEN', 'PUBLIC_SALT')
# Avoid punctuation that Samba tools may reject, still 160+ bits each.
def token():
    alphabet = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    chars = ['A', 'a', '7'] + [secrets.choice(alphabet) for _ in range(29)]
    secrets.SystemRandom().shuffle(chars)
    return ''.join(chars)
if path.exists():
    existing = path.read_text()
    present = {line.split('=', 1)[0] for line in existing.splitlines() if '=' in line and not line.startswith('#')}
    missing = [k for k in keys if k not in present]
    if not missing:
        print(f'[OK] Keeping existing {path} (never rotating silently).')
        sys.exit(0)
    with path.open('a') as fh:
        for key in missing: fh.write(f'{key}={token()}\n')
    print(f'[OK] Added missing credential keys {missing} without changing existing values.')
else:
    path.write_text('# Private lab credentials. Do not commit.\n' + ''.join(f'{k}={token()}\n' for k in keys))
path.chmod(0o600)
print(f'[OK] Generated {path} (owner-only read/write).')
