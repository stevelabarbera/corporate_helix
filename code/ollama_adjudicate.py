#!/usr/bin/env python3
import argparse, json, os, urllib.request
from datetime import datetime, timezone

DECISIONS={"SAME_ENTITY","DISTINCT_ENTITY","AMBIGUOUS","CONFLICTING_EVIDENCE"}
CONFIDENCE={"HIGH","MEDIUM","LOW"}

SCHEMA={
  "type":"object",
  "properties":{
    "decision":{"type":"string","enum":sorted(DECISIONS)},
    "confidence":{"type":"string","enum":sorted(CONFIDENCE)},
    "supporting_evidence_ids":{"type":"array","items":{"type":"string"}},
    "conflicting_evidence_ids":{"type":"array","items":{"type":"string"}},
    "rationale":{"type":"string"}
  },
  "required":["decision","confidence","supporting_evidence_ids","conflicting_evidence_ids","rationale"],
  "additionalProperties":False
}

SYSTEM="""You adjudicate corporate identity using ONLY the supplied packet.
Structured facts are authoritative. Never contradict them.
Never invent a country, identifier, former name, registration number, relationship, address, ownership fact, or corporate event.
Do not use similarity, same jurisdiction, or shared address as proof of identity.
If the evidence cannot establish SAME_ENTITY or DISTINCT_ENTITY, return AMBIGUOUS.
Your rationale must agree with your decision:
- SAME_ENTITY rationale must describe evidence of identity/continuity.
- DISTINCT_ENTITY rationale must describe evidence of distinct legal identity.
- AMBIGUOUS rationale must explain what evidence is missing or inconclusive.
A HIGH-confidence SAME_ENTITY conclusion requires identity-grade evidence.
A HIGH-confidence DISTINCT_ENTITY conclusion requires distinctness-grade evidence.
Return only schema-valid JSON."""

def load_jsonl(path):
    if not os.path.exists(path): return []
    with open(path,encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]

def write_jsonl(path,rows):
    os.makedirs(os.path.dirname(path) or ".",exist_ok=True)
    with open(path,"w",encoding="utf-8") as f:
        for x in rows:
            f.write(json.dumps(x,ensure_ascii=False)+"\n")

def _signals(packet):
    return (packet.get("deterministic_evaluation") or {}).get("signals") or {}

def _ctx(packet):
    return packet.get("evidence_summary") or packet.get("graph_context") or {}

def _rat(result):
    return (result.get("rationale") or "").casefold()

def _contains(text,phrases):
    return any(p in text for p in phrases)

def _identity_grade(packet):
    s=_signals(packet)
    keys=[]
    for key in ("exact_provider_identifier","explicit_former_name_match",
                "matching_registration_number","matching_lei","matching_cik",
                "explicit_legal_successor","explicit_legal_continuity"):
        if s.get(key) is True:
            keys.append(key)
    return keys

def _distinctness_grade(packet):
    s=_signals(packet); c=_ctx(packet); keys=[]
    if s.get("provider_identifier_conflict") is True:
        keys.append("provider_identifier_conflict")
    if s.get("jurisdiction_conflict") is True and s.get("exact_legal_name_base") is True:
        keys.append("same_base_different_jurisdiction")
    if c.get("separately_enumerated") is True and c.get("same_source_document") is True:
        keys.append("separately_enumerated_same_source")
    for key in ("conflicting_registration_number","conflicting_lei","conflicting_cik","explicit_distinct_entity_evidence"):
        if s.get(key) is True:
            keys.append(key)
    return keys

def consistency_errors(result,packet):
    errs=[]; s=_signals(packet); c=_ctx(packet); rat=_rat(result)
    valid_ids={e.get("evidence_id") for e in packet.get("evidence") or []}
    if result.get("decision") not in DECISIONS: errs.append("invalid decision")
    if result.get("confidence") not in CONFIDENCE: errs.append("invalid confidence")
    if not (result.get("rationale") or "").strip(): errs.append("missing rationale")
    for field in ("supporting_evidence_ids","conflicting_evidence_ids"):
        vals=result.get(field)
        if not isinstance(vals,list):
            errs.append(f"{field} must be a list"); continue
        bad=[x for x in vals if x not in valid_ids]
        if bad: errs.append(f"{field} contains unknown IDs: {bad}")
    if result.get("decision") in {"SAME_ENTITY","DISTINCT_ENTITY"} and not result.get("supporting_evidence_ids"):
        errs.append("conclusive decision has no supporting evidence IDs")
    if s.get("jurisdiction_match") is True and _contains(rat,(
        "different jurisdiction","different jurisdictions","different country","different countries",
        "separate jurisdictions","separate countries")):
        errs.append("rationale claims jurisdiction difference but jurisdiction_match=true")
    if s.get("jurisdiction_conflict") is True and _contains(rat,(
        "same jurisdiction","same country","matching jurisdiction")):
        errs.append("rationale claims jurisdiction match but jurisdiction_conflict=true")
    if s.get("explicit_former_name_match") is not True and _contains(rat,(
        "former name match","former names match","former name matches","matching former name",
        "same former name","previous name match","formerly known as","former name confirms")):
        errs.append("rationale claims former-name continuity but explicit_former_name_match=false")
    if s.get("shared_address") is not True and _contains(rat,(
        "same address","shared address","matching address","addresses match")):
        errs.append("rationale claims shared address but shared_address=false")
    if s.get("exact_provider_identifier") is not True and _contains(rat,(
        "same identifier","matching identifier","identifier matches","same registration number",
        "matching registration number","same lei","matching lei","same cik","matching cik")):
        errs.append("rationale claims matching identifier but exact_provider_identifier=false")
    if c.get("same_parent") is not True and _contains(rat,("same parent","shared parent","common parent")):
        errs.append("rationale claims shared parent but same_parent=false")
    decision=result.get("decision")
    if decision=="DISTINCT_ENTITY" and _contains(rat,(
        "same legal entity","same entity","identical entity","source entities are identical",
        "records are identical","confirming this is the same entity","confirms identity")):
        errs.append("DISTINCT_ENTITY rationale asserts sameness/identity")
    if decision=="SAME_ENTITY" and _contains(rat,(
        "distinct legal entities","different legal entities","separate legal entities",
        "not the same entity","unrelated entities")):
        errs.append("SAME_ENTITY rationale asserts distinctness")
    identity_grade=_identity_grade(packet); distinct_grade=_distinctness_grade(packet)
    if decision=="SAME_ENTITY" and result.get("confidence")=="HIGH" and not identity_grade:
        errs.append("HIGH-confidence SAME_ENTITY lacks identity-grade evidence")
    if decision=="DISTINCT_ENTITY" and result.get("confidence")=="HIGH" and not distinct_grade:
        errs.append("HIGH-confidence DISTINCT_ENTITY lacks distinctness-grade evidence")
    if decision=="DISTINCT_ENTITY" and not distinct_grade and _contains(rat,(
        "same legal entity","same entity","identical entity","source entities are identical")):
        errs.append("DISTINCT_ENTITY has no distinctness-grade evidence")
    return errs

