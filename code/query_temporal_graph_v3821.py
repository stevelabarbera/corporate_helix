#!/usr/bin/env python3
import argparse,json
from pathlib import Path

def existence_status(node,as_of):
    start=node.get("existence_start");end=node.get("existence_end")
    if start and as_of<start:return "NOT_YET_EXISTING"
    if end and as_of>=end:return "ENDED"
    if start is None:return "UNKNOWN_START"
    return "EXISTING"

def edge_in_effect(edge,as_of):
    start=edge.get("effective_date");end=edge.get("end_date")
    if start and as_of<start:return False
    if end and as_of>=end:return False
    return True

def find_node(g,name):
    q=name.casefold().strip()
    exact=[n for n in g.get("nodes",[]) if n.get("canonical_name","").casefold()==q]
    if exact:return exact[0]
    partial=[n for n in g.get("nodes",[]) if q in n.get("canonical_name","").casefold()]
    return partial[0] if len(partial)==1 else None

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--graph",required=True);ap.add_argument("--as-of",required=True);ap.add_argument("--entity");a=ap.parse_args()
    g=json.loads(Path(a.graph).read_text(encoding="utf-8"));ids={n["node_id"]:n for n in g.get("nodes",[])};asof=a.as_of
    if a.entity:
        n=find_node(g,a.entity)
        if not n:raise SystemExit(f"Entity not uniquely found: {a.entity}")
        print(f"Entity: {n['canonical_name']}");print(f"As of: {asof}")
        print(f"Existence status: {existence_status(n,asof)}")
        print(f"Observed in Helix from: {n.get('observed_from')}")
        states=[s for s in n.get("states",[]) if not s.get("effective_date") or s["effective_date"]<=asof]
        if states:
            print("States:")
            for s in states:print(f" - {s['effective_date']} {s['state_type']}: {s['value']}")
        state_edges=[e for e in g.get("edges",[]) if e.get("edge_class")=="STATE" and edge_in_effect(e,asof)
                     and (e["subject_node_id"]==n["node_id"] or e["object_node_id"]==n["node_id"])]
        event_edges=[e for e in g.get("edges",[]) if e.get("edge_class")=="EVENT" and e.get("effective_date")<=asof
                     and (e["subject_node_id"]==n["node_id"] or e["object_node_id"]==n["node_id"])]
        print("State relationships:")
        for e in state_edges:
            print(f" - {ids[e['subject_node_id']]['canonical_name']} --{e['edge_type']}--> {ids[e['object_node_id']]['canonical_name']} [{e['effective_date']}]")
        print("Historical events through date:")
        for e in event_edges:
            print(f" - {e['effective_date']} {ids[e['subject_node_id']]['canonical_name']} --{e['edge_type']}--> {ids[e['object_node_id']]['canonical_name']}")
        return
    print(f"As of {asof}")
    for n in sorted(g.get("nodes",[]),key=lambda x:x["canonical_name"]):
        print(f" - {n['canonical_name']}: {existence_status(n,asof)}")
if __name__=="__main__":main()
