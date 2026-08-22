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

SUFFIXES={"corp","corporation","inc","incorporated","company","co","limited","ltd","plc"}

def norm_name(s):
    t=re.sub(r"[^a-z0-9]+"," ",s.casefold()).split()
    while t and t[-1] in SUFFIXES: t.pop()
    return " ".join(t)

def dedupe_ciks(es):
    d={}
    for e in es:
        k=str(e["cik_str"])
        if k not in d:
            d[k]=dict(e); d[k]["tickers"]=[]
        tk=e.get("ticker")
        if tk and tk not in d[k]["tickers"]: d[k]["tickers"].append(tk)
    return list(d.values())

def find_cik(query,user_agent):
    """Tiered CIK resolution (exact ticker -> exact title -> normalized title
    -> substring), same logic proven in fetch_edgar.py v4. Replaces the old
    KNOWN_COMPANIES hardcoded dict so this works for any filer, not just the
    Broadcom/VMware benchmark pair."""
    es=list(json.loads(get(f"{SEC_DATA.replace('data.sec.gov','www.sec.gov')}/files/company_tickers.json",user_agent)).values())
    q=query.strip()
    if q.isdigit():
        m=dedupe_ciks([e for e in es if str(e["cik_str"])==str(int(q))])
        return m
    x=[e for e in es if str(e.get("ticker","")).casefold()==q.casefold()]
    if x: return dedupe_ciks(x)
    x=[e for e in es if str(e.get("title","")).strip().casefold()==q.casefold()]
    if x: return dedupe_ciks(x)
    nq=norm_name(q)
    x=[e for e in es if norm_name(str(e.get("title","")))==nq]
    if x: return dedupe_ciks(x)
    return dedupe_ciks([e for e in es if nq and nq in norm_name(str(e.get("title","")))])

# --- Party extraction ---------------------------------------------------
# SEC 8-Ks almost universally define parties with a legal-name + defined-term
# pattern: `Full Legal Name (the "ShortName")` or `Full Legal Name ("ShortName")`.
# This is a much stronger, more general signal than guessing from
# capitalization or hardcoding company names — it's how the filings define
# their own vocabulary, for any filer.
DEFINED_PARTY_RE = re.compile(
    r"([A-Z][A-Za-z0-9&,\.\-\' ]{2,90}?),?\s*(?:a [^,\(\)]{3,60}?,\s*)?\((?:the\s+)?[\"\u201c]([A-Za-z0-9 &\-\.]{2,40})[\"\u201d]\)"
)

def extract_defined_parties(text):
    """Returns list of (full_name, short_name) in order of first appearance,
    deduplicated by short_name."""
    seen = {}
    for m in DEFINED_PARTY_RE.finditer(text):
        full, short = m.group(1).strip(), m.group(2).strip()
        # The capture is greedy back to the nearest sentence-ish boundary,
        # which sometimes drags in a leading date fragment ("On November 22,
        # 2023, Broadcom Inc." instead of just "Broadcom Inc."). Strip
        # anything up through a trailing 4-digit year + comma if present.
        full = re.sub(r"^.*\b(?:19|20)\d{2},\s*", "", full)
        if short not in seen:
            seen[short] = full
    return list(seen.items())

def find_filer_short_name(defined_parties, filer_official_name):
    """Match the filer's own resolved SEC name against the defined parties
    found in the text, so we know which defined term IS the filer (acquirer
    vs target direction depends on this)."""
    filer_norm = norm_name(filer_official_name)
    for short, full in defined_parties:
        if norm_name(full) == filer_norm or norm_name(short) == filer_norm:
            return short, full
    # Loose fallback: first token match (e.g. "Broadcom" in "Broadcom Inc.")
    filer_first_word = filer_norm.split()[0] if filer_norm else ""
    for short, full in defined_parties:
        if filer_first_word and filer_first_word in norm_name(full):
            return short, full
    return None, None

ACQUIRED_OF_RE = re.compile(r"(?i)\b(?:completed|consummated|closed)\b[^.]{0,80}?\bacquisition of\s+([A-Za-z0-9 &\-\.\']{2,60})")
ACQUIRED_BY_RE = re.compile(r"(?i)\bacqui(?:red|sition)\b[^.]{0,60}?\bby\s+([A-Za-z0-9 &\-\.\']{2,60})")
AGREED_ACQUIRE_RE = re.compile(r"(?i)\bagree(?:d|ment)\b[^.]{0,120}?\bacquire\s+([A-Za-z0-9 &\-\.\']{2,60})")
MERGER_WITH_RE = re.compile(r"(?i)\bentered into\b[^.]{0,60}?\b(?:agreement and plan of merger|merger agreement)\b[^.]{0,60}?\bwith\s+([A-Za-z0-9 &\-\.\']{2,60})")
PENDING_ACQUISITION_RE = re.compile(r"(?i)\bpending acquisition\b[^.]{0,60}?\bof\s+([A-Za-z0-9 &\-\.\']{2,60})")
MERGER_RE = re.compile(r"(?i)\bagreement and plan of merger\b")

