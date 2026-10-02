import argparse, html as html_lib, json, os, re, sys, urllib.request, urllib.error
from html.parser import HTMLParser

TICKERS_URL="https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL="https://data.sec.gov/submissions/CIK{cik}.json"
SUBMISSIONS_ARCHIVE_URL="https://data.sec.gov/submissions/{name}"
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

def _flat_exhibit_21_lines(html):
    """Return meaningful text blocks from a non-tabular Exhibit 21.

    Exhibit 21 has no required table shape.  Some issuers publish a heading,
    followed by one paragraph/div per subsidiary.  Keep this fallback tightly
    scoped to the text after a subsidiary-list heading so filing boilerplate
    cannot become an entity candidate.
    """
    text=re.sub(r"(?i)<br\s*/?>", "\n", html)
    text=re.sub(r"(?i)</(?:p|div|li|tr|h[1-6])\s*>", "\n", text)
    text=re.sub(r"<[^>]+>", " ", text)
    text=html_lib.unescape(text).replace("\xa0", " ")
    return [" ".join(line.split()) for line in text.splitlines() if line.strip()]

def extract_exhibit_21_rows(html):
    """Extract an Exhibit 21 table or a conservative flat subsidiary list."""
    parsed_tables=tables(html)
    if parsed_tables:
        return parsed_tables[0]

    lines=_flat_exhibit_21_lines(html)
    heading_index=None
    for i,line in enumerate(lines):
        if re.search(r"\blist of (?:significant )?subsidiaries\b", line, re.I):
            heading_index=i
            break
    if heading_index is None:
        return []

    rows=[["Subsidiary", "State/Country of Organization"]]
    for line in lines[heading_index+1:]:
        if re.match(r"(?i)^pursuant to\b", line):
            break
        if re.match(r"(?i)^\(as of\b", line):
            continue
        match=re.fullmatch(r"(.+?)\s*\(([^()]+)\)", line)
        if not match:
            continue
        name=" ".join(match.group(1).split())
        jurisdiction=" ".join(match.group(2).split())
        if not name or re.search(r"(?i)\bcorporation$", jurisdiction):
            continue
        rows.append([name, jurisdiction])
    return rows if len(rows)>1 else []

def is_exhibit_21_filename(name):
    """Recognize common SEC filename spellings for Exhibit 21/21.1.

    Filers are not consistent: examples include ``ex-21.htm``,
    ``exhibit21.1.htm`` and an inline-decimal form such as
    ``tgt-20250201xexhibit211.htm``.
    """
    return bool(re.search(
        r"(?:ex(?:hibit)?[-_]?21(?:[-_.]?1)?)(?=\.[^.]+$)",
        name,
        re.I,
    ))

def compact_cells(row):
    return [c.strip() for c in row if c and c.strip()]

def header_text(table, n=3):
    return " | ".join(" | ".join(compact_cells(r)) for r in table[:n]).casefold()

def ownership_table_score(table):
    if len(table) < 3:
        return -999

    head = header_text(table, 4)
    body = " ".join(c for r in table[:40] for c in compact_cells(r)).casefold()

    # Strong positive structural signals
    score = 0
    has_name = any(x in head for x in (
        "name of company","company name","subsidiary name","name of subsidiary","legal name"
    ))
    has_country = any(x in head for x in (
        "country of incorporation","country of organization","country of organisation",
        "country of residence","jurisdiction","state/country of organization",
        "state of incorporation","place of incorporation"
    ))
    has_ownership = any(x in head for x in (
        "percentage owned","percent owned","ownership","voting interest","equity interest"
    ))

    if has_name: score += 10
    if has_country: score += 8
    if has_ownership: score += 8

    # Bonus when all three appear together
    if has_name and has_country and has_ownership:
        score += 12

    # Data-shape bonuses
    pct_like = 0
    country_like = 0
    entity_like = 0
    for row in table[1:60]:
        cells = compact_cells(row)
        if not cells: continue
        if any(re.fullmatch(r"\d{1,3}(?:\.\d+)?", c) or re.fullmatch(r"\d{1,3}(?:\.\d+)?%", c) for c in cells):
            pct_like += 1
        if any(re.fullmatch(r"[A-Za-z][A-Za-z .&'()-]{1,35}", c) for c in cells[1:]):
            country_like += 1
        if any(re.search(r"\b(?:inc\.?|corp\.?|corporation|llc|ltd\.?|limited|gmbh|b\.?v\.?|plc|pte\.?|pty|co\.?)\b", c, re.I) for c in cells[:2]):
            entity_like += 1

    if pct_like >= 5: score += 5
    if country_like >= 5: score += 3
    if entity_like >= 5: score += 4
    if len(table) >= 10: score += 2

    # Strong disqualifiers for the false positives observed in Sony v3
    disqualifiers = (
        "nyse standards","corporate governance practices","statutory tax rate",
        "deferred tax","yield curve","weighted average interest rate",
        "meeting records","attendance records","type of remuneration",
        "brief personal history","date of birth","notes to consolidated financial statements",
        "item 1. identity of directors","item 4. information on the company",
        "amended articles of incorporation","302 certification","906 certification"
    )
    if any(x in head or x in body[:1200] for x in disqualifiers):
        score -= 30

    # Facility tables are useful enrichment, but not the canonical ownership table.
    if "facility or subsidiary name" in head:
        score -= 12

    return score

