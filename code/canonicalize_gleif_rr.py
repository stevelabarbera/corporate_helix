#!/usr/bin/env python3

import argparse
import json
from pathlib import Path

from providers.gleif_lei_index import enrichment_state, lookup_lei
from providers.gleif_rr_adapter import GleifRelationshipRecordAdapter


def pairs(values):
    result = {}
    for item in values:
        if "=" not in item:
            raise ValueError(f"Expected LEI=value, got: {item!r}")
        key, value = item.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def _v(obj, *path):
    for part in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    if isinstance(obj, dict) and "$" in obj:
        return obj.get("$")
    return obj


def relationship_endpoints(wrapper):
    rr = wrapper.get("RelationshipRecord", wrapper)
    rel = rr.get("Relationship") or {}

    start = _v(rel, "StartNode", "NodeID")
    end = _v(rel, "EndNode", "NodeID")

    return start, end


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Canonicalize one GLEIF Level 2 Relationship Record, optionally "
            "enriching both LEI endpoints from the local Level 1 SQLite index."
        )
    )

    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)

    ap.add_argument(
        "--lei-index",
        help="Local GLEIF Level 1 SQLite index",
    )

    # Retain old options as optional manual overrides.
    ap.add_argument(
        "--name",
        action="append",
        default=[],
        help="Optional override: LEI=Legal Name",
    )
    ap.add_argument(
        "--jurisdiction",
        action="append",
        default=[],
        help="Optional override: LEI=CC or CC-REGION",
    )

    a = ap.parse_args()

    raw = json.loads(Path(a.inp).read_text(encoding="utf-8"))

    start_lei, end_lei = relationship_endpoints(raw)

    if not start_lei or not end_lei:
        raise SystemExit(
            "Input does not contain both GLEIF RR StartNode and EndNode LEIs."
        )

    names = {}
    jurisdictions = {}

    enrichment = {
        "level1_index": a.lei_index,
        "child": {
            "lei": start_lei,
            "state": "NOT_REQUESTED",
        },
        "parent": {
            "lei": end_lei,
            "state": "NOT_REQUESTED",
        },
    }

    if a.lei_index:
        child = lookup_lei(a.lei_index, start_lei)
        parent = lookup_lei(a.lei_index, end_lei)

        enrichment["child"]["state"] = enrichment_state(child)
        enrichment["parent"]["state"] = enrichment_state(parent)

        if child:
            enrichment["child"]["level1"] = child

            if child.get("legal_name"):
                names[start_lei] = child["legal_name"]

            if child.get("legal_jurisdiction"):
                jurisdictions[start_lei] = child["legal_jurisdiction"]

        if parent:
            enrichment["parent"]["level1"] = parent

            if parent.get("legal_name"):
                names[end_lei] = parent["legal_name"]

            if parent.get("legal_jurisdiction"):
                jurisdictions[end_lei] = parent["legal_jurisdiction"]

    # Explicit command-line values override SQLite enrichment.
    names.update(pairs(a.name))
    jurisdictions.update(pairs(a.jurisdiction))

    result = GleifRelationshipRecordAdapter().from_record(
        raw,
        names,
        jurisdictions,
    )

    result.metadata["level1_enrichment"] = enrichment

    child_state = enrichment["child"]["state"]
    parent_state = enrichment["parent"]["state"]

    if child_state == "UNRESOLVED_LEVEL1":
        result.warnings.append(
            f"Child LEI {start_lei} was not found in the Level 1 index; "
            "relationship preserved using the bare LEI."
        )

    if parent_state == "UNRESOLVED_LEVEL1":
        result.warnings.append(
            f"Parent LEI {end_lei} was not found in the Level 1 index; "
            "relationship preserved using the bare LEI."
        )

    if child_state == "PARTIAL_ENRICHMENT":
        result.warnings.append(
            f"Child LEI {start_lei} has incomplete Level 1 enrichment."
        )

    if parent_state == "PARTIAL_ENRICHMENT":
        result.warnings.append(
            f"Parent LEI {end_lei} has incomplete Level 1 enrichment."
        )

    out = result.to_dict()

    output_path = Path(a.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(out, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(
        f"Wrote RR canonical result: "
        f"{len(out['entities'])} related entity, "
        f"{len(out['relationships'])} relationship -> {a.out}"
    )

    print(
        f"Level 1 enrichment: "
        f"child={child_state}, "
        f"parent={parent_state}"
    )


if __name__ == "__main__":
    main()
