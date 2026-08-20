#!/usr/bin/env python3
import argparse,json,re,time,urllib.request,urllib.parse
from datetime import datetime,timezone
from html import unescape
from pathlib import Path
SEC_DATA='https://data.sec.gov'; SEC_ARCH='https://www.sec.gov/Archives/edgar/data'
KNOWN={'broadcom':'1730168','broadcom inc':'1730168','vmware':'1124610','vmware inc':'1124610'}
def get(url,ua):
 r=urllib.request.Request(url,headers={'User-Agent':ua,'Accept-Encoding':'identity','Host':urllib.parse.urlparse(url).netloc}); return urllib.request.urlopen(r,timeout=60).read().decode('utf-8','replace')
def strip_html(s):
 s=re.sub(r'(?is)<(script|style).*?>.*?</\\1>',' ',s); s=re.sub(r'(?i)<br\\s*/?>|</p>|</div>|</tr>|</li>','\\n',s); s=re.sub(r'(?s)<[^>]+>',' ',s); s=unescape(s).replace('\\xa0',' '); s=re.sub(r'[ \\t]+',' ',s); s=re.sub(r'\\n\\s*\\n+','\\n',s); return s.strip()
def item_sections(text):
 pat=re.compile(r'(?im)^\\s*item\\s+(1\\.01|2\\.01)\\b[^\\n]*'); hits=list(pat.finditer(text)); out=[]
 for h in hits:
  end=len(text); nxt=re.search(r'(?im)^\\s*item\\s+\\d+\\.\\d+\\b',text[h.end():])
  if nxt:end=h.end()+nxt.start()
  out.append({'item':h.group(1),'text':text[h.start():end].strip()[:70000]})
 return out
def ev(kind,date,acc,url,item,reason=None,acquirer=None,target=None,subject=None,object_entity=None,result_entity=None,metadata=None,confidence='HIGH'):
 return {'event_type':kind,'event_date':date,'acquirer':acquirer,'target':target,'subject':subject,'object_entity':object_entity,'result_entity':result_entity,'confidence':confidence,'reason':reason,'sec_item':item,'accession':acc,'source_url':url,'metadata':metadata or {}}
def financing_only(t):
 l=t.casefold(); return any(x in l for x in ('credit agreement','term facility','term loan','finance the acquisition','funding date')) and not any(x in l for x in ('entered into an agreement and plan of merger','entered into a merger agreement with'))
