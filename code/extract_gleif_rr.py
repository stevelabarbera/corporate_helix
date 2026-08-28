#!/usr/bin/env python3
import argparse, json, zipfile
from pathlib import Path

def records(path):
    with zipfile.ZipFile(path) as z, z.open(z.namelist()[0]) as f:
        buf=[]; depth=0; active=False
        for raw in f:
            s=raw.decode('utf-8')
            if not active and '"RelationshipRecord"' in s:
                active=True; buf=['{\n',s]; depth=1+s.count('{')-s.count('}')
            elif active:
                buf.append(s); depth += s.count('{')-s.count('}')
                if depth==0:
                    yield json.loads(''.join(buf).rstrip().rstrip(','))
                    active=False; buf=[]

def val(d,*p):
    for x in p: d=d.get(x,{}) if isinstance(d,dict) else {}
    return d.get('$') if isinstance(d,dict) else None

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--zip',required=True); ap.add_argument('--out',required=True)
    ap.add_argument('--type',default='IS_DIRECTLY_CONSOLIDATED_BY'); ap.add_argument('--lei')
    a=ap.parse_args()
    for obj in records(a.zip):
        r=obj['RelationshipRecord']['Relationship']; typ=val(r,'RelationshipType')
        s=val(r,'StartNode','NodeID'); e=val(r,'EndNode','NodeID')
        if typ==a.type and (not a.lei or a.lei in (s,e)):
            Path(a.out).write_text(json.dumps(obj,indent=2),encoding='utf-8')
            print(f'Extracted {typ}: {s} -> {e} -> {a.out}'); return
    raise SystemExit('No matching relationship found')
if __name__=='__main__': main()
