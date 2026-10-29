#!/usr/bin/env python3
"""Create isolated lab credentials without shipping default passwords."""
from pathlib import Path
import secrets
import sys

root = Path(__file__).resolve().parents[1]
path = root / '.env'
if path.exists():
    print(f'[OK] Keeping existing {path} (never rotating silently).')
    sys.exit(0)
keys = ('CORP_AD_ADMIN_PASSWORD', 'CORP_AD_ANALYST_PASSWORD',
        'ICS_AD_ADMIN_PASSWORD', 'ICS_AD_OPERATOR_PASSWORD',
        'JUMP_PASSWORD', 'DB_PASSWORD')
# Avoid punctuation that Samba tools may reject, still 160+ bits each.
def token():
    alphabet = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    chars = ['A', 'a', '7'] + [secrets.choice(alphabet) for _ in range(29)]
    secrets.SystemRandom().shuffle(chars)
    return ''.join(chars)
path.write_text('# Private lab credentials. Do not commit.\n' + ''.join(f'{k}={token()}\n' for k in keys))
path.chmod(0o600)
print(f'[OK] Generated {path} (owner-only read/write).')