def table_signature(table):
    """
    Duplicate detection for equivalent ownership tables in the same filing.
    Uses normalized first-column entity names, ignoring headers and blanks.
    """
    vals=[]
    for row in table[1:]:
        cells=compact_cells(row)
        if not cells: continue
        first=norm(cells[0])
        if not first: continue
        if any(x in first for x in ("name of company","subsidiary name","company name")):
            continue
        vals.append(first)
    return tuple(vals)

def select_20f_ownership_table(html):
    ts=tables(html)
    scored=[(ownership_table_score(t),i,t) for i,t in enumerate(ts)]
    scored.sort(key=lambda x:x[0], reverse=True)

    diagnostics=[
        {"table_index":i,"score":s,"row_count":len(t),"header":header_text(t,2)[:300]}
        for s,i,t in scored[:12]
    ]

    candidates=[(s,i,t) for s,i,t in scored if s >= 20]
    if not candidates:
        return None, [], diagnostics

    # Keep best table, then record equivalent duplicates for provenance.
    best_score,best_idx,best_table=candidates[0]
    best_sig=table_signature(best_table)
    dupes=[]
    for s,i,t in candidates[1:]:
        sig=table_signature(t)
        if best_sig and sig:
            overlap=len(set(best_sig)&set(sig))
            denom=max(1,min(len(set(best_sig)),len(set(sig))))
            if overlap/denom >= 0.80:
                dupes.append({"table_index":i,"score":s,"row_count":len(t),"overlap_ratio":round(overlap/denom,3)})

    return {
        "table_index":best_idx,
        "score":best_score,
        "rows":best_table,
        "duplicate_tables":dupes,
    }, candidates, diagnostics

def _annual_filings_from_arrays(records, filing_year=None):
    out=[]
    forms=records.get("form",[])
    accessions=records.get("accessionNumber",[])
    dates=records.get("filingDate",[])
    primaries=records.get("primaryDocument",[""]*len(forms))
    for i,form in enumerate(forms):
        if form not in ("10-K","10-K/A","20-F","20-F/A"):
            continue
        date=dates[i]
        if filing_year is not None and not str(date).startswith(f"{filing_year:04d}-"):
            continue
        out.append((form,accessions[i],date,primaries[i] if i < len(primaries) else ""))
    return out

def _archive_overlaps_year(metadata, filing_year):
    if filing_year is None:
        return False
    start=str(metadata.get("filingFrom") or "")[:4]
    end=str(metadata.get("filingTo") or "")[:4]
    if not (start.isdigit() and end.isdigit()):
        return True
    return int(start) <= filing_year <= int(end)

