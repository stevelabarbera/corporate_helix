#!/usr/bin/env python3
"""M3.8.3 — Generic SEC 8-K merger event extraction.

Goals:
- no Broadcom/VMware or Cisco/Splunk company-specific extraction blocks
- identify agreement, acquisition completion, merger-sub -> target lineage,
  survivor, and post-closing subsidiary state from common Item 1.01 / 2.01 prose
- preserve conservative fallbacks when parties cannot be extracted confidently
"""

import argparse, json, re, time, urllib.request, urllib.parse
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

SEC_DATA="https://data.sec.gov"
SEC_ARCH="https://www.sec.gov/Archives/edgar/data"

KNOWN_COMPANIES={
    "broadcom":{"cik":"1730168","name":"Broadcom Inc."},
    "broadcom inc":{"cik":"1730168","name":"Broadcom Inc."},
    "cisco":{"cik":"858877","name":"Cisco Systems, Inc."},
    "cisco systems":{"cik":"858877","name":"Cisco Systems, Inc."},
    "cisco systems inc":{"cik":"858877","name":"Cisco Systems, Inc."},
    "splunk":{"cik":"1353283","name":"Splunk Inc."},
    "splunk inc":{"cik":"1353283","name":"Splunk Inc."},
}

LEGAL_SUFFIX=r"(?:Inc\.?|Incorporated|Corp\.?|Corporation|LLC|L\.L\.C\.|Ltd\.?|Limited|plc|PLC)"
ENTITY=r"[A-Z][A-Za-z0-9&.,'’\- ]{1,90}?(?=\s*(?:\(|,?\s+(?:a|an)\s+[A-Z]|(?:\s+entered|\s+merged|\s+will|\s+completed|\s+pursuant|\s+and\s)|$))"

def get(url,user_agent):
    req=urllib.request.Request(url,headers={
        "User-Agent":user_agent,
        "Accept-Encoding":"identity",
        "Host":urllib.parse.urlparse(url).netloc,
    })
    with urllib.request.urlopen(req,timeout=60) as r:
        return r.read().decode("utf-8","replace")

def strip_html(s):
    s=re.sub(r"(?is)<(script|style).*?>.*?</\1>"," ",s)
    s=re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>","\n",s)
    s=re.sub(r"(?s)<[^>]+>"," ",s)
    s=unescape(s).replace("\xa0"," ")
    s=re.sub(r"[ \t]+"," ",s)
    s=re.sub(r"\n\s*\n+","\n",s)
    return s.strip()

def item_sections(text):
    pat=re.compile(r"(?im)^\s*item\s+(1\.01|2\.01)\b[^\n]*")
    hits=list(pat.finditer(text))
    out=[]
    for h in hits:
        end=len(text)
        nxt=re.search(r"(?im)^\s*item\s+\d+\.\d+\b",text[h.end():])
        if nxt:end=h.end()+nxt.start()
        out.append({"item":h.group(1),"text":text[h.start():end].strip()[:80000]})
    return out

def norm_name(s):
    if not s:return None
    s=re.sub(r"\s+"," ",s).strip(" ,.;")
    return s

def event(kind,date,accession,url,item,confidence="HIGH",reason=None,
          acquirer=None,target=None,subject=None,object_entity=None,result_entity=None,metadata=None):
    return {
      "event_type":kind,"event_date":date,"acquirer":acquirer,"target":target,
      "subject":subject,"object_entity":object_entity,"result_entity":result_entity,
      "confidence":confidence,"reason":reason,"sec_item":item,
      "accession":accession,"source_url":url,"metadata":metadata or {}
    }

def financing_only(text):
    low=text.casefold()
    financing=("credit agreement","term facility","term loan","borrow","lenders named therein",
               "finance the acquisition","funding date","bridge facility")
    actual_execution=("entered into an agreement and plan of merger",
                      "entered into the merger agreement with",
                      "entered into a merger agreement with")
    return any(x in low for x in financing) and not any(x in low for x in actual_execution)

