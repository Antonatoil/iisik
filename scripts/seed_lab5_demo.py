"""One-time conversion of ONLY the original Lab 3 seeded demo users.

Run inside accounts container after Postgres is ready. Does not reset users,
databases, bookings, sessions or previously created passwords.
"""
import os
from sqlalchemy import text
from app.core.db import engine
from app.services.accounts_write import _hash

LEGACY = {
    '00000000-0000-4000-8000-000000000101': 'ceff7ffd7dc925f1f55dc4d74882e3774559b9227c28fba1c05347b8df231ded',
    '00000000-0000-4000-8000-000000000102': '82501600c50c7e857c50c866529502f6807fc9725b641ef210c1b84839c9044b',
    '00000000-0000-4000-8000-000000000201': '0d8e582d42094b954a011b8b156d623b06e3026933c5dec8e32723681af8e174',
    '00000000-0000-4000-8000-000000000202': '22e7d76271dd58cad849abc6dfa2ab7742fd3922b645f3a4122ac088df64d294',
    '00000000-0000-4000-8000-000000000301': '85205126422ac0e1b945b071dfe5e18c146b8266592e0c502fa0715e749d2605',
}
password = os.environ.get('LAB5_DEMO_PASSWORD')
if not password or len(password) < 18:
    raise SystemExit('LAB5_DEMO_PASSWORD must be set and at least 18 chars')
changed=0
with engine('a').begin() as conn:
    for uid, old_hash in LEGACY.items():
        new_hash = _hash(password)
        result = conn.execute(text('UPDATE users SET password_hash=:new WHERE id=CAST(:uid AS uuid) AND password_hash=:old'),
            {'new':new_hash,'uid':uid,'old':old_hash})
        changed += result.rowcount
print(f'Lab5: {changed} original demo account passwords upgraded; existing users unchanged')
