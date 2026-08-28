from __future__ import annotations
from copy import deepcopy
import hashlib
from normalization.names import normalize_legal_name

def _stable(parts):
    payload = "|".join((p or "").strip() for p in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]

def _node_id(name_norm, jurisdiction_norm):
    return "node:" + _stable([name_norm, jurisdiction_norm])

def _alias_id(alias_norm, jurisdiction_norm):
    return "alias:" + _stable([alias_norm, jurisdiction_norm])

def _root_from_result(result):
    name = result.get("resolved_name") or result.get("query")
    # Root identity must come from the provider's resolved root name.  The old
    # implementation borrowed the first relationship subject, which only held
    # for EDGAR's parent->subsidiary shape and breaks child->parent providers.
    name_norm = normalize_legal_name(name) if name else ""

    # Use explicit SEC root evidence jurisdiction if present.
    jurisdiction = (result.get("metadata") or {}).get("root_jurisdiction")
    for ent in result.get("entities", []):
        attrs = ent.get("attributes") or {}
        if (attrs.get("relationship_label") or "").casefold() == "ultimate parent":
            jurisdiction = ent.get("identity", {}).get("jurisdiction_normalized")
            break

    return {
        "node_id": _node_id(name_norm, jurisdiction),
        "canonical_name": name,
        "canonical_name_normalized": name_norm,
        "jurisdiction": jurisdiction,
        "provider_entity_ids": [result.get("provider_entity_id")] if result.get("provider_entity_id") else [],
        "source_entities": [],
        "aliases": [],
        "roles": ["root"],
        "resolution": {
            "method": "provider_root",
            "confidence": 1.0,
            "review_required": False,
        },
    }

def _canonicalize_relationship(rel, root_node):
    """
    Flip M1/M2 parent->child HAS_SUBSIDIARY to child->parent SUBSIDIARY_OF.
    Suppress SELF_OR_ULTIMATE_PARENT as an edge; its evidence is attached to root.
    """
    if rel.get("predicate") == "SELF_OR_ULTIMATE_PARENT":
        return None

    if rel.get("predicate") == "HAS_SUBSIDIARY":
        return {
            "subject_node_id": rel.get("object_entity_key"),
            "predicate": "SUBSIDIARY_OF",
            "object_node_id": root_node["node_id"],
            "ownership_percent": rel.get("ownership_percent"),
            "relationship_status": rel.get("relationship_status"),
            "provider": rel.get("provider"),
            "evidence": deepcopy(rel.get("evidence") or []),
            "attributes": deepcopy(rel.get("attributes") or {}),
            "source_relationship_key": rel.get("relationship_key"),
        }

    return {
        "subject_node_id": rel.get("subject_entity_key"),
        "predicate": rel.get("predicate"),
        "object_node_id": rel.get("object_entity_key"),
        "ownership_percent": rel.get("ownership_percent"),
        "relationship_status": rel.get("relationship_status"),
        "provider": rel.get("provider"),
        "evidence": deepcopy(rel.get("evidence") or []),
        "attributes": deepcopy(rel.get("attributes") or {}),
        "source_relationship_key": rel.get("relationship_key"),
    }

def _entity_to_node(entity):
    ident = entity.get("identity") or {}
    name_norm = ident.get("legal_name_normalized")
    j = ident.get("jurisdiction_normalized")
    aliases = []
    for raw, norm in zip(
        ident.get("former_names_raw") or [],
        ident.get("former_names_normalized") or []
    ):
        aliases.append({
            "alias_id": _alias_id(norm, j),
            "name_raw": raw,
            "name_normalized": norm,
            "jurisdiction": j,
            "alias_type": "former_name",
            "source": entity.get("provider"),
        })

    return {
        "node_id": entity.get("entity_key") or _node_id(name_norm, j),
        "canonical_name": entity.get("legal_name"),
        "canonical_name_normalized": name_norm,
        "legal_name_base": ident.get("legal_name_base"),
        "jurisdiction": j,
        "jurisdiction_raw": ident.get("jurisdiction_raw"),
        "provider_entity_ids": [entity.get("provider_entity_id")] if entity.get("provider_entity_id") else [],
        "source_entities": [deepcopy(entity)],
        "aliases": aliases,
        "roles": [],
        "resolution": {
            "method": "single_source_exact",
            "confidence": 1.0,
            "review_required": False,
        },
    }

def _same_exact(a, b):
    return (
        a.get("canonical_name_normalized") == b.get("canonical_name_normalized")
        and a.get("jurisdiction") == b.get("jurisdiction")
    )

def _former_name_match(a, b):
    """
    Conservative alias matching:
    A former-name alias may merge into another current entity only when
    normalized name AND jurisdiction agree.
    """
    for alias in a.get("aliases", []):
        if (
            alias.get("name_normalized") == b.get("canonical_name_normalized")
            and alias.get("jurisdiction") == b.get("jurisdiction")
        ):
            return True
    for alias in b.get("aliases", []):
        if (
            alias.get("name_normalized") == a.get("canonical_name_normalized")
            and alias.get("jurisdiction") == a.get("jurisdiction")
        ):
            return True
    return False

