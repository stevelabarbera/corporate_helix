#!/usr/bin/env python3
"""Paired canonical-only vs alias-enabled identity-discovery benchmark.

Measures discovery changes, NOT accuracy or M&A recall: ground truth and
transaction evidence are separate requirements. Same query/order and same
source databases for both arms.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3

from root_entity_resolver import resolve_company_root


SMOKE_COHORT = [
    "Trustmark National Bank",
    "IXIS ADVISOR FUNDS TRUST I",
    "CHALA ESTATES S.R.O.",
    "Sempra Energy",
    "SentinelOne",
]


def load_cohort(path=None):
    if path is None:
        return SMOKE_COHORT[:], "BUILT_IN_SMOKE_ONLY"
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".json":
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            parsed = parsed.get("companies", parsed.get("cohort"))
        if not isinstance(parsed, list):
            raise ValueError("JSON cohort must be a list or {'companies': [...]}")
        names = [
            item if isinstance(item, str) else item.get("company", item.get("name"))
            if isinstance(item, dict) else None
            for item in parsed
        ]
    else:
        names = [v.strip() for v in text.splitlines() if v.strip() and not v.lstrip().startswith("#")]
    if any(not isinstance(x, str) or not x.strip() for x in names):
        raise ValueError("Invalid cohort entry; require company name strings")
    if not names or len(names) != len(set(names)):
        raise ValueError("Cohort must have nonempty, unique company names")
    return names, str(p.resolve())


def db_metadata(lei_db, alias_db):
    lei = sqlite3.connect(f"{Path(lei_db).resolve().as_uri()}?mode=ro", uri=True)
    alias = sqlite3.connect(f"{Path(alias_db).resolve().as_uri()}?mode=ro", uri=True)
    try:
        canonical_count = lei.execute("SELECT COUNT(*) FROM lei_entities").fetchone()[0]
        metadata = dict(lei.execute("SELECT key,value FROM index_metadata").fetchall()) \
            if lei.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='index_metadata'").fetchone() else {}
        snapshots = alias.execute(
            "SELECT source_archive_sha256, record_count, alias_count, is_sample FROM source_snapshot"
        ).fetchall()
        if len(snapshots) != 1:
            raise ValueError("Expected exactly one alias source snapshot")
        sha, record_count, alias_count, is_sample = snapshots[0]
        if is_sample:
            raise ValueError("Benchmark requires full alias index, not a sample")
        return {
            "canonical_index_entities": canonical_count,
            "canonical_index_metadata": metadata,
            "alias_index_records_scanned": record_count,
            "alias_index_entries": alias_count,
            "alias_archive_sha256": sha,
            "cross_snapshot_alignment_verified": False,
            "alias_index_source_fidelity_verified_by_this_run": False,
        }
    finally:
        lei.close()
        alias.close()


def classify(result):
    seeds = result.seed_matches
    return {
        "status": result.status,
        "confidence": result.confidence,
        "seed_count": len(seeds),
        "seed_leis": sorted({str(x["lei"]) for x in seeds}),
        "alias_seed_leis": sorted({str(x["lei"]) for x in seeds
                                   if x.get("match_source") == "GLEIF_LEVEL1_ALIAS"}),
        "proposed_root_lei": result.root.lei if result.root else None,
        "reason": result.reason,
    }


def run(companies, lei_db, rr_db, alias_db):
    metadata = db_metadata(lei_db, alias_db)
    rows = []
    sums = Counter()
    for company in companies:
        canonical = classify(resolve_company_root(company, lei_db=lei_db, rr_db=rr_db))
        enabled = classify(resolve_company_root(
            company, lei_db=lei_db, rr_db=rr_db, alias_db=alias_db
        ))
        c_leis = set(canonical["seed_leis"])
        a_leis = set(enabled["seed_leis"])
        # Existing matching intentionally uses aliases as FALLBACK only:
        # canonical seeds are not augmented when any direct candidates exist.
        new_leis = sorted(a_leis - c_leis)
        if c_leis and canonical["status"] != enabled["status"]:
            raise RuntimeError(f"Canonical decision changed with aliases for {company!r}")
        if enabled["alias_seed_leis"] and (
            enabled["status"] != "REVIEW_REQUIRED" or enabled["confidence"] != "LOW"
        ):
            raise RuntimeError(f"Alias-only auto-resolve gate violated for {company!r}")
        if c_leis and new_leis:
            raise RuntimeError(f"Fallback-only contract violated for {company!r}")
        sums[f"baseline_{canonical['status']}"] += 1
        sums[f"alias_enabled_{enabled['status']}"] += 1
        sums["companies_with_new_leis"] += bool(new_leis)
        sums["new_seed_lei_pairs"] += len(new_leis)
        sums["previously_no_match_now_has_seeds"] += bool(
            not c_leis and bool(a_leis)
        )
        rows.append({
            "company": company,
            "canonical_only": canonical,
            "alias_enabled": enabled,
            "new_candidate_leis": new_leis,
            "new_seed_discovered": bool(new_leis),
            "identity_correctness": "NOT_SCORED",
            "m_and_a_recall": "NOT_SCORED",
            "ownership_verified": False,
        })
    return {
        "benchmark_type": "PAIRED_IDENTITY_DISCOVERY",
        "cohort_size": len(companies),
        "metadata": metadata,
        "summary": dict(sorted(sums.items())),
        "cases": rows,
        "limitations": [
            "No independently labeled identity ground truth; candidate discovery is NOT precision/accuracy.",
            "Aliases are fallback-only; existing canonical matches are not expanded with aliases.",
            "The existing bounded 5000-row coarse LIKE query can miss aliases; totals are lower-bound observations.",
            "LEI lookup and alias archive cross-snapshot alignment is not verified by this benchmark.",
            "Source SHA/count read from metadata, not reverified; run verify_compact_gleif_alias_index.py separately.",
            "Parent proposals are unverified and ownership/M&A detection is not measured.",
        ],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cohort", help="Frozen cohort .txt (one company/line) or .json list")
    p.add_argument("--lei-db", default="data/processed/gleif_lei.sqlite")
    p.add_argument("--rr-db", default="data/processed/gleif_rr.sqlite")
    p.add_argument("--alias-db", default="data/processed/gleif_alias_compact_full.sqlite")
    p.add_argument("--out", required=True, help="NEW JSON result file; never overwrite")
    args = p.parse_args()
    companies, cohort = load_cohort(args.cohort)
    output = run(companies, args.lei_db, args.rr_db, args.alias_db)
    output["cohort_source"] = cohort
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(output, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(json.dumps({
        "cohort_source": cohort,
        "cohort_size": len(companies),
        "summary": output["summary"],
        "result_path": str(path.resolve()),
        "quality_metrics": "NOT_SCORED",
    }, indent=2))


if __name__ == "__main__":
    main()
