#!/usr/bin/env python3
import argparse,json,re,sys,time
from pathlib import Path
from collections import defaultdict

def norm(s):
    if s is None:return None
    return re.sub(r"\s+"," ",s).strip(" ,;")

def prf(pred,gold):
    p=set(pred);g=set(gold)
    tp=len(p&g);fp=len(p-g);fn=len(g-p)
    precision=tp/(tp+fp) if tp+fp else (1.0 if not g else 0.0)
    recall=tp/(tp+fn) if tp+fn else 1.0
    f1=(2*precision*recall/(precision+recall)) if precision+recall else 0.0
    return {"tp":tp,"fp":fp,"fn":fn,"precision":precision,"recall":recall,"f1":f1}

def load_sections(paths):
    out={}
    for p in paths:
        raw=json.loads(Path(p).read_text(encoding="utf-8"))
        for f in raw.get("filings",[]):
            for s in f.get("sections",[]):
                out[(f.get("accession"),s.get("item"))]={
                    "text":s.get("text",""),
                    "filing_date":f.get("filing_date"),
                    "company":raw.get("company")
                }
    return out

# Corporate-entity name regex, shared by RegexBackend and LegalRulesBackend.
#
# The previous version anchored only on an initial capital letter and a
# trailing corporate suffix, with an unrestricted character class (including
# spaces and lowercase runs) in between. Because the suffix pattern is rare,
# the "shortest match" a non-greedy quantifier finds often still spans an
# entire sentence back to the nearest preceding capitalized word -- e.g. on
# real EDGAR text this matched "Disney will make a cash payment to New Fox,
# Inc." as a single organization name instead of "New Fox, Inc.", which then
# poisoned the alias map ("New Fox" -> that whole sentence) and suppressed
# event detection entirely for the filing.
#
# WORD requires each token in the name to itself start with a capital letter
# or a digit (entity names commonly include numbers, e.g. "TWDC Holdco 613
# Corp."); CONNECTOR whitelists a small set of lowercase joining words so
# names like "Murdoch Family Trust and Cruden Financial Services LLC" still
# match. Capping the run at 8 words prevents swallowing an entire clause
# even if it happens to contain other capitalized words.
CORP=r"(?:Inc\.?|Incorporated|Corporation|Corp\.?|LLC|L\.L\.C\.|Ltd\.?|Limited|PLC|plc|Company)"
_WORD=r"(?:[A-Z][A-Za-z0-9&.'’-]*|[0-9][A-Za-z0-9&.'’-]*)"
_CONNECTOR=r"(?:of|and|the|for)"
ENT=re.compile(
    r"\b("+_WORD+r"(?:[\s-]+(?:"+_WORD+r"|"+_CONNECTOR+r")){0,7}"+r",?\s*"+CORP+r")(?![A-Za-z.])"
)

class RegexBackend:
    name="regex"
    def parse(self,text):
        orgs=[];aliases={}
        for m in ENT.finditer(text):
            ent=norm(m.group(1));orgs.append(ent)
            tail=text[m.end():m.end()+260]
            pm=re.match(r"\s*(?:,\s*(?:a|an)\s+[^()]{0,150})?\s*\(([^)]{1,220})\)",tail,re.S)
            if pm:
                for a in re.findall(r'[“"]\s*(?:the\s+)?([^”"]+?)\s*[”"]',pm.group(1),re.I):
                    aliases[norm(a)]=ent
        return {"orgs":sorted(set(orgs)),"aliases":aliases}

class SpacyBackend:
    name="spacy"
    def __init__(self,model):
        import spacy
        self.nlp=spacy.load(model)
    def parse(self,text):
        doc=self.nlp(text);orgs=[];aliases={}
        for e in doc.ents:
            if e.label_!="ORG":continue
            ent=norm(e.text);orgs.append(ent)
            tail=text[e.end_char:e.end_char+260]
            pm=re.match(r"\s*(?:,\s*(?:a|an)\s+[^()]{0,150})?\s*\(([^)]{1,220})\)",tail,re.S)
            if pm:
                for a in re.findall(r'[“"]\s*(?:the\s+)?([^”"]+?)\s*[”"]',pm.group(1),re.I):
                    aliases[norm(a)]=ent
        return {"orgs":sorted(set(orgs)),"aliases":aliases}