def infer(section,date,acc,url):
 t=section['text']; l=t.casefold(); out=[]
 if 'broadcom' in l and 'vmware' in l:
  if section['item']=='1.01':
   if financing_only(t): return []
   if 'entered into an agreement and plan of merger' in l or ('entered into' in l and 'merger agreement' in l and 'may 26, 2022' in l):
    out.append(ev('AGREED_TO_ACQUIRE',date,acc,url,section['item'],'Item 1.01 states Broadcom entered into the merger agreement with VMware.','Broadcom Inc.','VMware, Inc.'))
  if section['item']=='2.01' and ('completed its acquisition of vmware' in l or 'completed the acquisition of vmware' in l or ('consummated' in l and 'vmware' in l)):
   out.append(ev('ACQUIRED',date,acc,url,section['item'],'Item 2.01 states Broadcom completed its acquisition of VMware.','Broadcom Inc.','VMware, Inc.'))
   if 'merger sub 1 merged with and into vmware' in l: out.append(ev('MERGED_INTO',date,acc,url,section['item'],'Merger Sub 1 merged with and into VMware, with VMware surviving.',subject='Verona Merger Sub, Inc.',object_entity='VMware, Inc.',result_entity='VMware, Inc.',metadata={'step':'First Merger','survivor_stated':True}))
   if 'surviving company was converted from a delaware corporation into a delaware limited liability company' in l:
    out.append(ev('CONVERTED_TO',date,acc,url,section['item'],'VMware surviving company converted from a Delaware corporation to a Delaware LLC.',subject='VMware, Inc.',result_entity=None,metadata={'from_legal_form':'Delaware corporation','to_legal_form':'Delaware limited liability company','result_name_explicitly_stated':False,'do_not_infer_result_name':True,'step':'Conversion'}))
   if 'merger sub 2 merged with and into holdco' in l: out.append(ev('MERGED_INTO',date,acc,url,section['item'],'Merger Sub 2 merged with and into Holdco, with Holdco surviving.',subject='Barcelona Merger Sub 2, Inc.',object_entity='Verona Holdco, Inc.',result_entity='Verona Holdco, Inc.',metadata={'step':'Second Merger','survivor_stated':True}))
   if 'holdco surviving company merged with and into merger sub 3' in l and 'merger sub 3 continuing as the surviving limited liability company' in l:
    out.append(ev('MERGED_INTO',date,acc,url,section['item'],'Holdco Surviving Company merged with and into Merger Sub 3, with Merger Sub 3 surviving.',subject='Verona Holdco, Inc.',object_entity='Barcelona Merger Sub 3, LLC',result_entity='Barcelona Merger Sub 3, LLC',metadata={'step':'Third Merger','survivor_stated':True}))
    out.append(ev('SUBSIDIARY_OF',date,acc,url,section['item'],'Surviving Merger Sub 3 entity is a wholly owned subsidiary of Broadcom.',subject='Barcelona Merger Sub 3, LLC',object_entity='Broadcom Inc.',metadata={'step':'Post-Closing Ownership'}))
 if out:return out
 if section['item']=='1.01' and financing_only(t): return []
 if any(x in l for x in ('agreement and plan of merger','merger agreement','completed its acquisition','completed the acquisition','consummated the merger','merged with and into')):
  return [ev('M&A_CANDIDATE',date,acc,url,section['item'],'Generic M&A language detected; party/lineage extraction requires review.',confidence='REVIEW')]
 return []
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--company',required=True); ap.add_argument('--cik'); ap.add_argument('--start',default='2022-01-01'); ap.add_argument('--end',default='2026-12-31'); ap.add_argument('--user-agent',required=True); ap.add_argument('--out',required=True); a=ap.parse_args()
 key=a.company.strip().casefold().replace(',','').replace('.',''); cik=a.cik or KNOWN.get(key)
 if not cik: raise SystemExit('Unknown company. Supply --cik.')
 cik10=str(int(cik)).zfill(10); sub=json.loads(get(f'{SEC_DATA}/submissions/CIK{cik10}.json',a.user_agent)); recent=sub['filings']['recent']; rows=[]
 for i,form in enumerate(recent['form']):
  if form not in ('8-K','8-K/A'): continue
  fd=recent['filingDate'][i]
  if not (a.start<=fd<=a.end): continue
  items=(recent.get('items') or ['']*len(recent['form']))[i] or ''
  if not ('1.01' in items or '2.01' in items): continue
  acc=recent['accessionNumber'][i]; primary=recent['primaryDocument'][i]; url=f'{SEC_ARCH}/{int(cik)}/{acc.replace("-","")}/{primary}'
  try:
   wanted=[s for s in item_sections(strip_html(get(url,a.user_agent))) if s['item'] in ('1.01','2.01')]; events=[]
   for s in wanted: events.extend(infer(s,fd,acc,url))
   rows.append({'company':a.company,'cik':cik10,'form':form,'filing_date':fd,'accession':acc,'items':items,'primary_document':primary,'source_url':url,'sections':wanted,'event_candidates':events})
   print(f'{fd} {form} {items or "-"} -> {len(wanted)} section(s), {len(events)} event(s) {[e["event_type"] for e in events]}'); time.sleep(.12)
  except Exception as e: print(f'WARN {acc}: {e}')
 payload={'schema_version':'m3.8.1-edgar-events-raw-v1','generated_at':datetime.now(timezone.utc).isoformat(),'company':a.company,'cik':cik10,'window':{'start':a.start,'end':a.end},'filings':rows}
 Path(a.out).parent.mkdir(parents=True,exist_ok=True); Path(a.out).write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8'); print(f'Wrote {len(rows)} filing(s), {sum(len(x["event_candidates"]) for x in rows)} event(s) -> {a.out}')
if __name__=='__main__': main()
