#!/usr/bin/env python3
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from legal_nlp.transaction_interpreter import agreement,completion,mergers,subsidiaries,conversions
def mk(kind,f,s,**kw):
    evidence=kw.pop('evidence',None);md=kw.pop('metadata',{});md['evidence']=evidence
    return {'event_type':kind,'event_date':f['filing_date'],'confidence':'HIGH','reason':'M3.8.3.1 legal-prose role/action interpreter.','sec_item':s['item'],'accession':f['accession'],'source_url':f['source_url'],'metadata':md,**kw}
def finance(t):
    q=t.casefold();return any(x in q for x in ('credit agreement','senior notes','underwriting agreement','partial financing of the proposed acquisition')) and 'entered into an agreement and plan of merger' not in q
def interpret(f,s):
    t=s['text'];out=[]
    if finance(t):return out
    if s['item']=='1.01':
        x=agreement(t)
        if x:out.append(mk('AGREED_TO_ACQUIRE',f,s,acquirer=x['acquirer'],target=x['target'],subject=None,object_entity=None,result_entity=None,evidence=x['evidence']))
    if s['item']=='2.01':
        x=completion(t);target=x['target'] if x else None
        if x:out.append(mk('ACQUIRED',f,s,acquirer=x['acquirer'],target=x['target'],subject=None,object_entity=None,result_entity=None,evidence=x['evidence']))
        for y in mergers(t):out.append(mk('MERGED_INTO',f,s,acquirer=None,target=None,**y))
        for y in conversions(t,target):out.append(mk('CONVERTED_TO',f,s,acquirer=None,target=None,subject=y['subject'],object_entity=None,result_entity=None,evidence=y['evidence'],metadata={'from_legal_form':y['from_legal_form'],'to_legal_form':y['to_legal_form'],'result_name_explicitly_stated':False,'do_not_infer_result_name':True}))
        for y in subsidiaries(t):out.append(mk('SUBSIDIARY_OF',f,s,acquirer=None,target=None,result_entity=None,**y))
    return out
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--in',dest='inp',required=True);ap.add_argument('--out',required=True);a=ap.parse_args();raw=json.loads(Path(a.inp).read_text());total=0
    for f in raw.get('filings',[]):
        e=[]
        for s in f.get('sections',[]):e+=interpret(f,s)
        f['event_candidates']=e;total+=len(e);print(f"{f['filing_date']} -> {len(e)} event(s) {[x['event_type'] for x in e]}")
    raw['schema_version']='m3.8.3.1-edgar-events-raw-v1';Path(a.out).write_text(json.dumps(raw,indent=2,ensure_ascii=False));print(f"Wrote {len(raw.get('filings',[]))} filing(s), {total} event(s) -> {a.out}")
if __name__=='__main__':main()