def _merge_nodes(target, source, reason):
    target["source_entities"].extend(source.get("source_entities") or [])
    for x in source.get("provider_entity_ids") or []:
        if x and x not in target["provider_entity_ids"]:
            target["provider_entity_ids"].append(x)
    seen = {(a["name_normalized"], a.get("jurisdiction")) for a in target.get("aliases", [])}
    for a in source.get("aliases", []):
        key = (a["name_normalized"], a.get("jurisdiction"))
        if key not in seen:
            target["aliases"].append(a)
            seen.add(key)
    target["resolution"] = {
        "method": reason,
        "confidence": 1.0 if reason == "exact_identity" else 0.95,
        "review_required": False,
    }


def normalize_jurisdiction_for_compare(default_j, rel, side):
    attrs = rel.get("attributes") or {}
    raw = attrs.get("child_jurisdiction" if side == "subject" else "parent_jurisdiction")
    if raw is None:
        return default_j
    # Keep dependency direction simple: relationship attrs generally already use the same
    # ISO-style jurisdiction forms as normalized provider data.
    return str(raw).strip().upper() or default_j

def resolve_provider_results(results):
    """
    M3 v1 resolver.

    Conservative merge rules:
      1. exact normalized legal name + normalized jurisdiction
      2. former-name alias + same normalized jurisdiction

    No fuzzy matching.
    No cross-jurisdiction merging.
    Similar base names become candidates only, never automatic merges.
    """
    graph = {
        "resolution_version": "m3-v1",
        "nodes": [],
        "relationships": [],
        "resolution_events": [],
        "review_candidates": [],
        "warnings": [],
    }

    node_by_source_key = {}

    for result in results:
        root = _root_from_result(result)

        # If provider supplied an Ultimate Parent entity, attach its evidence to root
        # instead of creating a self-edge.
        for ent in result.get("entities", []):
            label = ((ent.get("attributes") or {}).get("relationship_label") or "").casefold()
            if label == "ultimate parent":
                root["source_entities"].append(deepcopy(ent))
                if ent.get("entity_key"):
                    node_by_source_key[ent["entity_key"]] = root["node_id"]

        graph["nodes"].append(root)

        for entity in result.get("entities", []):
            label = ((entity.get("attributes") or {}).get("relationship_label") or "").casefold()
            if label == "ultimate parent":
                continue
            node = _entity_to_node(entity)
            graph["nodes"].append(node)
            if entity.get("entity_key"):
                node_by_source_key[entity["entity_key"]] = node["node_id"]

        for rel in result.get("relationships", []):
            edge = _canonicalize_relationship(rel, root)
            if edge:
                ident = rel.get("identity") or {}
                root_norm = root.get("canonical_name_normalized")
                root_j = root.get("jurisdiction")
                if (ident.get("subject_name_normalized") == root_norm and
                        normalize_jurisdiction_for_compare(ident.get("jurisdiction_normalized"), rel, side="subject") == root_j):
                    edge["subject_node_id"] = root["node_id"]
                if (ident.get("object_name_normalized") == root_norm and
                        normalize_jurisdiction_for_compare(ident.get("jurisdiction_normalized"), rel, side="object") == root_j):
                    edge["object_node_id"] = root["node_id"]
                graph["relationships"].append(edge)

    # Resolve nodes conservatively.
    resolved = []
    remap = {}

    for node in graph["nodes"]:
        match = None
        reason = None
        for existing in resolved:
            if _same_exact(existing, node):
                match = existing; reason = "exact_identity"; break
            if _former_name_match(existing, node):
                match = existing; reason = "former_name_same_jurisdiction"; break

        if match:
            remap[node["node_id"]] = match["node_id"]
            _merge_nodes(match, node, reason)
            graph["resolution_events"].append({
                "action": "merge",
                "from_node_id": node["node_id"],
                "into_node_id": match["node_id"],
                "reason": reason,
            })
        else:
            resolved.append(node)

    # Rewrite relationship node ids through merge map.
    def final_id(node_id):
        while node_id in remap:
            node_id = remap[node_id]
        return node_id

    for edge in graph["relationships"]:
        edge["subject_node_id"] = final_id(node_by_source_key.get(edge["subject_node_id"], edge["subject_node_id"]))
        edge["object_node_id"] = final_id(node_by_source_key.get(edge["object_node_id"], edge["object_node_id"]))

    # Base-name candidate detection: useful for M3 review, never auto-merge.
    for i, a in enumerate(resolved):
        for b in resolved[i+1:]:
            if not a.get("legal_name_base") or not b.get("legal_name_base"):
                continue
            if a["legal_name_base"] == b["legal_name_base"] and a["node_id"] != b["node_id"]:
                graph["review_candidates"].append({
                    "left_node_id": a["node_id"],
                    "right_node_id": b["node_id"],
                    "reason": "same_legal_name_base",
                    "left_jurisdiction": a.get("jurisdiction"),
                    "right_jurisdiction": b.get("jurisdiction"),
                    "auto_merge": False,
                })

    graph["nodes"] = resolved
    graph["summary"] = {
        "node_count": len(resolved),
        "relationship_count": len(graph["relationships"]),
        "merge_count": len(graph["resolution_events"]),
        "review_candidate_count": len(graph["review_candidates"]),
        "rules": [
            "exact normalized legal name + jurisdiction => merge",
            "former-name alias + same jurisdiction => merge",
            "same base name only => review candidate",
            "cross-jurisdiction similarity never auto-merges",
            "no fuzzy matching in m3-v1",
        ],
    }
    return graph
