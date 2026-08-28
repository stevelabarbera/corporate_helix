#!/usr/bin/env python3
import argparse,json
from pathlib import Path
from providers.gleif_rr_adapter import GleifRelationshipRecordAdapter

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--in',dest='inp',required=True); ap.add_argument('--out',required=True)
 ap.add_argument('--name',action='append',default=[],help='LEI=Legal Name'); ap.add_argument('--jurisdiction',action='append',default=[],help='LEI=CC or CC-REGION')
 a=ap.parse_args(); pairs=lambda xs: dict(x.split('=',1) for x in xs)
 raw=json.loads(Path(a.inp).read_text()); out=GleifRelationshipRecordAdapter().from_record(raw,pairs(a.name),pairs(a.jurisdiction)).to_dict()
 Path(a.out).parent.mkdir(parents=True,exist_ok=True); Path(a.out).write_text(json.dumps(out,indent=2,ensure_ascii=False))
 print(f"Wrote RR canonical result: {len(out['entities'])} related entity, {len(out['relationships'])} relationship -> {a.out}")
if __name__=='__main__': main()