def find_agreement_parties(text):
    # Pattern 1: "X entered into an Agreement and Plan of Merger ... with Y"
    pats=[
      r"(?P<a>[A-Z][A-Za-z0-9&.,'’\- ]{2,100}?)\s+(?:entered into|has entered into)\s+(?:an?\s+)?(?:Agreement and Plan of Merger|Merger Agreement)[^.\n]{0,180}?\s+with\s+(?P<t>[A-Z][A-Za-z0-9&.,'’\- ]{2,100}?)(?=\s*(?:\(|,|\.|\n))",
      r"(?P<a>[A-Z][A-Za-z0-9&.,'’\- ]{2,100}?)\s+(?:entered into|has entered into)\s+an?\s+Agreement and Plan of Merger[^.\n]{0,300}?(?P<t>[A-Z][A-Za-z0-9&.,'’\- ]{2,100}?)(?=\s*(?:\(|,|\.|\n))",
    ]
    for p in pats:
        m=re.search(p,text,re.I|re.S)
        if m:
            return norm_name(m.group("a")),norm_name(m.group("t"))
    return None,None

def find_completed_parties(text):
    pats=[
      r"(?P<a>[A-Z][A-Za-z0-9&.,'’\- ]{2,100}?)\s+completed\s+(?:its|the)\s+acquisition\s+of\s+(?P<t>[A-Z][A-Za-z0-9&.,'’\- ]{2,100}?)(?=\s*(?:\(|,|\.|\n))",
      r"(?P<a>[A-Z][A-Za-z0-9&.,'’\- ]{2,100}?)\s+completed\s+the\s+acquisition\s+of\s+(?P<t>[A-Z][A-Za-z0-9&.,'’\- ]{2,100}?)(?=\s*(?:\(|,|\.|\n))",
    ]
    for p in pats:
        m=re.search(p,text,re.I|re.S)
        if m:return norm_name(m.group("a")),norm_name(m.group("t"))
    return None,None

def find_merger_into(text):
    results=[]
    pat=re.compile(
      r"(?P<sub>[A-Z][A-Za-z0-9&.,'’\- ]{1,100}?)\s+(?:will be\s+)?merged with and into\s+(?P<obj>[A-Z][A-Za-z0-9&.,'’\- ]{1,100}?)(?=\s*(?:\(|,|\.|\n))",
      re.I|re.S
    )
    for m in pat.finditer(text):
        sub=norm_name(m.group("sub"));obj=norm_name(m.group("obj"))
        window=text[m.start():m.start()+500]
        survivor=None
        if re.search(rf"{re.escape(obj)}\s+(?:continuing|will continue)\s+as\s+the\s+surviving",window,re.I):
            survivor=obj
        else:
            m2=re.search(r"with\s+([A-Z][A-Za-z0-9&.,'’\- ]{1,100}?)\s+(?:continuing|as)\s+the\s+surviving",window,re.I|re.S)
            if m2:survivor=norm_name(m2.group(1))
        results.append((sub,obj,survivor))
    return results

def find_conversion(text):
    low=text.casefold()
    if "converted from a delaware corporation into a delaware limited liability company" in low:
        return {"from_legal_form":"Delaware corporation","to_legal_form":"Delaware limited liability company"}
    m=re.search(r"converted from an?\s+([^.;\n]{2,80}?)\s+into an?\s+([^.;\n]{2,80}?)(?=\.|;|\n)",text,re.I)
    if m:
        return {"from_legal_form":norm_name(m.group(1)),"to_legal_form":norm_name(m.group(2))}
    return None

def find_postclose_subsidiary(text):
    # "X ... becoming a wholly owned subsidiary of Y"
    out=[]
    pat=re.compile(
      r"(?P<sub>[A-Z][A-Za-z0-9&.,'’\- ]{1,100}?)\s+(?:continuing as .*?\s+and\s+)?(?:becoming|as)\s+a\s+wholly owned subsidiary of\s+(?P<par>[A-Z][A-Za-z0-9&.,'’\- ]{1,100}?)(?=\s*(?:\(|,|\.|\n))",
      re.I|re.S
    )
    for m in pat.finditer(text):
        out.append((norm_name(m.group("sub")),norm_name(m.group("par"))))
    return out