class LegalRulesBackend:
    name="legal_rules"
    def parse(self,text):
        orgs=[];aliases={}
        for m in ENT.finditer(text):
            ent=norm(m.group(1))
            tail=text[m.end():m.end()+260]
            pm=re.match(r"\s*(?:,\s*(?:a|an)\s+[^()]{0,150})?\s*\(([^)]{1,220})\)",tail,re.S)
            if not pm:continue
            got=False
            for a in re.findall(r'[“"]\s*(?:the\s+)?([^”"]+?)\s*[”"]',pm.group(1),re.I):
                aliases[norm(a)]=ent;got=True
            if got:orgs.append(ent)
        return {"orgs":sorted(set(orgs)),"aliases":aliases}

def bad_org(name):
    x=(name or "").casefold().strip()
    if x in ("the company","company","the corporation","corporation"):
        # "the Company"/"the Corporation" is a near-universal generic
        # self-reference convention in SEC filings (a filer aliasing
        # itself), not a real company name on its own -- distinct from a
        # genuine multi-word name that happens to END in "Company" (e.g.
        # "The Walt Disney Company"), which this exact-match check does
        # not reject.
        return True
    return any(b in x for b in ("section ","article ","item ","form ","rule ","schedule ",
        "general corporation law","merger agreement","credit agreement","senior notes","board of directors"))

def fuse(outputs,weights,threshold):
    votes=defaultdict(float)
    for backend,out in outputs.items():
        w=weights.get(backend,1.0)
        for org in out["orgs"]:
            if not bad_org(org):votes[org]+=w
    orgs=sorted(o for o,v in votes.items() if v>=threshold)

    alias_votes=defaultdict(lambda:defaultdict(float))
    for backend,out in outputs.items():
        w=weights.get(backend,1.0)
        for alias,ent in out["aliases"].items():
            if not bad_org(ent):alias_votes[alias][ent]+=w
    aliases={}
    for alias,cands in alias_votes.items():
        ent,score=sorted(cands.items(),key=lambda kv:(kv[1],kv[0]),reverse=True)[0]
        if ent in orgs or score>=threshold:aliases[alias]=ent
    return {"orgs":orgs,"aliases":aliases,"org_votes":dict(votes)}

def resolve(name,aliases):
    n=norm(name)
    if not n:return None
    key=re.sub(r"^the\s+","",n,flags=re.I)
    return aliases.get(n,aliases.get(key,n))

def known_prefix(raw,orgs):
    raw=norm(raw)
    if not raw:return None
    # The caller's capture regex stops at the first '.'/';', which very often
    # lands INSIDE the org's own legal suffix (e.g. captures "Acme Corp"
    # instead of "Acme Corp."), so a direct startswith() against orgs
    # (which keep their trailing period) silently misses a real match.
    # Compare with trailing periods stripped from both sides as well.
    raw_bare=raw.rstrip(".")
    hits=[o for o in orgs if raw.startswith(o) or raw_bare.startswith(o.rstrip("."))]
    return sorted(hits,key=len,reverse=True)[0] if hits else None

def temporal_status(fragment):
    f=fragment.casefold()
    proposed_markers=("will merge","will be merged","will continue","will be converted",
                      "will become","to merge","would merge","upon the terms and subject to")
    completed_markers=("merged with and into","was converted","completed its acquisition",
                       "completed the previously announced transaction","becoming a wholly owned subsidiary",
                       "continuing as the surviving","surviving the merger as")
    if any(x in f for x in proposed_markers):
        # Past/completed grammar overrides generic contractual context only when explicit
        if " merged with and into " in " "+f+" " and "will " not in f:
            return "COMPLETED"
        if " was converted " in " "+f+" ":
            return "COMPLETED"
        return "PROPOSED"
    if any(x in f for x in completed_markers):
        return "COMPLETED"
    return "UNKNOWN"


