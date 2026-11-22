#!/usr/bin/env python3
"""Read-only identity-quality gates: inspect wrong-root risks and LEI coverage.

This is a *diagnostic*, not an adjudicator. It never turns a graph edge into
identity proof or invents ground-truth labels. Source-backed seed names and
candidate roots are kept distinct. All outputs are JSON; no DB mutation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3

from root_entity_resolver import connect, normalize_name, resolve_company_root


def read_only(path):
    p = Path(path).resolve()
    if not p.is_file():
        raise FileNotFoundError(p)
    db = sqlite3.connect(f"{p.as_uri()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def reconcile_alias_leis(lei_db, alias_db):
    """Count exact LEI overlap; snapshot equality is NOT implied by overlap."""
    alias = read_only(alias_db)
    try:
        snapshots = alias.execute(
            "SELECT source_level, source_archive_sha256, record_count, "
            "alias_count, is_sample FROM source_snapshot"
        ).fetchall()
        if len(snapshots) != 1 or snapshots[0]["source_level"] != "lei":
            raise ValueError("Alias source must have one Level 1 snapshot")
        if snapshots[0]["is_sample"]:
            raise ValueError("Full alias index required for population reconciliation")
        # ATTACH is read-only; run a single SQLite join, not 548K Python lookups.
        canonical_path = Path(lei_db).resolve()
        if not canonical_path.is_file():
            raise FileNotFoundError(canonical_path)
        alias.execute("ATTACH DATABASE ? AS canonical",
                      (f"{canonical_path.as_uri()}?mode=ro",))
        query = """
            SELECT
              COUNT(*) AS alias_entities,
              SUM(CASE WHEN c.lei IS NULL THEN 1 ELSE 0 END) AS missing_in_canonical,
              SUM(CASE WHEN c.lei IS NOT NULL THEN 1 ELSE 0 END) AS present_in_canonical
            FROM source_observation AS a
            LEFT JOIN canonical.lei_entities AS c
              ON c.lei = a.record_identifier
        """
        result = dict(alias.execute(query).fetchone())
        examples = [
            dict(row) for row in alias.execute("""
                SELECT a.record_identifier AS lei, a.source_ordinal AS source_record_ordinal
                FROM source_observation AS a
                LEFT JOIN canonical.lei_entities AS c
                  ON c.lei = a.record_identifier
                WHERE c.lei IS NULL
                ORDER BY a.source_ordinal LIMIT 10
            """)
        ]
        canonical_count = alias.execute(
            "SELECT COUNT(*) FROM canonical.lei_entities"
        ).fetchone()[0]
        return {
            "status": "RECONCILED_LEI_PRESENCE",
            "alias_archive_sha256": snapshots[0]["source_archive_sha256"],
            "alias_source_records": snapshots[0]["record_count"],
            "alias_entries": snapshots[0]["alias_count"],
            "alias_bearing_entities": result["alias_entities"],
            "present_in_canonical_index": result["present_in_canonical"] or 0,
            "missing_in_canonical_index": result["missing_in_canonical"] or 0,
            "canonical_index_entity_count": canonical_count,
            "missing_examples": examples,
            "snapshot_identity_verified": False,
            "note": (
                "LEI presence only. This does not establish identical archive "
                "vintages, names, dates, successor status, or ownership."
            ),
        }
    finally:
        alias.close()


def inspect_case(company, lei_db, rr_db, alias_db=None):
    """Report lexical identity support independently of path/root selection."""
    result = resolve_company_root(
        company, lei_db=lei_db, rr_db=rr_db, alias_db=alias_db
    )
    seeds = []
    for entry in result.seed_matches:
        name = entry.get("matched_name") or entry.get("legal_name") or ""
        match_type = entry.get("match_source", "GLEIF_CANONICAL_NAME")
        # A token phrase in a longer legal name is not independently
        # established equivalence to the queried legal entity.
        exact = normalize_name(company) == normalize_name(name)
        seeds.append({
            "lei": entry["lei"],
            "indexed_legal_name": entry.get("legal_name"),
            "matched_name": name,
            "match_type": match_type,
            "exact_query_name": exact,
            "independently_verified_identity": False,
        })
    root = result.root.to_dict() if result.root else None
    selected_root_is_seed = bool(root and any(
        s["lei"] == root["lei"] for s in seeds
    ))
    exact_canonical = any(
        s["exact_query_name"] and s["match_type"] == "GLEIF_CANONICAL_NAME"
        for s in seeds
    )
    warnings = []
    if seeds and not exact_canonical:
        warnings.append("NO_EXACT_CANONICAL_NAME_IDENTITY_ANCHOR")
    if root and not selected_root_is_seed:
        warnings.append("PROPOSED_ROOT_FROM_RELATIONSHIP_TRAVERSAL")
    if root and not exact_canonical:
        warnings.append("ROOT_NOT_VALIDATED_AGAINST_QUERY_IDENTITY")
    if result.status == "AUTO_RESOLVED" and not exact_canonical:
        warnings.append("AUTOMATIC_SELECTION_WITHOUT_EXACT_CANONICAL_NAME")
    return {
        "query": company,
        "resolver_status": result.status,
        "resolver_confidence": result.confidence,
        "resolver_reason": result.reason,
        "seed_evidence": seeds,
        "proposed_root": root,
        "selected_root_is_seed": selected_root_is_seed,
        "quality_warnings": warnings,
        "identity_correctness": "NOT_SCORED",
        "proposed_root_correctness": "NOT_SCORED",
        "ownership_verified": False,
        "note": (
            "Diagnostic warnings are not ground-truth labels. In particular, "
            "a GLEIF child-parent path does not verify the query-to-seed identity."
        ),
    }


def audit(companies, lei_db, rr_db, alias_db):
    alignment = reconcile_alias_leis(lei_db, alias_db)
    cases = [inspect_case(n, lei_db, rr_db, alias_db) for n in companies]
    counts = Counter(w for case in cases for w in case["quality_warnings"])
    return {
        "status": "DIAGNOSTIC_ONLY",
        "alignment": alignment,
        "case_count": len(cases),
        "quality_warning_counts": dict(sorted(counts.items())),
        "cases": cases,
        "ground_truth_status": "NOT_SCORED",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lei-db", default="data/processed/gleif_lei.sqlite")
    ap.add_argument("--rr-db", default="data/processed/gleif_rr.sqlite")
    ap.add_argument("--alias-db", default="data/processed/gleif_alias_compact_full.sqlite")
    ap.add_argument("--company", action="append",
                    help="Repeatable company to evaluate; default is Sempra Energy")
    ap.add_argument("--out", required=True, help="NEW JSON output path; no overwrite")
    args = ap.parse_args()
    report = audit(
        args.company or ["Sempra Energy"], args.lei_db, args.rr_db, args.alias_db
    )
    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(json.dumps({
        "status": report["status"],
        "alignment": report["alignment"],
        "case_summaries": [
            {
                "query": case["query"],
                "status": case["resolver_status"],
                "proposed_root": case["proposed_root"]["legal_name"]
                    if case["proposed_root"] else None,
                "warnings": case["quality_warnings"],
            }
            for case in report["cases"]
        ],
        "out": str(destination.resolve()),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
