#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


RELATIONSHIP_LABELS = {
    "IS_DIRECTLY_CONSOLIDATED_BY": "DIRECT_ACCOUNTING_PARENT",
    "IS_ULTIMATELY_CONSOLIDATED_BY": "ULTIMATE_ACCOUNTING_PARENT",
}


def connect(path):
    if not Path(path).is_file():
        raise SystemExit(f"Database not found: {path}")

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def normalize_name(value):
    return " ".join(value.casefold().strip().split())


def find_company(db_path, company):
    conn = connect(db_path)

    query = normalize_name(company)

    # First try exact normalized legal-name match.
    rows = conn.execute(
        """
        SELECT *
        FROM lei_entities
        WHERE legal_name_normalized = ?
        ORDER BY
            CASE WHEN entity_status = 'ACTIVE' THEN 0 ELSE 1 END,
            legal_name
        LIMIT 50
        """,
        (query,),
    ).fetchall()

    if not rows:
        # Operator-friendly fallback.
        rows = conn.execute(
            """
            SELECT *
            FROM lei_entities
            WHERE legal_name_normalized LIKE ?
            ORDER BY
                CASE WHEN entity_status = 'ACTIVE' THEN 0 ELSE 1 END,
                legal_name
            LIMIT 50
            """,
            (f"%{query}%",),
        ).fetchall()

    conn.close()

    return [dict(row) for row in rows]


def lookup_lei(conn, lei):
    row = conn.execute(
        """
        SELECT *
        FROM lei_entities
        WHERE lei = ?
        """,
        (lei,),
    ).fetchone()

    return dict(row) if row else None


def get_relationships(rr_db, root_lei):
    conn = connect(rr_db)

    rows = conn.execute(
        """
        SELECT *
        FROM relationships
        WHERE child_lei = ?
           OR parent_lei = ?
        ORDER BY relationship_type, child_lei, parent_lei
        """,
        (root_lei, root_lei),
    ).fetchall()

    conn.close()

    return [dict(row) for row in rows]


def describe_relation(root_lei, relationship):
    child = relationship["child_lei"]
    parent = relationship["parent_lei"]
    raw_type = relationship["relationship_type"]

    canonical = RELATIONSHIP_LABELS.get(
        raw_type,
        raw_type,
    )

    if root_lei == child:
        # Root is the child: discovered entity is its accounting parent.
        return {
            "related_lei": parent,
            "direction": "OUTBOUND",
            "relationship": canonical,
            "raw_relationship": raw_type,
        }

    # Root is the parent: discovered entity is consolidated by the root.
    if raw_type == "IS_DIRECTLY_CONSOLIDATED_BY":
        relation = "DIRECT_ACCOUNTING_CHILD"
    elif raw_type == "IS_ULTIMATELY_CONSOLIDATED_BY":
        relation = "ULTIMATE_ACCOUNTING_CHILD"
    else:
        relation = f"INVERSE_{canonical}"

    return {
        "related_lei": child,
        "direction": "INBOUND",
        "relationship": relation,
        "raw_relationship": raw_type,
    }


def expand_company(root, lei_db, rr_db):
    relationships = get_relationships(rr_db, root["lei"])

    lei_conn = connect(lei_db)

    results = []

    seen = set()

    for raw in relationships:
        rel = describe_relation(root["lei"], raw)
        related_lei = rel["related_lei"]

        key = (
            related_lei,
            rel["relationship"],
        )

        if key in seen:
            continue

        seen.add(key)

        identity = lookup_lei(
            lei_conn,
            related_lei,
        )

        if identity:
            name = identity.get("legal_name")
            jurisdiction = identity.get("legal_jurisdiction")
            entity_status = identity.get("entity_status")
            registration_status = identity.get("registration_status")
            enrichment_state = "RESOLVED"
        else:
            name = related_lei
            jurisdiction = None
            entity_status = None
            registration_status = None
            enrichment_state = "UNRESOLVED_LEVEL1"

        result = {
            "name": name,
            "lei": related_lei,
            "jurisdiction": jurisdiction,
            "relationship": rel["relationship"],
            "raw_relationship": rel["raw_relationship"],
            "direction": rel["direction"],

            "entity_status": entity_status,
            "registration_status": registration_status,

            "relationship_status": raw.get(
                "relationship_status"
            ),

            "relationship_start": raw.get(
                "relationship_start"
            ),

            "relationship_end": raw.get(
                "relationship_end"
            ),

            "accounting_start": raw.get(
                "accounting_start"
            ),

            "accounting_end": raw.get(
                "accounting_end"
            ),

            "validation_sources": raw.get(
                "validation_sources"
            ),

            "validation_documents": raw.get(
                "validation_documents"
            ),

            "validation_reference": raw.get(
                "validation_reference"
            ),

            "source": "GLEIF",
            "corporate_confidence": "HIGH",
            "infrastructure_attribution_confidence": "UNKNOWN",

            "enrichment_state": enrichment_state,
        }

        results.append(result)

    lei_conn.close()

    return results


