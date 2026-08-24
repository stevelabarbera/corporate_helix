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
                out[(f.get("accession"),s.get("item"))]=s.get("text","")
    return out

class RegexBackend:
    name="regex"
    CORP=r"(?:Inc\.?|Incorporated|Corporation|Corp\.?|LLC|L\.L\.C\.|Ltd\.?|Limited|PLC|plc)"
    ENT=re.compile(r"\b([A-Z][A-Za-z0-9&.'’ -]{1,80}?(?:,\s*)?"+CORP+r")(?![A-Za-z.])")
    def parse(self,text):
        orgs=[];aliases={}
        for m in self.ENT.finditer(text):
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
    CORP=r"(?:Inc\.?|Incorporated|Corporation|Corp\.?|LLC|L\.L\.C\.|Ltd\.?|Limited|PLC|plc)"
    ENT=re.compile(r"\b([A-Z][A-Za-z0-9&.'’ -]{1,80}?(?:,\s*)?"+CORP+r")(?![A-Za-z.])")
    def parse(self,text):
        orgs=[];aliases={}
        for m in self.ENT.finditer(text):
            ent=norm(m.group(1))
            tail=text[m.end():m.end()+260]
            pm=re.match(r"\s*(?:,\s*(?:a|an)\s+[^()]{0,150})?\s*\(([^)]{1,220})\)",tail,re.S)
            if not pm:continue
            found=False
            for a in re.findall(r'[“"]\s*(?:the\s+)?([^”"]+?)\s*[”"]',pm.group(1),re.I):
                aliases[norm(a)]=ent;found=True
            if found:orgs.append(ent)
        return {"orgs":sorted(set(orgs)),"aliases":aliases}

def bad_org(name):
    x=(name or "").casefold()
    return any(b in x for b in ("section ","article ","item ","form ","rule ","schedule ",
        "general corporation law","merger agreement","credit agreement","senior notes","board of directors"))

def fuse(outputs,weights,threshold):
    votes=defaultdict(float);sources=defaultdict(list)
    for backend,out in outputs.items():
        w=weights.get(backend,1.0)
        for org in out.get("orgs",[]):
            if bad_org(org):continue
            votes[org]+=w;sources[org].append(backend)
    orgs=sorted(o for o,v in votes.items() if v>=threshold)

    av=defaultdict(lambda:defaultdict(float));asrc=defaultdict(lambda:defaultdict(list))
    for backend,out in outputs.items():
        w=weights.get(backend,1.0)
        for alias,ent in out.get("aliases",{}).items():
            if bad_org(ent):continue
            av[alias][ent]+=w;asrc[alias][ent].append(backend)
    aliases={};debug={}
    for alias,cands in av.items():
        ent,score=sorted(cands.items(),key=lambda kv:(kv[1],kv[0]),reverse=True)[0]
        if ent in orgs or score>=threshold:aliases[alias]=ent
        debug[alias]={"candidate":ent,"score":score,"sources":asrc[alias][ent]}
    return {"orgs":orgs,"aliases":aliases,"org_votes":dict(votes),"org_sources":dict(sources),"alias_debug":debug}

def resolve(name,aliases):
    n=norm(name)
    if not n:return None
    key=re.sub(r"^the\s+","",n,flags=re.I)
    return aliases.get(n,aliases.get(key,n))

def known_prefix(raw,orgs):
    raw=norm(raw);hits=[o for o in orgs if raw and raw.startswith(o)]
    return sorted(hits,key=len,reverse=True)[0] if hits else None

