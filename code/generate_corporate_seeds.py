#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

PARENT_PREDS = {"DIRECT_ACCOUNTING_PARENT", "ULTIMATE_ACCOUNTING_PARENT", "SUBSIDIARY_OF"}

# Worse-status wins when a seed is reachable via multiple edges with
# different resolution outcomes. None means the edge's provider doesn't
# carry a resolution_status at all (e.g. EDGAR) — treated as neutral,
# not as a failure.
_STATUS_RANK = {"RESOLVED": 0, "UNRESOLVED_RETRY": 1, "UNRESOLVED_TERMINAL": 2}


def generate(graph):
    nodes = {n.get("node_id"): n for n in graph.get("nodes", [])}
    root_ids = {nid for nid, n in nodes.items() if "root" in (n.get("roles") or [])}
    related = {}

    def add_seed(seed_id, edge, counterpart_id, seed_side):
        seed = nodes.get(seed_id); counterpart = nodes.get(counterpart_id)
        if not seed or not counterpart or seed_id in root_ids:
            return
        evidence = edge.get("evidence") or []
        providers = sorted({e.get("provider") for e in evidence if e.get("provider")} | ({edge.get("provider")} if edge.get("provider") else set()))

        attrs = edge.get("attributes") or {}
        resolution_status = attrs.get(f"{seed_side}_resolution_status")
        # An edge with no status field at all (non-GLEIF provider) never
        # degrades a seed. Only an explicit unresolved status does.
        name_resolved = resolution_status in (None, "RESOLVED")
        gleif_confirmed = "gleif" in providers and name_resolved

        item = related.setdefault(seed_id, {
            "node_id": seed_id, "legal_name": seed.get("canonical_name"),
            "jurisdiction": seed.get("jurisdiction"),
            "provider_entity_ids": seed.get("provider_entity_ids") or [],
            "seed_type": "related_legal_entity",
            "corporate_seed_confidence": "high" if gleif_confirmed else "review",
            "infrastructure_attribution_confidence": "unknown",
            "disposition": "SAFE_WITH_CONTEXT" if gleif_confirmed else "REVIEW_REQUIRED",
            "identity_resolution_status": None,
            "relationship_evidence": [],
            "asm_instruction": "Use as an organization/name seed for downstream infrastructure discovery; do not auto-attribute assets from this corporate edge alone.",
        })

        # Track the worst resolution status seen across every edge that
        # produced this seed, so a seed reached both by a resolved GLEIF
        # edge and an unresolved one still surfaces the unresolved state
        # rather than hiding it behind the first edge processed.
        current = item["identity_resolution_status"]
        if resolution_status is not None:
            if current is None or _STATUS_RANK.get(resolution_status, 0) > _STATUS_RANK.get(current, 0):
                item["identity_resolution_status"] = resolution_status
                if not name_resolved:
                    item["corporate_seed_confidence"] = "review"
                    item["disposition"] = "REVIEW_REQUIRED"

        item["relationship_evidence"].append({
            "predicate": edge.get("predicate"),
            "counterpart_node_id": counterpart_id,
            "counterpart_name": counterpart.get("canonical_name"),
            "providers": providers,
            "source_relationship_key": edge.get("source_relationship_key"),
            "identity_resolution_status": resolution_status,
        })

    for edge in graph.get("relationships", []):
        if edge.get("predicate") not in PARENT_PREDS:
            continue
        child_id, parent_id = edge.get("subject_node_id"), edge.get("object_node_id")
        # A seed is the non-root endpoint adjacent to the queried/root entity.
        # This handles both parent->child discovery and child->parent discovery.
        if parent_id in root_ids:
            add_seed(child_id, edge, parent_id, seed_side="child")
        if child_id in root_ids:
            add_seed(parent_id, edge, child_id, seed_side="parent")

    seeds = sorted(related.values(), key=lambda x: ((x.get("legal_name") or "").casefold(), x.get("node_id") or ""))
    return {
        "schema_version": "corporate-asm-seeds-v1", "seed_count": len(seeds), "seeds": seeds,
        "safety_note": "Corporate relationship evidence proposes entities to investigate. It does not establish infrastructure ownership or ASM attribution.",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    graph = json.loads(Path(a.graph).read_text(encoding="utf-8"))
    out = generate(graph)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out['seed_count']} corporate ASM seed(s) -> {a.out}")


if __name__ == "__main__":
    main()