def choose_root(candidates, requested_lei=None):
    if requested_lei:
        for candidate in candidates:
            if candidate["lei"] == requested_lei:
                return candidate

        raise SystemExit(
            f"Requested LEI {requested_lei} was not among company matches."
        )

    if not candidates:
        return None

    if len(candidates) == 1:
        return candidates[0]

    exact_active = [
        c for c in candidates
        if c.get("entity_status") == "ACTIVE"
    ]

    if len(exact_active) == 1:
        return exact_active[0]

    return None


def print_candidates(candidates):
    print()
    print("Multiple possible root entities found:")
    print()

    for i, row in enumerate(candidates, 1):
        print(
            f"[{i}] {row.get('legal_name')}"
        )

        print(
            f"    LEI: {row.get('lei')}"
        )

        print(
            f"    Jurisdiction: "
            f"{row.get('legal_jurisdiction') or '-'}"
        )

        print(
            f"    Status: "
            f"{row.get('entity_status') or '-'}"
        )

        print()


def print_report(root, results):
    print()
    print("=" * 72)
    print("CORPORATION HELIX")
    print("=" * 72)

    print()
    print("ROOT")
    print(f"  Name         : {root.get('legal_name')}")
    print(f"  LEI          : {root.get('lei')}")
    print(
        f"  Jurisdiction : "
        f"{root.get('legal_jurisdiction') or '-'}"
    )
    print(
        f"  Status       : "
        f"{root.get('entity_status') or '-'}"
    )

    print()
    print(
        f"RELATED LEGAL ENTITIES ({len(results)})"
    )
    print("-" * 72)

    if not results:
        print("No supported GLEIF relationships found.")
        return

    for result in results:
        print()
        print(result["name"])

        print(
            f"  Relationship : "
            f"{result['relationship']}"
        )

        print(
            f"  LEI          : "
            f"{result['lei']}"
        )

        print(
            f"  Jurisdiction : "
            f"{result['jurisdiction'] or '-'}"
        )

        print(
            f"  Entity status: "
            f"{result['entity_status'] or '-'}"
        )

        print(
            f"  RR status    : "
            f"{result['relationship_status'] or '-'}"
        )

        print(
            f"  Evidence     : GLEIF"
        )

        print(
            f"  Corporate confidence     : "
            f"{result['corporate_confidence']}"
        )

        print(
            f"  Infrastructure confidence: "
            f"{result['infrastructure_attribution_confidence']}"
        )

        if result["enrichment_state"] != "RESOLVED":
            print(
                f"  REVIEW       : "
                f"{result['enrichment_state']}"
            )


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Expand a company into related legal entities "
            "using local Corporation Helix indexes."
        )
    )

    ap.add_argument(
        "--company",
        required=True,
        help='Company name, e.g. "Sony"',
    )

    ap.add_argument(
        "--lei",
        help="Explicit root LEI when company-name search is ambiguous",
    )

    ap.add_argument(
        "--lei-index",
        default="data/processed/gleif_lei.sqlite",
    )

    ap.add_argument(
        "--rr-index",
        default="data/processed/gleif_rr.sqlite",
    )

    ap.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of terminal report",
    )

    args = ap.parse_args()

    candidates = find_company(
        args.lei_index,
        args.company,
    )

    if not candidates:
        raise SystemExit(
            f'No GLEIF Level 1 matches found for "{args.company}".'
        )

    root = choose_root(
        candidates,
        args.lei,
    )

    if root is None:
        print_candidates(candidates)

        print(
            "Root identity is ambiguous."
        )

        print(
            "Run again with:"
        )

        print()
        print(
            '  python3 code/helix_company.py '
            f'--company "{args.company}" '
            "--lei <LEI>"
        )

        raise SystemExit(2)

    results = expand_company(
        root,
        args.lei_index,
        args.rr_index,
    )

    if args.json:
        print(
            json.dumps(
                {
                    "query": args.company,
                    "root": root,
                    "related_entities": results,
                },
                indent=2,
                ensure_ascii=False,
            )
        )

    else:
        print_report(
            root,
            results,
        )


if __name__ == "__main__":
    main()
