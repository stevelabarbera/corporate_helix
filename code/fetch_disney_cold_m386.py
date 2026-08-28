#!/usr/bin/env python3
import argparse,json,re,time,urllib.request
from pathlib import Path
from html import unescape
def clean(x):
 x=re.sub(r"(?is)<(script|style).*?>.*?</\1>"," ",x); x=re.sub(r"(?i)<br\s*/?>","\n",x)
 x=re.sub(r"(?i)</(?:p|div|tr|table|h[1-6])>","\n",x); x=re.sub(r"(?s)<[^>]+>"," ",x)
 x=unescape(x).replace("\xa0"," "); x=re.sub(r"[ \t]+"," ",x); return re.sub(r"\n\s*\n+","\n",x).strip()
def section(t,item):
 if item=="EXPLANATORY NOTE":
  m=re.search(r"(?i)\bEXPLANATORY NOTE\b",t)
  if not m:return ""
  q=t[m.end():]; e=re.search(r"(?i)\n\s*ITEM\s+[0-9]",q); return q[:e.start() if e else 12000].strip()
 m=re.search(rf"(?i)\bITEM\s*{re.escape(item)}\b",t)
 if not m:return ""
 q=t[m.end():]; e=re.search(r"(?i)\n\s*ITEM\s+(?:1\.0[1-9]|2\.0[1-9]|[3-9]\.0[1-9])\b",q)
 return q[:e.start() if e else 16000].strip()
ap=argparse.ArgumentParser(); ap.add_argument("--manifest",default="./data/benchmark/disney_cold_manifest.json")
ap.add_argument("--user-agent",required=True); ap.add_argument("--out",default="./data/raw/edgar_disney_fox_cold_m386.json"); a=ap.parse_args()
man=json.loads(Path(a.manifest).read_text()); filings=[]
for i,c in enumerate(man["cases"]):
 req=urllib.request.Request(c["url"],headers={"User-Agent":a.user_agent,"Accept-Encoding":"identity"})
 with urllib.request.urlopen(req,timeout=30) as r: txt=clean(r.read().decode("utf-8","replace"))
 sec=section(txt,c["item"])
 if not sec: raise SystemExit(f"SECTION FAILED: {c['id']} / {c['item']}")
 filings.append({"accession":c["accession"],"filing_date":c["filing_date"],"form":"8-K","items":[c["item"]],
  "sections":[{"item":c["item"],"text":sec}],"cold_case_id":c["id"],"source_url":c["url"]})
 print(f"{c['id']}: {len(sec):,} chars [{c['item']}]")
 if i+1<len(man["cases"]):time.sleep(.2)
Path(a.out).parent.mkdir(parents=True,exist_ok=True)
Path(a.out).write_text(json.dumps({"company":"Disney / 21CF cold corpus","filings":filings},indent=2))
print(f"Wrote {len(filings)} filing(s) -> {a.out}")
