#!/usr/bin/env python3
"""Compare successive corporate-structure disclosure snapshots.

Changes describe what appeared in SEC disclosure. They do not infer acquisition,
divestiture, dissolution, ownership, or legal-status changes.
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def compare(timeline):
    filing_dates = sorted(timeline.get("filing_dates", []))
    by_date = defaultdict(dict)
    history = defaultdict(set)

    for entity in timeline.get("entities", []):
        key = entity["identity_key"]
        for appearance in entity.get("filing_appearances", []):
            date = appearance.get("filing_date")
            if not date:
                continue
            row = by_date[date].setdefault(key, {
                "identity_key": key,
                "names": set(),
                "jurisdictions": set(),
                "accessions": set(),
            })
            if appearance.get("name"):
                row["names"].add(appearance["name"])
            if appearance.get("jurisdiction"):
                row["jurisdictions"].add(appearance["jurisdiction"])
            if appearance.get("accession"):
                row["accessions"].add(appearance["accession"])
            history[key].add(date)

    changes = []
    counts = Counter()
    for previous_date, current_date in zip(filing_dates, filing_dates[1:]):
        previous = by_date.get(previous_date, {})
        current = by_date.get(current_date, {})
        previous_keys = set(previous)
        current_keys = set(current)

        for key in sorted(current_keys - previous_keys):
            earlier = any(d < previous_date for d in history[key])
            change_type = "REAPPEARED_IN_DISCLOSURE" if earlier else "APPEARED_IN_DISCLOSURE"
            changes.append(_change(change_type, previous_date, current_date, None, current[key]))
            counts[change_type] += 1

        for key in sorted(previous_keys - current_keys):
            changes.append(_change(
                "DISAPPEARED_FROM_DISCLOSURE", previous_date, current_date,
                previous[key], None,
            ))
            counts["DISAPPEARED_FROM_DISCLOSURE"] += 1

        for key in sorted(previous_keys & current_keys):
            if previous[key]["names"] != current[key]["names"]:
                changes.append(_change(
                    "NAME_TEXT_CHANGED", previous_date, current_date,
                    previous[key], current[key],
                ))
                counts["NAME_TEXT_CHANGED"] += 1
            if previous[key]["jurisdictions"] != current[key]["jurisdictions"]:
                changes.append(_change(
                    "JURISDICTION_TEXT_CHANGED", previous_date, current_date,
                    previous[key], current[key],
                ))
                counts["JURISDICTION_TEXT_CHANGED"] += 1

    return {
        "schema_version": "structure-disclosure-changes-v1",
        "company": timeline.get("company"),
        "cik": timeline.get("cik"),
        "filing_dates": filing_dates,
        "changes": changes,
        "summary": {
            "comparison_count": max(0, len(filing_dates) - 1),
            "change_count": len(changes),
            "counts_by_type": dict(sorted(counts.items())),
        },
        "interpretation_warning": (
            "These are changes in SEC disclosure only. Appearance or disappearance does not "
            "prove acquisition, divestiture, dissolution, ownership, or legal status."
        ),
    }


def _snapshot(row):
    if row is None:
        return None
    return {
        "identity_key": row["identity_key"],
        "names": sorted(row["names"], key=str.casefold),
        "jurisdictions": sorted(row["jurisdictions"], key=str.casefold),
        "accessions": sorted(row["accessions"]),
    }


def _change(change_type, previous_date, current_date, previous, current):
    row = current or previous
    return {
        "change_type": change_type,
        "identity_key": row["identity_key"],
        "previous_filing_date": previous_date,
        "current_filing_date": current_date,
        "previous_disclosure": _snapshot(previous),
        "current_disclosure": _snapshot(current),
        "inferred_corporate_event": None,
        "requires_external_confirmation": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeline", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    timeline = json.loads(Path(args.timeline).read_text(encoding="utf-8"))
    result = compare(timeline)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    summary = result["summary"]
    print(
        f"Wrote disclosure changes: {summary['change_count']} changes across "
        f"{summary['comparison_count']} filing comparisons -> {out}"
    )
    for kind, count in summary["counts_by_type"].items():
        print(f"  {kind}: {count}")


if __name__ == "__main__":
    main()
