#!/usr/bin/env python3
import argparse,json
from pathlib import Path
from providers.gleif_rr_adapter import GleifRelationshipRecordAdapter
from providers.gleif_lei_lookup import GleifLeiIndex

DEFAULT_LEI_DB = "data/processed/gleif_lei.sqlite"

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--in',dest='inp',required=True); ap.add_argument('--out',required=True)
 ap.add_argument('--name',action='append',default=[],help='LEI=Legal Name (overrides index lookup)')
 ap.add_argument('--jurisdiction',action='append',default=[],help='LEI=CC or CC-REGION (overrides index lookup)')
 ap.add_argument('--lei-db',default=DEFAULT_LEI_DB,help=f'Path to GLEIF Level 1 SQLite index (default: {DEFAULT_LEI_DB})')
 ap.add_argument('--no-lei-db',action='store_true',help='Skip auto-enrichment; unresolved LEIs are tagged UNRESOLVED_RETRY')
 a=ap.parse_args(); pairs=lambda xs: dict(x.split('=',1) for x in xs)

 lei_index=None
 if not a.no_lei_db:
  db_path=Path(a.lei_db)
  if db_path.is_file():
   lei_index=GleifLeiIndex(db_path)
  else:
   print(f"Note: GLEIF LEI index not found at {db_path} — proceeding without auto-enrichment "
         f"(unresolved LEIs will be tagged UNRESOLVED_RETRY). Build it with "
         f"code/build_gleif_lei_index.py, or pass --no-lei-db to silence this note.")

 raw=json.loads(Path(a.inp).read_text())
 out=GleifRelationshipRecordAdapter().from_record(raw,pairs(a.name),pairs(a.jurisdiction),lei_index).to_dict()

 if lei_index is not None:
  lei_index.close()

 Path(a.out).parent.mkdir(parents=True,exist_ok=True); Path(a.out).write_text(json.dumps(out,indent=2,ensure_ascii=False))
 print(f"Wrote RR canonical result: {len(out['entities'])} related entity, {len(out['relationships'])} relationship -> {a.out}")
if __name__=='__main__': main()
