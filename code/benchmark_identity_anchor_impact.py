#!/usr/bin/env python3
"""Compare actual pre- and post-anchoring resolvers on a frozen, stratified cohort.

Not an accuracy benchmark: no independently confirmed identities or parent truth.
All inputs are local, output is exclusive, and indexed DBs are read-only.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import re
import sqlite3
import subprocess
import sys
import types

from root_entity_resolver import normalize_name, resolve_company_root

BASELINE_REF = "origin/feat/identity-quality-gates"
SEED = 20261123
STRATA = ("general_exact", "relationship_child_exact", "inactive_exact", "shortened_name", "historical_alias", "known_risk")


def readonly(path):
    p = Path(path).resolve()
    if not p.is_file():
        raise FileNotFoundError(p)
    con = sqlite3.connect(f"{p.as_uri()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def reservoir(cursor, size, rng, converter):
    selected = []
    seen = 0
    for row in cursor:
        item = converter(row)
        if item is None:
            continue
        seen += 1
        if len(selected) < size:
            selected.append(item)
        else:
            i = rng.randrange(seen)
            if i < size:
                selected[i] = item
    return selected


def generate_cohort(lei_db, rr_db, alias_db, seed=SEED):
    """Reproducible name sample from local indices; user should freeze output."""
    rng = random.Random(seed)
    lei = readonly(lei_db)
    rr = readonly(rr_db)
    alias = readonly(alias_db)
    try:
        base_query = ("SELECT lei, legal_name, entity_status FROM lei_entities "
                      "WHERE legal_name IS NOT NULL AND trim(legal_name) != '' "
                      "ORDER BY lei")
        general = reservoir(
            lei.execute(base_query + ""), 40, rng,
            lambda r: {"query": r["legal_name"], "expected_source_lei": r["lei"]}
            if r["entity_status"] == "ACTIVE" else None
        )
        inactive = reservoir(
            lei.execute(base_query), 10, rng,
            lambda r: {"query": r["legal_name"], "expected_source_lei": r["lei"]}
            if r["entity_status"] != "ACTIVE" else None
        )
        # Relationship-child stratum deliberately tests parent-ranking pressure.
        # De-duplicate children before sampling. This is not a verified
        # ownership label; it only indicates an indexed relationship row.
        rr_children = reservoir(
            rr.execute("""
                SELECT DISTINCT child_lei FROM relationships
                WHERE relationship_status='ACTIVE'
                  AND relationship_type IN (
                    'IS_DIRECTLY_CONSOLIDATED_BY',
                    'IS_ULTIMATELY_CONSOLIDATED_BY'
                  )
                ORDER BY child_lei
            """), 80, rng, lambda r: r["child_lei"]
        )
        linked = []
        for child in rr_children:
            match = lei.execute("SELECT lei,legal_name FROM lei_entities WHERE lei=?", (child,)).fetchone()
            if match and match["legal_name"]:
                linked.append({"query": match["legal_name"], "expected_source_lei": match["lei"]})
            if len(linked) >= 20:
                break
        # Shortened names are intentionally not assumed to identify the same
        # entity: these are retrieval probes, not legal identity ground truth.
        shortened = []
        for item in general + linked:
            tokens = re.findall(r"\w+", item["query"], flags=re.UNICODE)
            if len(tokens) < 3:
                continue
            short = " ".join(tokens[:2])
            if normalize_name(short) == normalize_name(item["query"]):
                continue
            shortened.append({"query": short, "derived_from": item["query"]})
            if len(shortened) >= 15:
                break
        # Sample across the compact alias table rather than taking an
        # alphabetically biased prefix. Keep sampled aliases only when the LEI
        # is in canonical DB. A failed lookup is NOT marked an identity error.
        maximum = alias.execute("SELECT MAX(rowid) FROM entity_name").fetchone()[0] or 0
        historical = []
        used_alias = set()
        for _ in range(400):
            if len(historical) >= 12 or maximum == 0:
                break
            offset = rng.randint(1, maximum)
            row = alias.execute("""
                SELECT n.name, o.record_identifier AS lei
                FROM entity_name AS n
                JOIN source_observation AS o ON o.observation_id=n.observation_id
                WHERE n.rowid >= ? ORDER BY n.rowid LIMIT 1
            """, (offset,)).fetchone()
            if not row or not row["name"] or normalize_name(row["name"]) in used_alias:
                continue
            current = lei.execute("SELECT legal_name FROM lei_entities WHERE lei=?",
                                  (row["lei"],)).fetchone()
            if not current or normalize_name(current["legal_name"] or "") == normalize_name(row["name"]):
                continue
            used_alias.add(normalize_name(row["name"]))
            historical.append({
                "query": row["name"],
                "source_alias_lei": row["lei"],
                "indexed_current_name": current["legal_name"],
            })
        result = []
        seen = set()
        for category, items in (
            ("general_exact", general), ("relationship_child_exact", linked),
            ("inactive_exact", inactive), ("shortened_name", shortened),
            ("historical_alias", historical),
            ("known_risk", [{"query": "Sempra Energy"}, {"query": "SentinelOne"}]),
        ):
            for item in items:
                name = item["query"]
                # Deduplicate across strata, preserving original stratum.
                key = normalize_name(name)
                if key and key not in seen:
                    seen.add(key)
                    result.append({"stratum": category, **item})
        if not result:
            raise ValueError("No benchmark entries generated")
        return result
    finally:
        lei.close()
        rr.close()
        alias.close()


def load_cohort(path):
    parsed = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = parsed.get("cases") if isinstance(parsed, dict) else parsed
    if not isinstance(rows, list) or not rows:
        raise ValueError("Cohort JSON must contain non-empty cases list")
    for row in rows:
        if not isinstance(row, dict) or row.get("stratum") not in STRATA or not isinstance(row.get("query"), str) or not row["query"].strip():
            raise ValueError("Each case requires stratum and nonempty query")
    if len({normalize_name(c["query"]) for c in rows}) != len(rows):
        raise ValueError("Duplicate query in frozen cohort")
    return rows


def previous_resolver(ref):
    """Load the actual historical implementation at a resolved Git commit."""
    sha = subprocess.check_output(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], text=True
    ).strip()
    source = subprocess.check_output(
        ["git", "show", f"{sha}:code/root_entity_resolver.py"], text=True
    )
    module_name = "_historical_root_entity_resolver"
    old = types.ModuleType(module_name)
    old.__file__ = f"git:{sha}:code/root_entity_resolver.py"
    sys.modules[module_name] = old
    exec(compile(source, old.__file__, "exec"), old.__dict__)
    return old.resolve_company_root, sha, hashlib.sha256(source.encode()).hexdigest()


def outcome(result):
    return {
        "status": result.status,
        "confidence": result.confidence,
        "root_lei": result.root.lei if result.root else None,
        "root_name": result.root.legal_name if result.root else None,
        "top_exploratory_lei": result.candidates[0].lei if result.candidates else None,
        "top_exploratory_name": result.candidates[0].legal_name if result.candidates else None,
        "seed_leis": sorted({s["lei"] for s in result.seed_matches}),
        "candidate_count": len(result.candidates),
        "reason": result.reason,
    }


def compare_cases(cohort, old_resolver, lei_db, rr_db, alias_db):
    rows = []
    counters = Counter()
    per_stratum = {}
    for item in cohort:
        args = dict(lei_db=lei_db, rr_db=rr_db, alias_db=alias_db)
        before = outcome(old_resolver(item["query"], **args))
        after = outcome(resolve_company_root(item["query"], **args))
        stratum = item["stratum"]
        old_auto = before["status"] == "AUTO_RESOLVED"
        new_auto = after["status"] == "AUTO_RESOLVED"
        changed = (before["status"], before["root_lei"]) != (after["status"], after["root_lei"])
        transitions = per_stratum.setdefault(stratum, Counter())
        for tally in (counters, transitions):
            tally["cases"] += 1
            tally["before_auto"] += int(old_auto)
            tally["after_auto"] += int(new_auto)
            tally["before_review"] += int(before["status"] == "REVIEW_REQUIRED")
            tally["after_review"] += int(after["status"] == "REVIEW_REQUIRED")
            tally["changed_decisions"] += int(changed)
            tally["auto_to_review"] += int(old_auto and after["status"] == "REVIEW_REQUIRED")
            tally["suppressed_root"] += int(before["root_lei"] is not None and after["root_lei"] is None)
            tally["seed_set_changed"] += int(before["seed_leis"] != after["seed_leis"])
            tally["candidate_top_changed"] += int(before["top_exploratory_lei"] != after["top_exploratory_lei"])
        rows.append({
            "query": item["query"],
            "stratum": stratum,
            "sampling_metadata": {k: v for k, v in item.items() if k not in ("query", "stratum")},
            "before": before, "after": after,
            "changed_decision": changed,
            "identity_correctness": "NOT_SCORED",
            "root_correctness": "NOT_SCORED",
            "m_and_a_recall": "NOT_SCORED",
        })
    return {
        "counts": dict(sorted(counters.items())),
        "by_stratum": {k: dict(sorted(v.items())) for k, v in sorted(per_stratum.items())},
        "cases": rows,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--lei-db", default="data/processed/gleif_lei.sqlite")
    p.add_argument("--rr-db", default="data/processed/gleif_rr.sqlite")
    p.add_argument("--alias-db", default="data/processed/gleif_alias_compact_full.sqlite")
    p.add_argument("--baseline-ref", default=BASELINE_REF,
                   help="Original pre-safeguard Git ref (must exist locally)")
    p.add_argument("--cohort", help="Existing frozen cohort JSON; default generates stratified cohort")
    p.add_argument("--out", required=True, help="New comparison JSON; refuses overwrite")
    args = p.parse_args()
    baseline, sha, source_hash = previous_resolver(args.baseline_ref)
    cohort = load_cohort(args.cohort) if args.cohort else generate_cohort(
        args.lei_db, args.rr_db, args.alias_db
    )
    comparison = compare_cases(cohort, baseline, args.lei_db, args.rr_db, args.alias_db)
    report = {
        "benchmark": "PAIRED_PRE_POST_IDENTITY_ANCHORING",
        "baseline_commit": sha,
        "baseline_resolver_sha256": source_hash,
        "cohort_origin": str(Path(args.cohort).resolve()) if args.cohort else "GENERATED_DETERMINISTIC_STRATIFIED",
        "generator_seed": SEED if not args.cohort else None,
        "frozen_cohort": cohort,
        **comparison,
        "ground_truth_status": "NOT_SCORED",
        "limitations": [
            "Stratified diagnostic cohort, not a representative random sample of all organizations.",
            "No independent labels for identity, root correctness, or M&A recall.",
            "Source name/LEI for sampling is not verification that a shortened query has that identity.",
            "LEI, RR, and compact alias snapshots may have different vintages.",
            "Current and historical resolvers are run against the same local databases.",
            "Root suppression is a safety property, not measured accuracy gain.",
            "Alias search candidate recall may be truncated by coarse SQL LIMIT 5000.",
        ],
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as fp:
        json.dump(report, fp, indent=2, ensure_ascii=False)
        fp.write("\n")
    print(json.dumps({
        "cohort_size": len(cohort), "baseline_commit": sha,
        "counts": comparison["counts"], "by_stratum": comparison["by_stratum"],
        "out": str(path.resolve()), "quality": "NOT_SCORED",
    }, indent=2))


if __name__ == "__main__":
    main()
