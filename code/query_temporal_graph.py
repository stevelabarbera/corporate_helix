#!/usr/bin/env python3
"""Point-in-time queries for M3.8.2 temporal graph."""

import argparse, json
from pathlib import Path

def active_node(node, as_of):
    fs=node.get("first_seen")
    ls=node.get("last_seen")
    if fs and as_of < fs:
        return False
    if ls and as_of >= ls:
        return False
    return True

def edge_active(edge, as_of):
    start=edge.get("effective_date")
    end=edge.get("end_date")
    if start and as_of < start:
        return False
    if end and as_of >= end:
        return False
    return True

def node_by_name(graph, name):
    q=name.casefold().strip()
    exact=[n for n in graph.get("nodes",[]) if n.get("canonical_name","").casefold()==q]
    if exact:return exact[0]
    partial=[n for n in graph.get("nodes",[]) if q in n.get("canonical_name","").casefold()]
    return partial[0] if len(partial)==1 else None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--graph",required=True)
    ap.add_argument("--as-of",required=True)
    ap.add_argument("--entity")
    a=ap.parse_args()

    g=json.loads(Path(a.graph).read_text(encoding="utf-8"))
    asof=a.as_of
    ids={n["node_id"]:n for n in g.get("nodes",[])}

    if a.entity:
        n=node_by_name(g,a.entity)
        if not n:
            raise SystemExit(f"Entity not uniquely found: {a.entity}")
        print(f"Entity: {n['canonical_name']}")
        print(f"As of: {asof}")
        print(f"Active: {active_node(n,asof)}")
        states=[s for s in n.get("states",[]) if not s.get("effective_date") or s["effective_date"]<=asof]
        if states:
            print("States:")
            for s in states:
                print(f" - {s['effective_date']} {s['state_type']}: {s['value']}")
        rels=[e for e in g.get("edges",[]) if edge_active(e,asof) and (e["subject_node_id"]==n["node_id"] or e["object_node_id"]==n["node_id"])]
        print("Relationships:")
        for e in rels:
            subj=ids[e["subject_node_id"]]["canonical_name"]
            obj=ids[e["object_node_id"]]["canonical_name"]
            print(f" - {subj} --{e['edge_type']}--> {obj} [{e['effective_date']}]")
        return

    active=[n for n in g.get("nodes",[]) if active_node(n,asof)]
    active_ids={n["node_id"] for n in active}
    print(f"As of {asof}: {len(active)} active node(s)")
    for n in sorted(active,key=lambda x:x["canonical_name"]):
        print(" -",n["canonical_name"])
    print("Active relationships:")
    for e in g.get("edges",[]):
        if edge_active(e,asof) and e["subject_node_id"] in active_ids and e["object_node_id"] in active_ids:
            print(f" - {ids[e['subject_node_id']]['canonical_name']} --{e['edge_type']}--> {ids[e['object_node_id']]['canonical_name']}")

if __name__=="__main__":
    main()