def infer(section,filing_date,accession,url):
    text=section["text"];item=section["item"];low=text.casefold();events=[]

    if item=="1.01" and financing_only(text):
        return []

    a,t=find_agreement_parties(text)
    if item=="1.01" and a and t:
        events.append(event("AGREED_TO_ACQUIRE",filing_date,accession,url,item,
                            reason="Generic Item 1.01 merger-agreement execution pattern.",
                            acquirer=a,target=t))

    a2,t2=find_completed_parties(text)
    if item=="2.01" and a2 and t2:
        events.append(event("ACQUIRED",filing_date,accession,url,item,
                            reason="Generic Item 2.01 completed-acquisition pattern.",
                            acquirer=a2,target=t2))

    if item=="2.01":
        for i,(sub,obj,survivor) in enumerate(find_merger_into(text),1):
            events.append(event("MERGED_INTO",filing_date,accession,url,item,
                                reason="Generic 'merged with and into' transaction-lineage pattern.",
                                subject=sub,object_entity=obj,result_entity=survivor,
                                metadata={"sequence_index":i,"survivor_stated":bool(survivor)}))

        conv=find_conversion(text)
        if conv:
            # We intentionally do not infer the resulting legal name.
            # If target is known from ACQUIRED, attach conversion to the target as a conservative subject.
            subject=t2
            events.append(event("CONVERTED_TO",filing_date,accession,url,item,
                                reason="Generic legal-form conversion pattern.",
                                subject=subject,result_entity=None,
                                metadata={**conv,"result_name_explicitly_stated":False,
                                          "do_not_infer_result_name":True}))

        seen=set()
        for sub,par in find_postclose_subsidiary(text):
            key=(sub,par)
            if key in seen:continue
            seen.add(key)
            events.append(event("SUBSIDIARY_OF",filing_date,accession,url,item,
                                reason="Generic wholly-owned-subsidiary pattern.",
                                subject=sub,object_entity=par))

    if events:
        return events

    if any(x in low for x in (
        "agreement and plan of merger","merger agreement","completed its acquisition",
        "completed the acquisition","merged with and into","consummated the merger"
    )):
        return [event("M&A_CANDIDATE",filing_date,accession,url,item,
                      confidence="REVIEW",
                      reason="M&A language detected but generic party extraction was inconclusive.")]
    return []

def resolve_company(name,cik=None):
    if cik:return str(int(cik))
    key=name.strip().casefold().replace(",","").replace(".","")
    known=KNOWN_COMPANIES.get(key)
    if known:return known["cik"]
    raise SystemExit("Unknown company. Supply --cik.")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--company",required=True)
    ap.add_argument("--cik")
    ap.add_argument("--start",default="2020-01-01")
    ap.add_argument("--end",default="2026-12-31")
    ap.add_argument("--user-agent",required=True)
    ap.add_argument("--out",required=True)
    a=ap.parse_args()

    cik=resolve_company(a.company,a.cik)
    cik10=str(int(cik)).zfill(10)
    sub=json.loads(get(f"{SEC_DATA}/submissions/CIK{cik10}.json",a.user_agent))
    recent=sub["filings"]["recent"]

    rows=[]
    for i,form in enumerate(recent["form"]):
        if form not in ("8-K","8-K/A"):continue
        fd=recent["filingDate"][i]
        if not (a.start<=fd<=a.end):continue
        items=(recent.get("items") or [""]*len(recent["form"]))[i] or ""
        if not ("1.01" in items or "2.01" in items):continue

        acc=recent["accessionNumber"][i]
        primary=recent["primaryDocument"][i]
        url=f"{SEC_ARCH}/{int(cik)}/{acc.replace('-','')}/{primary}"
        try:
            text=strip_html(get(url,a.user_agent))
            sections=[s for s in item_sections(text) if s["item"] in ("1.01","2.01")]
            evs=[]
            for s in sections:evs.extend(infer(s,fd,acc,url))
            rows.append({"company":a.company,"cik":cik10,"form":form,"filing_date":fd,
                         "accession":acc,"items":items,"primary_document":primary,
                         "source_url":url,"sections":sections,"event_candidates":evs})
            print(f"{fd} {form} {items or '-'} -> {len(sections)} section(s), {len(evs)} event(s) {[e['event_type'] for e in evs]}")
            time.sleep(0.12)
        except Exception as e:
            print(f"WARN {acc}: {e}")

    payload={"schema_version":"m3.8.3-edgar-events-raw-v1",
             "generated_at":datetime.now(timezone.utc).isoformat(),
             "company":a.company,"cik":cik10,"window":{"start":a.start,"end":a.end},
             "filings":rows}
    Path(a.out).parent.mkdir(parents=True,exist_ok=True)
    Path(a.out).write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
    total=sum(len(x["event_candidates"]) for x in rows)
    print(f"Wrote {len(rows)} filing(s), {total} event(s) -> {a.out}")

if __name__=="__main__":
    main()
