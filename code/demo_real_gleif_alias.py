#!/usr/bin/env python3
"""Demonstrate a genuine Level-1 GLEIF alias from a staged evidence sample.

Discovers a REAL stored alias, confirms the associated LEI is in the
existing Level-1 lookup, and invokes the normal resolver. Does not
manufacture company records or modify any SQLite database. A historical
alias MUST remain review-only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3

from root_entity_resolver import (
    connect, find_seed_matches, normalize_name, resolve_company_root
)


def _read_only(path):
    if not Path(path).is_file():
        raise FileNotFoundError(path)
    db = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def run_demo(evidence_db, lei_db, rr_db, preferred_alias=None):
    evidence = _read_only(evidence_db)
    lei = connect(lei_db)
    try:
        snapshot = evidence.execute(
            "SELECT source_level, is_sample, source_archive_sha256, record_count "
            "FROM source_snapshot"
        ).fetchall()
        if len(snapshot) != 1 or snapshot[0]["source_level"] != "lei":
            raise ValueError("Expected exactly one Level 1 evidence snapshot")
        query = """
            SELECT n.name AS alias_name, n.raw_value_json, n.source_path,
                   o.record_identifier AS lei, o.source_ordinal,
                   e.name AS source_legal_name
              FROM entity_name AS n
              JOIN source_observation AS o
                ON o.observation_id=n.observation_id
              LEFT JOIN entity_name AS e
                ON e.observation_id=n.observation_id
               AND e.source_path='Entity.LegalName'
             WHERE n.source_path != 'Entity.LegalName'
               AND n.name IS NOT NULL
             ORDER BY o.source_ordinal, n.source_ordinal
        """
        available = evidence.execute(query).fetchall()
        # Prefer short, distinct historical names with a direct demo value.
        # Choosing from actual rows prevents a fabricated example.
        if preferred_alias:
            available = sorted(
                available,
                key=lambda row: 0 if normalize_name(row["alias_name"])
                == normalize_name(preferred_alias) else 1,
            )
        else:
            preferred = (
                "Trustmark National Bank",
                "IXIS ADVISOR FUNDS TRUST I",
                "CHALA ESTATES S.R.O.",
            )
            available = sorted(available, key=lambda row: (
                preferred.index(row["alias_name"]) if row["alias_name"] in preferred else len(preferred),
                row["source_ordinal"],
            ))
        attempted = 0
        for item in available:
            alias = item["alias_name"]
            if preferred_alias and normalize_name(alias) != normalize_name(preferred_alias):
                continue
            if normalize_name(alias) == normalize_name(item["source_legal_name"] or ""):
                continue
            if lei.execute("SELECT 1 FROM lei_entities WHERE lei=?", (item["lei"],)).fetchone() is None:
                continue
            attempted += 1
            if find_seed_matches(lei, alias):
                # The existing canonical-only resolver already covers this query;
                # do not misrepresent it as a new discovery through aliases.
                continue
            resolution = resolve_company_root(
                alias, lei_db=lei_db, rr_db=rr_db,
                alias_db=evidence_db, allow_sample_aliases=True,
            )
            seeds = [s for s in resolution.seed_matches
                     if s["lei"] == item["lei"]
                     and s.get("match_source") == "GLEIF_LEVEL1_ALIAS"]
            if not seeds:
                continue
            if resolution.status != "REVIEW_REQUIRED" or resolution.confidence != "LOW":
                raise RuntimeError("Alias-only match incorrectly escaped review-only safety gate")
            return {
                "status": "DEMONSTRATED",
                "query": alias,
                "alias_type": json.loads(item["raw_value_json"]).get("@type"),
                "source_lei": item["lei"],
                "source_current_legal_name": item["source_legal_name"],
                "source_record_ordinal": item["source_ordinal"],
                "source_archive_sha256": snapshot[0]["source_archive_sha256"],
                "evidence_is_sample": bool(snapshot[0]["is_sample"]),
                "resolution_status": resolution.status,
                "resolution_confidence": resolution.confidence,
                "matched_seed_count": len(seeds),
                "resolved_seed_leis": [s["lei"] for s in seeds],
                "root_lei_for_review": resolution.root.lei if resolution.root else None,
                "ownership_verified": False,
                "notice": "Alias-only match: candidate lead, not current corporate ownership.",
            }
        return {
            "status": "NO_DEMONSTRABLE_ALIAS",
            "reason": (
                "No sampled alias could be shown as a genuine new discovery "
                "against the existing lookup. This does not imply no aliases "
                "exist in the full GLEIF source."
            ),
            "sample_alias_rows": len(available),
            "eligible_aliases_examined": attempted,
            "evidence_is_sample": bool(snapshot[0]["is_sample"]),
        }
    finally:
        evidence.close()
        lei.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--alias-db", default="data/processed/gleif_lei_tier1_sample.sqlite")
    p.add_argument("--lei-db", default="data/processed/gleif_lei.sqlite")
    p.add_argument("--rr-db", default="data/processed/gleif_rr.sqlite")
    p.add_argument("--prefer-alias", help="Optional name to demonstrate, if present")
    args = p.parse_args()
    result = run_demo(args.alias_db, args.lei_db, args.rr_db, args.prefer_alias)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "DEMONSTRATED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
