"""Resolve local account phone aliases without changing the email auth runtime."""
import json
import re
from backend.registration import CHOICES

PREFIXES={choice['value']:''.join(re.findall(r'[0-9]',choice['label'].split('(')[0]))
          for choice in CHOICES['phone_codes']}


def number(value):
    if not isinstance(value,str):return None
    value=value.strip()
    if not re.fullmatch(r'\+?[0-9 ()\-]{4,30}',value):return None
    digits=re.sub(r'[^0-9]','',value)
    if not 4<=len(digits)<=18:return None
    return ('+' if value.startswith('+') else '')+digits


def resolve(db,identifier):
    """Only one matching account is usable; never pick a row by query order."""
    wanted=number(identifier)
    if wanted is None:return None
    matches=set()
    rows=db.execute("""SELECT a.email_normalized,e.payload FROM local_auth_accounts a
        JOIN icloud_entities e ON e.owner=a.account_id
        WHERE a.email_verified=1 AND e.kind='settings' AND e.id='profile'""")
    for row in rows:
        profile=json.loads(row['payload']);phone=number(profile.get('phone'))
        prefix=PREFIXES.get(profile.get('phone_code'))
        if not phone or not prefix:continue
        international=phone if phone.startswith('+') else '+'+prefix+phone
        if not international.startswith('+'+prefix):continue
        national=international[len(prefix)+1:]
        aliases={international,national,international[1:]}
        if wanted in aliases:matches.add(row['email_normalized'])
    return next(iter(matches)) if len(matches)==1 else None
