#!/usr/bin/env python3
import argparse,json,hashlib
from pathlib import Path

ALLOWED={"AGREED_TO_ACQUIRE","ACQUIRED","MERGED_INTO","CONVERTED_TO",
         "RENAMED_TO","SUBSIDIARY_OF","M&A_CANDIDATE"}

def event_id(e):
    raw="|".join(str(e.get(k) or "") for k in (
        "event_type","event_date","acquirer","target","subject",
        "object_entity","result_entity","accession"
    ))
    return "evt:"+hashlib.sha256(raw.encode()).hexdigest()[:20]

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--in",dest="inp",required=True);ap.add_argument("--out",required=True);a=ap.parse_args()
    raw=json.loads(Path(a.inp).read_text(encoding="utf-8"))
    events=[]
    for filing in raw.get("filings",[]):
        for e in filing.get("event_candidates",[]):
            if e.get("event_type") not in ALLOWED:continue
            events.append({
              "event_id":event_id(e),"event_type":e["event_type"],
              "effective_date":e.get("event_date"),
              "status":"CANDIDATE" if e["event_type"]=="M&A_CANDIDATE" else "ASSERTED_FROM_FILING",
              "parties":{"acquirer":e.get("acquirer"),"target":e.get("target"),
                         "subject":e.get("subject"),"object_entity":e.get("object_entity"),
                         "result_entity":e.get("result_entity")},
              "confidence":e.get("confidence"),"metadata":e.get("metadata") or {},
              "provenance":{"provider":"sec_edgar","form":filing.get("form"),
                            "sec_item":e.get("sec_item"),"accession":e.get("accession"),
                            "filing_date":filing.get("filing_date"),"source_url":e.get("source_url")},
              "reason":e.get("reason")
            })
    out={"schema_version":"m3.8.3-canonical-events-v1",
         "source_company":raw.get("company"),"source_cik":raw.get("cik"),"events":events}
    Path(a.out).parent.mkdir(parents=True,exist_ok=True)
    Path(a.out).write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding="utf-8")
    counts={}
    for e in events:counts[e["event_type"]]=counts.get(e["event_type"],0)+1
    print(f"Wrote {len(events)} canonical event(s) -> {a.out}")
    print("Event types:",counts or "NONE")
if __name__=="__main__":main()
