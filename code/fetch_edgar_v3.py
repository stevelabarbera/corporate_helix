import argparse, json, os, re, sys, urllib.request, urllib.error
from html.parser import HTMLParser

TICKERS_URL="https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL="https://data.sec.gov/submissions/CIK{cik}.json"
INDEX_URL="https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/index.json"
DOC_URL="https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{name}"
SUFFIXES={"corp","corporation","inc","incorporated","company","co","limited","ltd","plc"}

def get_json(url, ua):
    r=urllib.request.Request(url,headers={"User-Agent":ua})
    with urllib.request.urlopen(r,timeout=30) as x: return json.loads(x.read().decode())

def get_text(url, ua):
    r=urllib.request.Request(url,headers={"User-Agent":ua})
    with urllib.request.urlopen(r,timeout=30) as x: return x.read().decode("utf-8","replace")

def norm(s):
    t=re.sub(r"[^a-z0-9]+"," ",s.casefold()).split()
    while t and t[-1] in SUFFIXES: t.pop()
    return " ".join(t)

def dedupe(es):
    d={}
    for e in es:
        k=str(e["cik_str"])
        if k not in d:
            d[k]=dict(e); d[k]["tickers"]=[]
        tk=e.get("ticker")
        if tk and tk not in d[k]["tickers"]: d[k]["tickers"].append(tk)
    return list(d.values())

def find_cik(q,ua):
    es=list(get_json(TICKERS_URL,ua).values()); q=q.strip()
    if q.isdigit(): return dedupe([e for e in es if str(e["cik_str"])==str(int(q))])
    x=[e for e in es if str(e.get("ticker","")).casefold()==q.casefold()]
    if x:return dedupe(x)
    x=[e for e in es if str(e.get("title","")).strip().casefold()==q.casefold()]
    if x:return dedupe(x)
    nq=norm(q)
    x=[e for e in es if norm(str(e.get("title","")))==nq]
    if x:return dedupe(x)
    return dedupe([e for e in es if nq and nq in norm(str(e.get("title","")))])

class Tables(HTMLParser):
    def __init__(self):
        super().__init__(); self.tables=[]; self.depth=0; self.table=None; self.row=None; self.cell=None
    def handle_starttag(self,tag,attrs):
        tag=tag.lower()
        if tag=="table":
            self.depth+=1
            if self.depth==1:self.table=[]
        elif self.depth==1 and tag=="tr": self.row=[]
        elif self.depth==1 and tag in ("td","th"): self.cell=[]
        elif self.depth==1 and tag=="br" and self.cell is not None:self.cell.append(" ")
    def handle_data(self,data):
        if self.depth==1 and self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        tag=tag.lower()
        if self.depth==1 and tag in ("td","th") and self.cell is not None:
            if self.row is not None:self.row.append(" ".join("".join(self.cell).split()))
            self.cell=None
        elif self.depth==1 and tag=="tr":
            if self.row and any(self.row):self.table.append(self.row)
            self.row=None
        elif tag=="table":
            if self.depth==1 and self.table:self.tables.append(self.table)
            if self.depth>0:self.depth-=1

def tables(html):
    p=Tables(); p.feed(html); return p.tables

def score_table(t):
    if len(t)<3:return 0
    text=" ".join(c for r in t for c in r).casefold()
    head=" ".join(c for r in t[:6] for c in r).casefold()
    s=0
    if any(x in text for x in ("subsidiar","organizational structure","organisation structure","principal companies")):s+=8
    if any(x in head for x in ("country","jurisdiction","state of","place of","incorporation","organization","organisation")):s+=3
    if any(x in head for x in ("ownership","owned","percentage","percent","%","voting")):s+=3
    legal=len(re.findall(r"\b(?:inc|corp|corporation|ltd|limited|llc|gmbh|pty)\b",text))
    if legal>=3:s+=2
    if legal>=10:s+=2
    if len(re.findall(r"\b\d{1,3}(?:\.\d+)?\s*%",text))>=3:s+=2
    if len(t)>=8:s+=1
    if len(t)>=20:s+=1
    return s