def compact_facts(packet):
    s=_signals(packet); c=_ctx(packet)
    return {
      "candidate_a_name":(packet.get("candidate_a") or {}).get("canonical_name"),
      "candidate_b_name":(packet.get("candidate_b") or {}).get("canonical_name"),
      "candidate_a_jurisdiction":(packet.get("candidate_a") or {}).get("jurisdiction"),
      "candidate_b_jurisdiction":(packet.get("candidate_b") or {}).get("jurisdiction"),
      "jurisdiction_match":s.get("jurisdiction_match"),
      "jurisdiction_conflict":s.get("jurisdiction_conflict"),
      "exact_legal_name_base":s.get("exact_legal_name_base"),
      "shared_address":s.get("shared_address"),
      "shared_addresses":s.get("shared_addresses") or [],
      "exact_provider_identifier":s.get("exact_provider_identifier"),
      "provider_identifier_conflict":s.get("provider_identifier_conflict"),
      "explicit_former_name_match":s.get("explicit_former_name_match"),
      "same_parent":c.get("same_parent"),
      "same_source_document":c.get("same_source_document"),
      "separately_enumerated":c.get("separately_enumerated"),
      "identity_grade_signals":_identity_grade(packet),
      "distinctness_grade_signals":_distinctness_grade(packet)
    }

def call(packet,model,url):
    body={"model":model,"stream":False,"format":SCHEMA,"options":{"temperature":0},
          "messages":[{"role":"system","content":SYSTEM},
                      {"role":"user","content":json.dumps({
                          "structured_facts":compact_facts(packet),
                          "evidence":packet.get("evidence") or [],
                          "question":packet.get("question"),
                          "required_output":SCHEMA},ensure_ascii=False)}]}
    req=urllib.request.Request(url,data=json.dumps(body).encode(),headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=180) as r:
        raw=json.loads(r.read().decode())
    return json.loads(raw["message"]["content"])

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--pending",default="./data/review/pending.jsonl")
    ap.add_argument("--packet-id")
    ap.add_argument("--model",required=True)
    ap.add_argument("--url",default="http://localhost:11434/api/chat")
    ap.add_argument("--out",default="./data/review/llm_adjudicated.jsonl")
    a=ap.parse_args()
    rows=load_jsonl(a.pending)
    if not rows: raise SystemExit("No pending packets")
    packet=next((p for p in rows if not a.packet_id or p.get("packet_id")==a.packet_id),None)
    if not packet: raise SystemExit("Packet not found")
    result=call(packet,a.model,a.url)
    errs=consistency_errors(result,packet)
    validation="VALID" if not errs else "INVALID"
    record={"packet_id":packet["packet_id"],"model":a.model,
            "adjudicated_at":datetime.now(timezone.utc).isoformat(),
            "result":result,"validation_status":validation,"validation_errors":errs,
            "identity_grade_signals":_identity_grade(packet),
            "distinctness_grade_signals":_distinctness_grade(packet),
            "schema_version":"m3.6-llm-adjudication-v3.1"}
    out=load_jsonl(a.out); out.append(record); write_jsonl(a.out,out)
    for p in rows:
        if p.get("packet_id")==packet["packet_id"]:
            p.setdefault("adjudication",{})["llm"]=record
            p["adjudication"]["status"]="LLM_ADJUDICATED_PENDING_HUMAN" if not errs else "LLM_INVALID_REMAINS_REVIEW"
    write_jsonl(a.pending,rows)
    print(f"LLM -> {result.get('decision')} / {result.get('confidence')} | validation={validation}")
    print("Rationale:",result.get("rationale"))
    print("Identity-grade signals:",_identity_grade(packet) or "NONE")
    print("Distinctness-grade signals:",_distinctness_grade(packet) or "NONE")
    if errs:
        print("Validation errors:")
        for e in errs: print(" -",e)
        print("Final graph action: NONE; deterministic REVIEW remains in force.")
    else:
        print("Evidence-backed model advice stored; no automatic graph mutation.")

if __name__=="__main__":
    main()