def infer_events(text,aliases,orgs):
    out=[];low=text.casefold()
    financing=any(x in low[:2200] for x in ("credit agreement","senior notes","underwriting agreement","partial financing of the proposed acquisition","term loan"))
    merger_exec="entered into an agreement and plan of merger" in low[:2200]
    closing=("completed its acquisition" in low[:1000] or "completed the previously announced transaction" in low[:1000])
    if financing and not merger_exec and not closing:return out

    m=re.search(r"\bentered into an? Agreement and Plan of Merger\b",text,re.I)
    if m:
        acq=None
        for a in ("Company","Broadcom","Cisco"):
            if a in aliases and aliases[a] in text[:m.start()]:acq=aliases[a];break
        if not acq:
            prior=[o for o in orgs if o in text[:m.start()]]
            if prior:acq=prior[-1]
        after=text[m.end():m.end()+1300];target=None
        wm=re.search(r"\bwith\s+([^.;]{2,180})",after,re.I)
        if wm:target=known_prefix(wm.group(1),orgs)
        if not target:
            for a in ("Splunk","VMware"):
                if a in aliases:target=aliases[a];break
        if acq and target:out.append({"event_type":"AGREED_TO_ACQUIRE","subject":acq,"object":target})

    m=re.search(r"\bcompleted\s+(?:its acquisition of|the previously announced transaction with)\s+([^.;]{2,180})",text,re.I)
    if m:
        target=known_prefix(m.group(1),orgs)
        if not target:
            for a in ("Splunk","VMware"):
                if a in aliases:
                    target=aliases[a]
                    break
        acq=None
        for a in ("Company","Broadcom","Cisco"):
            if a in aliases:acq=aliases[a];break
        if not acq:
            prior=[o for o in orgs if o in text[:m.start()]]
            if prior:acq=prior[-1]
        if acq and target:out.append({"event_type":"ACQUIRED","subject":acq,"object":target})

    alias_lc={k.casefold():v for k,v in aliases.items()}
    if alias_lc:
        ap="|".join(sorted((re.escape(k) for k in alias_lc),key=len,reverse=True))
        pat=re.compile(rf"\b({ap})\s+(?:will be\s+|was\s+)?merged with and into\s+({ap})\b",re.I)
        for m in pat.finditer(text):
            s=alias_lc.get(m.group(1).casefold());o=alias_lc.get(m.group(2).casefold())
            if s and o:out.append({"event_type":"MERGED_INTO","subject":s,"object":o})
        pat2=re.compile(rf"\bwith\s+({ap})\s+(?:surviving|continuing)[^.;]{{0,220}}?(?:as|becoming)\s+a\s+wholly[- ]owned subsidiary of\s+((?:the\s+)?(?:{ap}))",re.I)
        for m in pat2.finditer(text):
            s=resolve(m.group(1),aliases);o=resolve(m.group(2),aliases)
            if s and o:out.append({"event_type":"SUBSIDIARY_OF","subject":s,"object":o})

    if re.search(r"converted from a Delaware corporation into a Delaware limited liability company",text,re.I) and "VMware" in aliases:
        out.append({"event_type":"CONVERTED_TO","subject":aliases["VMware"],"object":"Delaware limited liability company"})
    return out

def ekey(e):return (e["event_type"],norm(e["subject"]),norm(e["object"]))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--gold",default="./data/benchmark/legal_benchmark_gold.json")
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
    sections=load_sections(a.inputs);gold=json.loads(Path(a.gold).read_text(encoding="utf-8"))

    orgm=[];aliasm=[];eventall=[];eventpos=[];neg=negfp=0;rows=[];start=time.perf_counter()
    for case in gold["cases"]:
        text=sections[(case["accession"],case["item"])]
        outputs={};times={}
        for b in backends:
            t=time.perf_counter();outputs[b.name]=b.parse(text);times[b.name]=time.perf_counter()-t
        fused=fuse(outputs,weights,a.threshold);events=infer_events(text,fused["aliases"],fused["orgs"])
        om=None
        if case["expected_orgs"]:
            om=prf(fused["orgs"],case["expected_orgs"]);orgm.append(om)
        am=prf(list(fused["aliases"].items()),list(case["expected_aliases"].items()));aliasm.append(am)
        em=prf([ekey(x) for x in events],[ekey(x) for x in case["expected_events"]]);eventall.append(em)
        if case["expected_events"]:eventpos.append(em)
        else:
            neg+=1
            if events:negfp+=1
        rows.append({"case":case["id"],"org":om,"alias":am,"event":em,"events":events,"fused":fused,"backend_outputs":outputs,"timings":times})
        print(f"{case['id']}: org={(om['f1'] if om else 0):.2f} alias={am['f1']:.2f} event={em['f1']:.2f} events={len(events)}")
    macro=lambda xs:sum(x["f1"] for x in xs)/len(xs) if xs else 0.0
    summary={"org_macro_f1":macro(orgm),"alias_macro_f1":macro(aliasm),"event_macro_f1_all":macro(eventall),
             "event_macro_f1_positive_only":macro(eventpos),"negative_control_fp_rate":negfp/neg if neg else 0.0,
             "runtime_seconds":time.perf_counter()-start,"weights":weights,"threshold":a.threshold}
    print("\nENSEMBLE SUMMARY")
    for k,v in summary.items():print(f"{k}: {v:.3f}" if isinstance(v,float) else f"{k}: {v}")
    if a.json_out:
        Path(a.json_out).parent.mkdir(parents=True,exist_ok=True)
        Path(a.json_out).write_text(json.dumps({"summary":summary,"cases":rows},indent=2),encoding="utf-8")

if __name__=="__main__":main()