def infer_candidates(section, filing_date, accession, source_url, filer_official_name):
    txt = section["text"]
    events = []

    def add(kind, confidence, reason, acquirer=None, target=None, subject=None, result=None, candidate_parties=None):
        events.append({
            "event_type": kind, "event_date": filing_date,
            "acquirer": acquirer, "target": target, "subject": subject, "result_entity": result,
            "confidence": confidence, "reason": reason,
            "candidate_parties": candidate_parties,
            "sec_item": section["item"], "accession": accession, "source_url": source_url
        })

    defined_parties = extract_defined_parties(txt)
    filer_short, filer_full = find_filer_short_name(defined_parties, filer_official_name)
    other_parties = [(s, f) for s, f in defined_parties if s != filer_short]

    # Try to resolve acquirer/target direction using the filer's own identity
    # plus directional action phrases. Only assert a role if we can match a
    # defined party's short name inside the action phrase's captured text —
    # if the captured text doesn't correspond to a defined party we found,
    # we don't trust it as a name (could be truncated mid-sentence garbage).
    def match_captured_to_party(captured):
        cap_norm = norm_name(captured)
        for short, full in other_parties:
            if norm_name(short) in cap_norm or norm_name(full)[:len(cap_norm)] == cap_norm[:len(norm_name(full))]:
                return full
        return None

    resolved = False
    if filer_short:
        m = ACQUIRED_OF_RE.search(txt)
        if m:
            target = match_captured_to_party(m.group(1))
            if target:
                add("ACQUIRED", "HIGH",
                    f"Filer ({filer_full}) named as acquirer via 'completed acquisition of' language; target matched to a defined party.",
                    acquirer=filer_full, target=target)
                resolved = True

        if not resolved:
            m = ACQUIRED_BY_RE.search(txt)
            if m:
                acquirer = match_captured_to_party(m.group(1))
                if acquirer:
                    add("ACQUIRED", "HIGH",
                        f"Filer ({filer_full}) named as target via 'acquired by' language; acquirer matched to a defined party.",
                        acquirer=acquirer, target=filer_full)
                    resolved = True

        if not resolved:
            m = PENDING_ACQUISITION_RE.search(txt)
            if m:
                target = match_captured_to_party(m.group(1))
                if target:
                    add("AGREED_TO_ACQUIRE", "MEDIUM",
                        f"Filing references a 'pending acquisition' of a party matched to a defined party (corroborating, not a fresh agreement-execution statement).",
                        acquirer=filer_full, target=target)
                    resolved = True

        if not resolved and MERGER_RE.search(txt):
            m = AGREED_ACQUIRE_RE.search(txt)
            if m:
                target = match_captured_to_party(m.group(1))
                if target:
                    add("AGREED_TO_ACQUIRE", "HIGH",
                        f"Merger agreement language with filer ({filer_full}) as acquirer; target matched to a defined party.",
                        acquirer=filer_full, target=target)
                    resolved = True

            if not resolved:
                m = MERGER_WITH_RE.search(txt)
                if m:
                    target = match_captured_to_party(m.group(1))
                    if target:
                        add("AGREED_TO_ACQUIRE", "HIGH",
                            f"Filer ({filer_full}) entered into merger agreement 'with' a party matched to a defined party.",
                            acquirer=filer_full, target=target)
                        resolved = True

            if not resolved and len(other_parties) == 1:
                # Merger agreement + exactly one other named party + filer
                # present, but direction phrase didn't match cleanly. Still
                # better than nothing, but lower confidence since direction
                # is inferred rather than matched to explicit language.
                add("AGREED_TO_ACQUIRE", "MEDIUM",
                    f"Merger agreement language between filer ({filer_full}) and one other defined party; direction inferred, not explicitly matched.",
                    acquirer=filer_full, target=other_parties[0][1])
                resolved = True

    # Conservative fallback: M&A language detected but we couldn't confidently
    # assign acquirer/target roles. Carry whatever defined parties we found
    # so a reviewer has real names to look at, rather than nothing — but
    # never assert a role we didn't actually match.
    if not resolved:
        low = txt.casefold()
        if any(x in low for x in (
            "merger agreement", "agreement and plan of merger", "acquisition",
            "acquired", "completed the acquisition", "consummated the merger"
        )):
            add("M&A_CANDIDATE", "REVIEW",
                "M&A language detected; parties could not be confidently assigned roles from filing text.",
                candidate_parties=[f for _, f in defined_parties] or None)

    return events

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

    if a.cik:
        cik = a.cik
        filer_official_name = a.company
    else:
        matches = find_cik(a.company, a.user_agent)
        if not matches:
            raise SystemExit(f"No CIK found for '{a.company}'. Supply --cik directly.")
        if len(matches) > 1:
            print(f"Multiple matches for '{a.company}', using first:", file=__import__("sys").stderr)
            for m in matches:
                print(f"  - {m['title']} (CIK {m['cik_str']}, tickers {m.get('tickers', [])})", file=__import__("sys").stderr)
        cik = str(matches[0]["cik_str"])
        filer_official_name = matches[0]["title"]

    cik10=str(int(cik)).zfill(10)
    print(f"Resolved filer: {filer_official_name} (CIK {cik10})")

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
                events.extend(infer_candidates(s,fd,acc,url,filer_official_name))
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
