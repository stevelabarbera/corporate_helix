#!/usr/bin/env python3
import argparse,json,hashlib
from pathlib import Path

def _id(prefix,*parts):
    raw="|".join("" if p is None else str(p) for p in parts)
    return f"{prefix}:"+hashlib.sha256(raw.encode()).hexdigest()[:20]

def _key(name): return (name or "").strip().casefold()

def ensure_node(by_key,nodes,name,observed_from,role="ENTITY"):
    if not name:return None
    k=_key(name)
    if k in by_key:
        n=by_key[k]
        if observed_from and (n.get("observed_from") is None or observed_from<n["observed_from"]):
            n["observed_from"]=observed_from
        return n["node_id"]
    n={"node_id":_id("node",name),"canonical_name":name,"entity_key":k,"role":role,
       "observed_from":observed_from,"existence_start":None,"existence_end":None,
       "states":[],"metadata":{"existence_start_known":False}}
    nodes.append(n);by_key[k]=n
    return n["node_id"]

def add_state(node,date,state_type,value,event_id):
    node["states"].append({"effective_date":date,"state_type":state_type,"value":value,"source_event_id":event_id})

def add_edge(edges,etype,sid,oid,date,event_id,metadata=None,end_date=None,edge_class="STATE"):
    if not sid or not oid:return
    edges.append({"edge_id":_id("edge",etype,sid,oid,date,event_id),"edge_type":etype,
                  "edge_class":edge_class,"subject_node_id":sid,"object_node_id":oid,
                  "effective_date":date,"end_date":end_date,"source_event_id":event_id,
                  "metadata":metadata or {}})

def build(canonical):
    nodes=[];by_key={};edges=[];events=[];pending={}
    rows=sorted(canonical.get("events",[]),key=lambda e:(e.get("effective_date") or "",e.get("event_id") or ""))
    for ev in rows:
        eid=ev["event_id"];d=ev.get("effective_date");t=ev.get("event_type")
        p=ev.get("parties") or {};md=ev.get("metadata") or {}
        acq=ensure_node(by_key,nodes,p.get("acquirer"),d,"COMPANY")
        tgt=ensure_node(by_key,nodes,p.get("target"),d,"COMPANY")
        sub=ensure_node(by_key,nodes,p.get("subject"),d)
        obj=ensure_node(by_key,nodes,p.get("object_entity"),d)
        res=ensure_node(by_key,nodes,p.get("result_entity"),d)
        events.append({"event_id":eid,"event_type":t,"effective_date":d,
                       "provenance":ev.get("provenance") or {},"confidence":ev.get("confidence"),
                       "reason":ev.get("reason"),"metadata":md})
        lookup={n["node_id"]:n for n in nodes}
        if t=="AGREED_TO_ACQUIRE":
            add_edge(edges,t,acq,tgt,d,eid,md,edge_class="EVENT")
            if acq and tgt: pending[(acq,tgt)]=len(edges)-1
        elif t=="ACQUIRED":
            add_edge(edges,t,acq,tgt,d,eid,md,edge_class="EVENT")
            add_edge(edges,"CORPORATE_OWNS",acq,tgt,d,eid,{"derived_from":"ACQUIRED"},edge_class="STATE")
            idx=pending.get((acq,tgt))
            if idx is not None:
                edges[idx]["end_date"]=d
                edges[idx]["metadata"]["closed_by_event_id"]=eid
        elif t=="SUBSIDIARY_OF":
            add_edge(edges,t,sub,obj,d,eid,md,edge_class="STATE")
            add_edge(edges,"CORPORATE_OWNS",obj,sub,d,eid,{"derived_from":"SUBSIDIARY_OF"},edge_class="STATE")
        elif t=="MERGED_INTO":
            add_edge(edges,t,sub,obj,d,eid,md,edge_class="EVENT")
            if sub and obj and sub!=obj:
                lookup[sub]["existence_end"]=d
                add_state(lookup[sub],d,"LEGAL_STATUS","MERGED_OUT",eid)
                add_state(lookup[obj],d,"LEGAL_STATUS","SURVIVING_ENTITY",eid)
        elif t=="CONVERTED_TO":
            if sub:
                add_state(lookup[sub],d,"LEGAL_FORM",{"from":md.get("from_legal_form"),
                                                     "to":md.get("to_legal_form"),
                                                     "result_name_explicitly_stated":md.get("result_name_explicitly_stated")},eid)
            if sub and res and sub!=res:
                add_edge(edges,t,sub,res,d,eid,md,edge_class="EVENT")
                lookup[sub]["existence_end"]=d
        elif t=="RENAMED_TO" and sub and res:
            add_edge(edges,t,sub,res,d,eid,md,edge_class="EVENT")
            lookup[sub]["existence_end"]=d
    for n in nodes:
        n["states"]=sorted(n["states"],key=lambda s:(s["effective_date"] or "",s["state_type"]))
    return {"schema_version":"m3.8.2.1-temporal-graph-v1","source_company":canonical.get("source_company"),
            "source_cik":canonical.get("source_cik"),"nodes":nodes,"edges":edges,"events":events,
            "summary":{"node_count":len(nodes),"edge_count":len(edges),"event_count":len(events)}}

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--events",required=True);ap.add_argument("--out",required=True);a=ap.parse_args()
    c=json.loads(Path(a.events).read_text(encoding="utf-8"));g=build(c)
    Path(a.out).parent.mkdir(parents=True,exist_ok=True)
    Path(a.out).write_text(json.dumps(g,indent=2,ensure_ascii=False),encoding="utf-8")
    s=g["summary"];print(f"Wrote temporal graph: {s['node_count']} nodes, {s['edge_count']} edges, {s['event_count']} events -> {a.out}")
if __name__=="__main__":main()