def annual_filings(cik,ua,filing_year=None):
    sub=get_json(SUBMISSIONS_URL.format(cik=cik.zfill(10)),ua)
    filings=sub.get("filings",{})
    out=_annual_filings_from_arrays(filings.get("recent",{}),filing_year)

    # SEC moves older submissions into named archive JSON files.  Avoid the
    # extra requests for the normal latest-filing path; consult only archive
    # chunks whose advertised date range can contain the requested year.
    if filing_year is not None:
        for metadata in filings.get("files",[]):
            name=metadata.get("name")
            if not name or not _archive_overlaps_year(metadata,filing_year):
                continue
            archived=get_json(SUBMISSIONS_ARCHIVE_URL.format(name=name),ua)
            out.extend(_annual_filings_from_arrays(archived,filing_year))

    # Amendment and duplicate records can repeat the same accession.
    deduped={row[1]:row for row in out}
    return sorted(deduped.values(),key=lambda row:(row[2],row[1]),reverse=True)

def discover(cik,ua,maxn,filing_year=None):
    ci=str(int(cik)); out=[]
    for form,acc,date,primary in annual_filings(cik,ua,filing_year=filing_year):
        an=acc.replace("-","")
        if form.startswith("10-K"):
            try:d=get_json(INDEX_URL.format(cik=ci,acc=an),ua)
            except Exception as e:
                print("Warning index",acc,e,file=sys.stderr);continue
            ex=None
            for item in d.get("directory",{}).get("item",[]):
                n=item.get("name","")
                if is_exhibit_21_filename(n):ex=n;break
            if ex:out.append((form,acc,date,DOC_URL.format(cik=ci,acc=an,name=ex),"exhibit_21"))
        else:
            if primary:out.append((form,acc,date,DOC_URL.format(cik=ci,acc=an,name=primary),"20f_ownership_table"))
        if len(out)>=maxn:break
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--company",required=True);ap.add_argument("--out",required=True)
    ap.add_argument("--user-agent",default=os.environ.get("SEC_USER_AGENT"));ap.add_argument("--max-filings",type=int,default=1)
    ap.add_argument("--filing-year",type=int,help="Fetch annual corporate-structure filings submitted in this year, including SEC archive indexes")
    a=ap.parse_args()
    if not a.user_agent:sys.exit("Set SEC_USER_AGENT or pass --user-agent")
    m=find_cik(a.company,a.user_agent)
    if not m:sys.exit(f"No CIK found for '{a.company}'")
    if len(m)>1:
        print(f"Multiple matches for '{a.company}', using first:",file=sys.stderr)
        for x in m:print(" -",x["title"],"CIK",x["cik_str"],x.get("tickers",[]),file=sys.stderr)
    cik=str(m[0]["cik_str"]); docs=discover(cik,a.user_agent,a.max_filings,filing_year=a.filing_year)
    scope=f"filed in {a.filing_year}" if a.filing_year is not None else "in recent filings"
    if not docs:sys.exit(f"No supported corporate-structure documents found {scope} for CIK {cik}")

    out={"company":m[0]["title"],"cik":cik,"filings":[]}
    for form,acc,date,url,method in docs:
        h=get_text(url,a.user_agent)
        f={"accession":acc,"filing_date":date,"form_type":form,"document_url":url,"extraction_method":method}
        ts=tables(h)
        if method=="exhibit_21":
            f["extracted_rows"]=extract_exhibit_21_rows(h)
        else:
            selected, candidates, diagnostics = select_20f_ownership_table(h)
            f["candidate_table_diagnostics"]=diagnostics
            if selected:
                f["selected_table"]={
                    "table_index":selected["table_index"],
                    "score":selected["score"],
                    "duplicate_tables":selected["duplicate_tables"],
                }
                f["extracted_rows"]=selected["rows"]
            else:
                f["selected_table"]=None
                f["extracted_rows"]=[]
                print("Warning: 20-F found but no ownership table met threshold.",file=sys.stderr)
        out["filings"].append(f)

    os.makedirs(os.path.dirname(a.out) or ".",exist_ok=True)
    with open(a.out,"w",encoding="utf-8") as fp:json.dump(out,fp,indent=2,ensure_ascii=False)
    total=sum(len(x.get("extracted_rows",[])) for x in out["filings"])
    print(f"Wrote {len(out['filings'])} filing(s), {total} extracted rows, to {a.out}")
    print("Methods:",", ".join(x["form_type"]+":"+x["extraction_method"] for x in out["filings"]))
    print("NOTE: best-effort corporate-structure evidence; review before trusting.")

if __name__=="__main__": main()