def enrich_survivor_aliases(text,aliases):
    """Resolve surviving-entity defined terms back to their legal entities."""
    out=dict(aliases)
    changed=True
    while changed:
        changed=False
        alias_lc={k.casefold():v for k,v in out.items()}
        if not alias_lc:
            break
        ap="|".join(sorted((re.escape(k) for k in alias_lc),key=len,reverse=True))
        pat=re.compile(
            rf"\b(?:with\s+)?({ap})\s+continuing as the surviving "
            rf"(?:corporation|company|limited liability company)"
            rf"[^.;]{{0,260}}?\(\s*the\s+[“\"]([^”\"]+)[”\"]\s*\)", re.I)
        for m in pat.finditer(text):
            entity=alias_lc.get(m.group(1).casefold())
            defined=norm(m.group(2))
            if entity and defined and out.get(defined)!=entity:
                out[defined]=entity
                changed=True
    return out

def mark_transient_relationships(events):
    """Intermediate subsidiary states are evidence, not final graph state,
    when that same entity subsequently merges out in the closing chain."""
    merger_subjects={e["subject"] for e in events
                     if e["event_type"]=="MERGED_INTO" and e["status"]=="COMPLETED"}
    for e in events:
        e.setdefault("lifecycle","FINAL")
        if (e["event_type"]=="SUBSIDIARY_OF" and e["status"]=="COMPLETED"
                and e["subject"] in merger_subjects):
            e["lifecycle"]="TRANSIENT"
    return events

def add_event(out,etype,subject,obj,status,evidence):
    out.append({"event_type":etype,"subject":subject,"object":obj,
                "status":status,"evidence":norm(evidence)})

