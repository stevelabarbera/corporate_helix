#!/usr/bin/env python3
"""M3.8: fetch SEC 8-K M&A event evidence.

MVP target: Broadcom / VMware.
Discovers 8-K filings from SEC submissions, fetches primary documents, and
extracts Item 1.01 / 2.01 text plus conservative M&A event candidates.
"""
import argparse, json, re, time, urllib.request, urllib.parse
from datetime import datetime, timezone
from html import unescape

SEC_DATA="https://data.sec.gov"
SEC_ARCH="https://www.sec.gov/Archives/edgar/data"

KNOWN_COMPANIES={
    "broadcom":{"cik":"1730168","name":"Broadcom Inc."},
    "broadcom inc":{"cik":"1730168","name":"Broadcom Inc."},
    "vmware":{"cik":"1124610","name":"VMware, Inc."},
    "vmware inc":{"cik":"1124610","name":"VMware, Inc."},
}

def get(url,user_agent):
    req=urllib.request.Request(url,headers={
        "User-Agent":user_agent,
        "Accept-Encoding":"identity",
        "Host":urllib.parse.urlparse(url).netloc
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
    # Capture Item 1.01 / 2.01 until the next Item heading.
    pat=re.compile(r"(?im)^\s*item\s+(1\.01|2\.01)\b[^\n]*")
    hits=list(pat.finditer(text))
    out=[]
    for h in hits:
        end=len(text)
        nxt=re.search(r"(?im)^\s*item\s+\d+\.\d+\b",text[h.end():])
        if nxt: end=h.end()+nxt.start()
        body=text[h.start():end].strip()
        out.append({"item":h.group(1),"text":body[:50000]})
    return out

def infer_candidates(section,filing_date,accession,source_url):
    txt=section["text"]
    low=txt.casefold()
    events=[]
    def add(kind,confidence,reason,acquirer=None,target=None,subject=None,result=None):
        events.append({
          "event_type":kind,"event_date":filing_date,
          "acquirer":acquirer,"target":target,"subject":subject,"result_entity":result,
          "confidence":confidence,"reason":reason,
          "sec_item":section["item"],"accession":accession,"source_url":source_url
        })

    # Broadcom/VMware benchmark-specific extraction, intentionally conservative.
    if "broadcom" in low and "vmware" in low:
        if section["item"]=="1.01" and any(x in low for x in ("merger agreement","agreement and plan of merger","acquire vmware")):
            add("AGREED_TO_ACQUIRE","HIGH","Broadcom and VMware named in Item 1.01 acquisition/merger agreement.",
                "Broadcom Inc.","VMware, Inc.")
        if section["item"]=="2.01" and any(x in low for x in ("completed","completion","consummated","consummation","acquisition")):
            add("ACQUIRED","HIGH","Broadcom and VMware named in Item 2.01 completion/consummation language.",
                "Broadcom Inc.","VMware, Inc.")
        if "vmware llc" in low and ("converted" in low or "conversion" in low):
            add("CONVERTED_TO","HIGH","Filing describes VMware legal-form conversion.",
                subject="VMware, Inc.",result="VMware LLC")

    # Generic M&A candidate signal for future companies; REVIEW by default.
    if not events and any(x in low for x in (
        "merger agreement","agreement and plan of merger","acquisition",
        "acquired","completed the acquisition","consummated the merger"
    )):
        add("M&A_CANDIDATE","REVIEW","M&A language detected; parties require adjudication.")

    return events

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--company",required=True)
    ap.add_argument("--cik")
    ap.add_argument("--start",default="2022-01-01")
    ap.add_argument("--end",default="2026-12-31")
    ap.add_argument("--user-agent",default="CorporateHelix research contact@example.com",
                    help="SEC asks for an identifying User-Agent; replace email with yours.")
    ap.add_argument("--out",required=True)
    a=ap.parse_args()

    key=a.company.strip().casefold().replace(",","").replace(".","")
    known=KNOWN_COMPANIES.get(key)
    cik=(a.cik or (known or {}).get("cik"))
    if not cik:
        raise SystemExit("Unknown company. Supply --cik.")
    cik10=str(int(cik)).zfill(10)

    sub=json.loads(get(f"{SEC_DATA}/submissions/CIK{cik10}.json",a.user_agent))
    recent=sub["filings"]["recent"]
    rows=[]
    for i,form in enumerate(recent["form"]):
        if form not in ("8-K","8-K/A"): continue
        fd=recent["filingDate"][i]
        if not (a.start <= fd <= a.end): continue
        items=(recent.get("items") or [""]*len(recent["form"]))[i] or ""
        if not ("1.01" in items or "2.01" in items): continue
        acc=recent["accessionNumber"][i]
        primary=recent["primaryDocument"][i]
        acc_nodash=acc.replace("-","")
        url=f"{SEC_ARCH}/{int(cik)}/{acc_nodash}/{primary}"
        try:
            html=get(url,a.user_agent)
            text=strip_html(html)
            secs=item_sections(text)
            wanted=[s for s in secs if s["item"] in ("1.01","2.01")]
            events=[]
            for s in wanted:
                events.extend(infer_candidates(s,fd,acc,url))
            rows.append({
              "company":a.company,"cik":cik10,"form":form,"filing_date":fd,
              "accession":acc,"items":items,"primary_document":primary,
              "source_url":url,"sections":wanted,"event_candidates":events
            })
            print(f"{fd} {form} {items or '-'} -> {len(wanted)} section(s), {len(events)} event candidate(s)")
            time.sleep(0.12)
        except Exception as e:
            print(f"WARN {acc}: {e}")

    payload={
      "schema_version":"m3.8-edgar-events-raw-v1",
      "generated_at":datetime.now(timezone.utc).isoformat(),
      "company":a.company,"cik":cik10,
      "window":{"start":a.start,"end":a.end},
      "filings":rows
    }
    PathLike=__import__("pathlib").Path
    PathLike(a.out).parent.mkdir(parents=True,exist_ok=True)
    PathLike(a.out).write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
    total=sum(len(x["event_candidates"]) for x in rows)
    print(f"Wrote {len(rows)} filing(s), {total} event candidate(s) -> {a.out}")

if __name__=="__main__":
    main()