def annual_filings(cik,ua):
    sub=get_json(SUBMISSIONS_URL.format(cik=cik.zfill(10)),ua)
    r=sub["filings"]["recent"]; out=[]
    prim=r.get("primaryDocument",[""]*len(r["form"]))
    for i,f in enumerate(r["form"]):
        if f in ("10-K","10-K/A","20-F","20-F/A"):
            out.append((f,r["accessionNumber"][i],r["filingDate"][i],prim[i]))
    return out

def discover(cik,ua,maxn):
    ci=str(int(cik)); out=[]
    for form,acc,date,primary in annual_filings(cik,ua):
        an=acc.replace("-","")
        if form.startswith("10-K"):
            try:d=get_json(INDEX_URL.format(cik=ci,acc=an),ua)
            except Exception as e:
                print("Warning index",acc,e,file=sys.stderr);continue
            ex=None
            for item in d.get("directory",{}).get("item",[]):
                n=item.get("name","")
                if re.search(r"ex-?21",n,re.I):ex=n;break
            if ex:out.append((form,acc,date,DOC_URL.format(cik=ci,acc=an,name=ex),"exhibit_21"))
        else:
            if primary:out.append((form,acc,date,DOC_URL.format(cik=ci,acc=an,name=primary),"20f_table_scan"))
        if len(out)>=maxn:break
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--company",required=True);ap.add_argument("--out",required=True)
    ap.add_argument("--user-agent",default=os.environ.get("SEC_USER_AGENT"));ap.add_argument("--max-filings",type=int,default=1)
    a=ap.parse_args()
    if not a.user_agent:sys.exit("Set SEC_USER_AGENT or pass --user-agent")
    m=find_cik(a.company,a.user_agent)
    if not m:sys.exit(f"No CIK found for '{a.company}'")
    if len(m)>1:
        print(f"Multiple matches for '{a.company}', using first:",file=sys.stderr)
        for x in m:print(" -",x["title"],"CIK",x["cik_str"],x.get("tickers",[]),file=sys.stderr)
    cik=str(m[0]["cik_str"]); docs=discover(cik,a.user_agent,a.max_filings)
    if not docs:sys.exit(f"No supported corporate-structure documents found in recent 10-K/20-F filings for CIK {cik}")
    out={"company":m[0]["title"],"cik":cik,"filings":[]}
    for form,acc,date,url,method in docs:
        h=get_text(url,a.user_agent)
        f={"accession":acc,"filing_date":date,"form_type":form,"document_url":url,"extraction_method":method}
        ts=tables(h)
        if method=="exhibit_21":
            f["extracted_rows"]=ts[0] if ts else []
        else:
            ranked=sorted([(score_table(t),i,t) for i,t in enumerate(ts)],reverse=True,key=lambda z:z[0])
            sel=[{"table_index":i,"score":s,"rows":t} for s,i,t in ranked if s>=6]
            f["candidate_table_diagnostics"]=[{"table_index":i,"score":s,"row_count":len(t)} for s,i,t in ranked[:10]]
            f["selected_tables"]=sel
            f["extracted_rows"]=[r for x in sel for r in x["rows"]]
            if not sel:print("Warning: 20-F found but no table met threshold.",file=sys.stderr)
        out["filings"].append(f)
    os.makedirs(os.path.dirname(a.out) or ".",exist_ok=True)
    with open(a.out,"w",encoding="utf-8") as fp:json.dump(out,fp,indent=2,ensure_ascii=False)
    total=sum(len(x.get("extracted_rows",[])) for x in out["filings"])
    print(f"Wrote {len(out['filings'])} filing(s), {total} extracted rows, to {a.out}")
    print("Methods:",", ".join(x["form_type"]+":"+x["extraction_method"] for x in out["filings"]))
    print("NOTE: best-effort corporate-structure evidence; review before trusting.")

if __name__=="__main__":main()