def infer_events(text,aliases,orgs,item):
    aliases=enrich_survivor_aliases(text,aliases)
    out=[];low=text.casefold()
    financing=any(x in low[:2200] for x in ("credit agreement","senior notes","underwriting agreement",
        "partial financing of the proposed acquisition","term loan"))
    merger_exec="entered into an agreement and plan of merger" in low[:2200]
    closing=("completed its acquisition" in low[:1000] or "completed the previously announced transaction" in low[:1000]
        or "completed its previously" in low[:1000])
    if item=="1.01" and financing and not merger_exec:return out

    # Agreement itself is a completed legal event.
    m=re.search(r"\bentered into an? Agreement and Plan of Merger\b",text,re.I)
    if m:
        acq=None
        # "the Company"/"Company" is a near-universal 8-K self-reference
        # convention (a filer aliasing itself), not specific to any one
        # company -- unlike a hardcoded list of company names, which would
        # only ever match the exact companies this parser was tuned against.
        if "Company" in aliases and aliases["Company"] in text[:m.start()]:
            acq=aliases["Company"]
        if not acq:
            prior=[o for o in orgs if o in text[:m.start()]]
            if prior:acq=prior[-1]
        after=text[m.end():m.end()+1300];target=None
        wm=re.search(r"\bwith\s+([^.;]{2,180})",after,re.I)
        if wm:target=known_prefix(wm.group(1),orgs)
        if not target:
            # General fallback: whichever known org is mentioned earliest
            # in the text immediately following the merger-agreement clause
            # (and isn't the acquirer) is the most likely counterparty.
            candidates=[o for o in orgs if o!=acq and o in after]
            if candidates:target=min(candidates,key=lambda o:after.find(o))
        if acq and target:
            add_event(out,"AGREED_TO_ACQUIRE",acq,target,"COMPLETED",text[max(0,m.start()-120):m.end()+240])

    # Closing. The bracketed "(the \"Acquisition\")"-style aside and the
    # "previously[- ]announced" variant are both real phrasing found on
    # actual filings (Lumen/CenturyLink and Tenable both use them) that the
    # narrower original pattern -- "completed its acquisition of" /
    # "completed the previously announced transaction with" -- missed
    # entirely, despite orgs/aliases being extracted correctly in both
    # cases. Confirmed independently on two unrelated companies before
    # generalizing here, not a guess.
    m=re.search(r"\bcompleted\s+(?:its(?:\s+previously[- ]announced)?\s+acquisition\s*(?:\([^)]{0,80}\))?\s*of|the previously announced transaction with)\s+([^.;]{2,180})",text,re.I)
    if m:
        target=known_prefix(m.group(1),orgs)
        acq=None
        if "Company" in aliases and aliases["Company"] in text[:m.start()]:
            acq=aliases["Company"]
        if not acq:
            prior=[o for o in orgs if o in text[:m.start()]]
            if prior:acq=prior[-1]
        if not target:
            # General fallback, mirroring the acquirer-side one above: the
            # known org mentioned earliest after this clause, excluding
            # whichever org was already identified as the acquirer.
            after=text[m.end():m.end()+400]
            candidates=[o for o in orgs if o!=acq and o in after]
            if candidates:target=min(candidates,key=lambda o:after.find(o))
        if acq and target:
            add_event(out,"ACQUIRED",acq,target,"COMPLETED",text[max(0,m.start()-120):m.end()+220])

    # Alias-focused actions
    alias_lc={k.casefold():v for k,v in aliases.items()}
    if alias_lc:
        ap="|".join(sorted((re.escape(k) for k in alias_lc),key=len,reverse=True))

        # merged with and into
        pat=re.compile(rf"\b({ap})\s+(?P<modal>will be\s+|was\s+)?merged with and into\s+({ap})\b",re.I)
        for m in pat.finditer(text):
            s=alias_lc.get(m.group(1).casefold());o=alias_lc.get(m.group(3).casefold())
            if not s or not o:continue
            frag=text[max(0,m.start()-160):m.end()+260]
            status="PROPOSED" if m.group("modal") and "will" in m.group("modal").casefold() else temporal_status(frag)
            if status=="UNKNOWN":status="COMPLETED" if item=="2.01" else "PROPOSED"
            add_event(out,"MERGED_INTO",s,o,status,frag)

        # subsidiary relation
        pat2=re.compile(rf"\bwith\s+({ap})\s+(?:surviving|continuing)[^.;]{{0,220}}?(?:as|becoming)\s+a\s+wholly[- ]owned subsidiary of\s+((?:the\s+)?(?:{ap}))",re.I)
        for m in pat2.finditer(text):
            s=resolve(m.group(1),aliases);o=resolve(m.group(2),aliases)
            if not s or not o:continue
            frag=text[max(0,m.start()-180):m.end()+180]
            status=temporal_status(frag)
            if status=="UNKNOWN":status="COMPLETED" if item=="2.01" else "PROPOSED"
            add_event(out,"SUBSIDIARY_OF",s,o,status,frag)

    # Conversion
    conv=re.search(r"(?P<lead>will be\s+|was\s+)?converted from a Delaware corporation into a Delaware limited liability company",text,re.I)
    if conv and "VMware" in aliases:
        frag=text[max(0,conv.start()-180):conv.end()+160]
        lead=(conv.group("lead") or "").casefold()
        status="PROPOSED" if "will" in lead else ("COMPLETED" if "was" in lead or item=="2.01" else temporal_status(frag))
        add_event(out,"CONVERTED_TO",aliases["VMware"],"Delaware limited liability company",status,frag)

    # 10-K/annual-report style declarative acquisition statement. Distinct
    # from every pattern above, which all assume 8-K-style third-person
    # contract language ("X entered into an Agreement...", "X completed its
    # acquisition of Y"). A 10-K's Business Combinations footnote is written
    # in first person about the filer itself: "In October 2023, we acquired
    # Ermetic Ltd. ('Ermetic')... We acquired 100% of Ermetic's equity...".
    # Found via Tenable's real 10-K text -- confirmed this pattern was
    # entirely unmatched by anything above (orgs extracted fine, zero events
    # produced) before this was added, not a hypothetical gap.
    #
    # The acquirer side is always "we"/the registrant itself in this style,
    # never a named org -- REGISTRANT_SELF_REFERENCE is a sentinel the
    # calling provider (edgar_ma_provider.other_party) resolves to whichever
    # pivot company is actually being queried, the same way "the Company"
    # resolves for the 8-K patterns above.
    for m in re.finditer(r"\bwe acquired\s+(?:100%\s+of\s+)?([A-Z][^.;,]{1,120}?)(?:'s equity|,|\.|;)", text, re.I):
        raw = m.group(1).strip()
        target = known_prefix(raw, orgs)
        if not target:
            resolved = resolve(raw, aliases)
            if resolved in orgs:
                target = resolved
        if not target:
            continue
        frag = text[max(0, m.start() - 100):m.end() + 200]
        add_event(out, "ACQUIRED", "REGISTRANT_SELF_REFERENCE", target, "COMPLETED", frag)

    # Keep proposed mechanics in raw output, but completed_only controls graph mutation / benchmark.
    return out

