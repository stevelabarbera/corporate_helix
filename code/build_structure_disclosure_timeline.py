#!/usr/bin/env python3
"""Build an observation timeline from historical EDGAR structure filings.

The output deliberately describes disclosure observations, not legal life spans:
an entity disappearing from Exhibit 21 is not evidence that it was sold,
dissolved, or ceased to be a subsidiary.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from normalization.names import normalize_alias
from providers.edgar_adapter import EdgarJsonAdapter


def build(raw):
    observations = defaultdict(list)
    aliases = defaultdict(set)
    jurisdictions = defaultdict(set)
    filing_dates = sorted({
        f.get("filing_date") for f in raw.get("filings", []) if f.get("filing_date")
    })

    adapter = EdgarJsonAdapter()
    for filing in raw.get("filings", []):
        result = adapter.from_dict(
            {"company": raw.get("company"), "cik": raw.get("cik"), "filings": [filing]},
            raw.get("company", ""),
        )
        for rel in result.relationships:
            if rel.predicate != "HAS_SUBSIDIARY":
                continue
            # Issuer resolution intentionally strips corporate-form words to
            # match names such as "SERVICE CORP INTERNATIONAL".  That is too
            # lossy here: Corporation, LLC, Co. Ltd. and Limited can identify
            # distinct legal entities.  Timeline grouping therefore folds
            # only spelling, punctuation, case and accents.
            key = normalize_alias(rel.object_name)
            if not key:
                continue
            aliases[key].add(rel.object_name)
            if rel.jurisdiction:
                jurisdictions[key].add(rel.jurisdiction)
            observations[key].append({
                "filing_date": filing.get("filing_date"),
                "accession": filing.get("accession"),
                "form_type": filing.get("form_type") or filing.get("form"),
                "name": rel.object_name,
                "jurisdiction": rel.jurisdiction,
                "source_url": rel.evidence[0].source_url if rel.evidence else None,
            })

    entities = []
    for key, rows in observations.items():
        rows.sort(key=lambda x: (x.get("filing_date") or "", x.get("accession") or ""))
        observed_dates = {r["filing_date"] for r in rows if r.get("filing_date")}
        first = min(observed_dates) if observed_dates else None
        last = max(observed_dates) if observed_dates else None
        between = [d for d in filing_dates if first and last and first <= d <= last]
        entities.append({
            "identity_key": key,
            "canonical_name": rows[-1]["name"],
            "aliases": sorted(aliases[key], key=str.casefold),
            "jurisdictions": sorted(jurisdictions[key], key=str.casefold),
            "first_observed": first,
            "last_observed": last,
            "observation_count": len(rows),
            "filing_appearances": rows,
            "not_disclosed_between_observations": [d for d in between if d not in observed_dates],
            "current_filing_disclosure": bool(filing_dates and filing_dates[-1] in observed_dates),
        })

    entities.sort(key=lambda x: (x["first_observed"] or "", x["canonical_name"].casefold()))
    return {
        "schema_version": "structure-disclosure-timeline-v1",
        "company": raw.get("company"),
        "cik": str(raw.get("cik", "")),
        "filing_count": len(raw.get("filings", [])),
        "filing_dates": filing_dates,
        "entities": entities,
        "summary": {
            "entity_count": len(entities),
            "observation_count": sum(len(v) for v in observations.values()),
        },
        "interpretation_warning": (
            "First/last observed are disclosure bounds only. Absence from an Exhibit 21 "
            "filing does not prove acquisition, divestiture, dissolution, or ownership status."
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    raw = json.loads(Path(args.input).read_text(encoding="utf-8"))
    timeline = build(raw)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(timeline, indent=2, ensure_ascii=False), encoding="utf-8")
    summary = timeline["summary"]
    print(
        f"Wrote disclosure timeline: {summary['entity_count']} entities, "
        f"{summary['observation_count']} observations -> {out}"
    )


if __name__ == "__main__":
    main()
