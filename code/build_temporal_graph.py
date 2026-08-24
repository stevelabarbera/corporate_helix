#!/usr/bin/env python3
"""M3.8.2 — build a temporal corporate graph from canonical M&A events."""

import argparse, json, hashlib
from pathlib import Path
from datetime import datetime

def _id(prefix, *parts):
    raw="|".join("" if p is None else str(p) for p in parts)
    return f"{prefix}:"+hashlib.sha256(raw.encode()).hexdigest()[:20]

def _entity_key(name):
    return (name or "").strip().casefold()

def _ensure_node(nodes_by_key, nodes, name, first_seen, role="ENTITY", metadata=None):
    if not name:
        return None
    k=_entity_key(name)
    if k in nodes_by_key:
        node=nodes_by_key[k]
        if first_seen and (node.get("first_seen") is None or first_seen < node["first_seen"]):
            node["first_seen"]=first_seen
        return node["node_id"]
    node_id=_id("node",name)
    node={
        "node_id":node_id,
        "canonical_name":name,
        "entity_key":k,
        "role":role,
        "first_seen":first_seen,
        "last_seen":None,
        "states":[],
        "metadata":metadata or {}
    }
    nodes.append(node); nodes_by_key[k]=node
    return node_id

def _add_state(node, effective_date, state_type, value, source_event_id):
    node["states"].append({
        "effective_date":effective_date,
        "state_type":state_type,
        "value":value,
        "source_event_id":source_event_id
    })

def _node_lookup(nodes):
    return {n["node_id"]:n for n in nodes}

def _edge(edges, edge_type, subject_id, object_id, effective_date, source_event_id, metadata=None, end_date=None):
    if not subject_id or not object_id:
        return
    edges.append({
        "edge_id":_id("edge",edge_type,subject_id,object_id,effective_date,source_event_id),
        "edge_type":edge_type,
        "subject_node_id":subject_id,
        "object_node_id":object_id,
        "effective_date":effective_date,
        "end_date":end_date,
        "source_event_id":source_event_id,
        "metadata":metadata or {}
    })

def build(canonical):
    nodes=[]; nodes_by_key={}; edges=[]; events=[]
    event_rows=sorted(canonical.get("events",[]), key=lambda e:(e.get("effective_date") or "", e.get("event_id") or ""))

    for ev in event_rows:
        eid=ev["event_id"]
        d=ev.get("effective_date")
        t=ev.get("event_type")
        p=ev.get("parties") or {}
        md=ev.get("metadata") or {}

        acq_id=_ensure_node(nodes_by_key,nodes,p.get("acquirer"),d,"COMPANY")
        tgt_id=_ensure_node(nodes_by_key,nodes,p.get("target"),d,"COMPANY")
        sub_id=_ensure_node(nodes_by_key,nodes,p.get("subject"),d)
        obj_id=_ensure_node(nodes_by_key,nodes,p.get("object_entity"),d)
        res_id=_ensure_node(nodes_by_key,nodes,p.get("result_entity"),d)

        events.append({
            "event_id":eid,
            "event_type":t,
            "effective_date":d,
            "provenance":ev.get("provenance") or {},
            "confidence":ev.get("confidence"),
            "reason":ev.get("reason"),
            "metadata":md
        })

        lookup=_node_lookup(nodes)

        if t=="AGREED_TO_ACQUIRE":
            _edge(edges,"AGREED_TO_ACQUIRE",acq_id,tgt_id,d,eid,md)

        elif t=="ACQUIRED":
            _edge(edges,"ACQUIRED",acq_id,tgt_id,d,eid,md)
            _edge(edges,"CORPORATE_OWNS",acq_id,tgt_id,d,eid,{"derived_from":"ACQUIRED"})

        elif t=="SUBSIDIARY_OF":
            _edge(edges,"SUBSIDIARY_OF",sub_id,obj_id,d,eid,md)
            _edge(edges,"CORPORATE_OWNS",obj_id,sub_id,d,eid,{"derived_from":"SUBSIDIARY_OF"})

        elif t=="MERGED_INTO":
            _edge(edges,"MERGED_INTO",sub_id,obj_id,d,eid,md)
            if sub_id and obj_id and sub_id != obj_id:
                lookup[sub_id]["last_seen"]=d
                _add_state(lookup[sub_id],d,"LEGAL_STATUS","MERGED_OUT",eid)
                _add_state(lookup[obj_id],d,"LEGAL_STATUS","SURVIVING_ENTITY",eid)

        elif t=="CONVERTED_TO":
            if sub_id:
                _add_state(lookup[sub_id],d,"LEGAL_FORM",{
                    "from":md.get("from_legal_form"),
                    "to":md.get("to_legal_form"),
                    "result_name_explicitly_stated":md.get("result_name_explicitly_stated")
                },eid)
            if sub_id and res_id and sub_id != res_id:
                _edge(edges,"CONVERTED_TO",sub_id,res_id,d,eid,md)
                lookup[sub_id]["last_seen"]=d

        elif t=="RENAMED_TO":
            if sub_id and res_id:
                _edge(edges,"RENAMED_TO",sub_id,res_id,d,eid,md)
                lookup[sub_id]["last_seen"]=d

    for n in nodes:
        n["states"]=sorted(n["states"], key=lambda s:(s["effective_date"] or "",s["state_type"]))

    return {
        "schema_version":"m3.8.2-temporal-graph-v1",
        "source_company":canonical.get("source_company"),
        "source_cik":canonical.get("source_cik"),
        "nodes":nodes,
        "edges":edges,
        "events":events,
        "summary":{
            "node_count":len(nodes),
            "edge_count":len(edges),
            "event_count":len(events)
        }
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--events",required=True)
    ap.add_argument("--out",required=True)
    a=ap.parse_args()
    canonical=json.loads(Path(a.events).read_text(encoding="utf-8"))
    graph=build(canonical)
    Path(a.out).parent.mkdir(parents=True,exist_ok=True)
    Path(a.out).write_text(json.dumps(graph,indent=2,ensure_ascii=False),encoding="utf-8")
    s=graph["summary"]
    print(f"Wrote temporal graph: {s['node_count']} nodes, {s['edge_count']} edges, {s['event_count']} events -> {a.out}")

if __name__=="__main__":
    main()