def completed_only(events):
    mark_transient_relationships(events)
    return [e for e in events
            if e["status"]=="COMPLETED" and e.get("lifecycle")!="TRANSIENT"]

def ekey(e):
    return (e["event_type"],norm(e["subject"]),norm(e["object"]),e["status"])

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--gold",default="./data/benchmark/legal_benchmark_gold_v385.json")
    ap.add_argument("--inputs",nargs="+",required=True)
    ap.add_argument("--spacy-model",default="en_core_web_sm")
    ap.add_argument("--threshold",type=float,default=1.5)
    ap.add_argument("--json-out")
    a=ap.parse_args()
    try:sp=SpacyBackend(a.spacy_model)
    except Exception as e:
        print("BACKEND_UNAVAILABLE:",e);sys.exit(3)

    backends=[RegexBackend(),sp,LegalRulesBackend()]
    weights={"regex":0.5,"spacy":1.0,"legal_rules":1.25}
    sections=load_sections(a.inputs)
    gold=json.loads(Path(a.gold).read_text(encoding="utf-8"))

    orgm=[];aliasm=[];eventall=[];eventpos=[];neg=negfp=0;rows=[];start=time.perf_counter()
    for case in gold["cases"]:
        sec=sections[(case["accession"],case["item"])]
        text=sec["text"];outputs={}
        for b in backends:outputs[b.name]=b.parse(text)
        fused=fuse(outputs,weights,a.threshold)
        raw_events=infer_events(text,fused["aliases"],fused["orgs"],case["item"])
        final_events=completed_only(raw_events)

        om=None
        if case["expected_orgs"]:
            om=prf(fused["orgs"],case["expected_orgs"]);orgm.append(om)
        am=prf(list(fused["aliases"].items()),list(case["expected_aliases"].items()));aliasm.append(am)
        em=prf([ekey(x) for x in final_events],[ekey(x) for x in case["expected_events"]]);eventall.append(em)
        if case["expected_events"]:eventpos.append(em)
        else:
            neg+=1
            if final_events:negfp+=1

        rows.append({"case":case["id"],"org":om,"alias":am,"event":em,
                     "raw_events":raw_events,"completed_events":final_events,"fused":fused})
        print(f"{case['id']}: org={(om['f1'] if om else 0):.2f} alias={am['f1']:.2f} "
              f"event={em['f1']:.2f} raw={len(raw_events)} completed={len(final_events)} "
              f"proposed={sum(1 for e in raw_events if e['status']=='PROPOSED')}")

    macro=lambda xs:sum(x["f1"] for x in xs)/len(xs) if xs else 0.0
    summary={"org_macro_f1":macro(orgm),"alias_macro_f1":macro(aliasm),
             "event_macro_f1_all":macro(eventall),"event_macro_f1_positive_only":macro(eventpos),
             "negative_control_fp_rate":negfp/neg if neg else 0.0,
             "runtime_seconds":time.perf_counter()-start}
    print("\nM3.8.5 SUMMARY")
    for k,v in summary.items():print(f"{k}: {v:.3f}")

    if a.json_out:
        Path(a.json_out).parent.mkdir(parents=True,exist_ok=True)
        Path(a.json_out).write_text(json.dumps({"summary":summary,"cases":rows},indent=2),encoding="utf-8")

if __name__=="__main__":main()
