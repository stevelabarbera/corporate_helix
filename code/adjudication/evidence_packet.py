from __future__ import annotations
from datetime import datetime, timezone
import hashlib, json

def _stable_id(*parts):
    raw="|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]

def _public_node(n):
    return {k:n.get(k) for k in (
        "node_id","canonical_name","canonical_name_normalized",
        "legal_name_base","jurisdiction","jurisdiction_raw",
        "provider_entity_ids","aliases","roles"
    )}

def _parent_edges(graph,node_id):
    return [
        r for r in graph.get("relationships",[])
        if r.get("subject_node_id")==node_id and r.get("predicate")=="SUBSIDIARY_OF"
    ]

def _iter_evidence(rel):
    """
    Relationship evidence may be:
      - a list of evidence dicts (current resolved graph)
      - a single evidence dict (older/alternate shape)
      - missing/None
    Normalize to an iterable of dictionaries.
    """
    ev = rel.get("evidence")
    if isinstance(ev, list):
        for item in ev:
            if isinstance(item, dict):
                yield item
    elif isinstance(ev, dict):
        yield ev

def _source_keys(rel):
    """
    Return all useful source fingerprints for a relationship.
    We intentionally keep multiple fingerprints because a relationship can
    carry more than one evidence record after cross-provider corroboration.
    """
    keys = []

    # Relationship-level fallback values.
    rel_provider = rel.get("provider")
    rel_accession = rel.get("accession")
    rel_source_url = rel.get("source_url")
    rel_effective = rel.get("effective_date")

    found = False
    for ev in _iter_evidence(rel):
        found = True
        keys.append({
            "provider": ev.get("provider") or rel_provider,
            "accession": (
                ev.get("source_document_id")
                or ev.get("accession")
                or rel_accession
            ),
            "source_url": ev.get("source_url") or rel_source_url,
            "effective_date": (
                ev.get("as_of_date")
                or ev.get("effective_date")
                or rel_effective
            ),
        })

    if not found:
        keys.append({
            "provider": rel_provider,
            "accession": rel_accession,
            "source_url": rel_source_url,
            "effective_date": rel_effective,
        })

    return keys

def _same_source_document(left_rel, right_rel):
    """
    True when two relationships share a meaningful source-document locator.
    Provider equality alone is not enough.
    """
    left_keys = _source_keys(left_rel)
    right_keys = _source_keys(right_rel)

    for a in left_keys:
        for b in right_keys:
            if a.get("accession") and a["accession"] == b.get("accession"):
                return True
            if a.get("source_url") and a["source_url"] == b.get("source_url"):
                return True
    return False

def _graph_context(graph,left,right):
    la=_parent_edges(graph,left.get("node_id"))
    rb=_parent_edges(graph,right.get("node_id"))

    lp={r.get("object_node_id") for r in la if r.get("object_node_id")}
    rp={r.get("object_node_id") for r in rb if r.get("object_node_id")}
    shared=sorted(lp & rp)

    same_source = any(
        _same_source_document(a,b)
        for a in la
        for b in rb
    )

    def ownership(edges):
        vals=[]
        for r in edges:
            v=r.get("ownership_percent")
            if v is not None:
                vals.append(v)
        return vals

    return {
        "same_parent": bool(shared),
        "shared_parent_node_ids": shared,
        "both_have_explicit_subsidiary_edges": bool(la and rb),
        "same_source_document": same_source,
        "separately_enumerated": bool(
            left.get("node_id") != right.get("node_id") and la and rb
        ),
        "candidate_a_ownership_percentages": ownership(la),
        "candidate_b_ownership_percentages": ownership(rb),
        "candidate_a_jurisdiction": left.get("jurisdiction"),
        "candidate_b_jurisdiction": right.get("jurisdiction"),
    }

def _collect_evidence(graph,left,right):
    evidence=[]; seen=set()

    def add(kind,source_node_id,item):
        payload=json.dumps(item,sort_keys=True,ensure_ascii=False,default=str)
        eid="ev:"+_stable_id(kind,source_node_id,payload)
        if eid in seen:
            return
        seen.add(eid)
        evidence.append({
            "evidence_id":eid,
            "evidence_type":kind,
            "source_node_id":source_node_id,
            "payload":item
        })

    for n in (left,right):
        for ent in n.get("source_entities") or []:
            add("source_entity",n.get("node_id"),ent)

    ids={left.get("node_id"),right.get("node_id")}
    for rel in graph.get("relationships") or []:
        if rel.get("subject_node_id") in ids or rel.get("object_node_id") in ids:
            add("graph_relationship",None,rel)

    return evidence

def build_evidence_packet(graph,left,right,evaluation,policy_name=None):
    policy=policy_name or evaluation.get("policy")
    if not policy:
        raise ValueError("policy required")

    ctx=_graph_context(graph,left,right)

    packet_id="pkt:"+_stable_id(
        policy,
        left.get("node_id"),
        right.get("node_id"),
        evaluation.get("decision"),
        evaluation.get("resolution_reason")
    )

    return {
      "schema_version":"m3.6-evidence-packet-v2.1",
      "packet_id":packet_id,
      "created_at":datetime.now(timezone.utc).isoformat(),
      "policy":policy,
      "question":(
          "Do these records represent the same legal entity?"
          if policy=="SAME_ENTITY"
          else "Does the supplied evidence support the proposed subsidiary relationship?"
      ),
      "candidate_a":_public_node(left),
      "candidate_b":_public_node(right),
      "deterministic_evaluation":{
        "decision":evaluation.get("decision"),
        "resolution_reason":evaluation.get("resolution_reason"),
        "score":evaluation.get("score"),
        "signals":evaluation.get("signals") or {},
        "hard_confirms":evaluation.get("hard_confirms") or [],
        "hard_conflicts":evaluation.get("hard_conflicts") or [],
        "guard_events":evaluation.get("guard_events") or [],
        "contributions":evaluation.get("contributions") or []
      },
      "graph_context":ctx,
      "evidence_summary":ctx,
      "evidence":_collect_evidence(graph,left,right),
      "model_contract":{
        "reason_only_from_supplied_evidence":True,
        "decision_field":{
          "allowed":["SAME_ENTITY","DISTINCT_ENTITY","AMBIGUOUS","CONFLICTING_EVIDENCE"]
        },
        "confidence_field":{"allowed":["HIGH","MEDIUM","LOW"]},
        "required_fields":[
            "decision","confidence","supporting_evidence_ids",
            "conflicting_evidence_ids","rationale"
        ],
        "prohibited_behavior":[
          "Do not use model memory as evidence.",
          "Do not invent corporate facts.",
          "Do not silently overwrite deterministic decisions."
        ]
      },
      "adjudication":{"status":"PENDING","llm":None,"human":None,"final":None}
    }
