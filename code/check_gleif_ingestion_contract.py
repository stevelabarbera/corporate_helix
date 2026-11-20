#!/usr/bin/env python3
"""GLEIF field-contract / schema-drift gate for cardinality audit JSON.

Read-only. This gate is deliberately NOT a certificate of lossless ingestion:
unpreserved repeating structures block readiness even with zero source drift.
A baseline freezes observed paths/shapes; adding a new provider field needs
review rather than being silently accepted.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


# Normalized index is explicitly a *projection*, not complete source storage.
# Lists below name source paths without the leading '$.'.
# Status 'unpreserved' means a query index doesn't store every source element;
# it does NOT establish accidental truncation or that the data is absent from
# the original ZIP. 'partially_flattened' has demonstrated overwrite risk.
POLICY = {
    "rr": {
        "RelationshipRecord.Relationship.RelationshipPeriods.RelationshipPeriod":
            {"status": "partially_flattened", "action": "preserve all typed periods with source ordinal"},
        "RelationshipRecord.Relationship.RelationshipQualifiers.RelationshipQualifier":
            {"status": "unpreserved", "action": "retain qualifiers and their multiplicity in evidence store"},
    },
    "lei": {
        "Entity.LegalEntityEvents.LegalEntityEvent":
            {"status": "unpreserved", "action": "persist event collection with dates and event type"},
        "Entity.LegalEntityEvents.LegalEntityEvent[].AffectedFields.AffectedField":
            {"status": "unpreserved", "action": "preserve every affected field per event"},
        "Entity.OtherEntityNames.OtherEntityName":
            {"status": "unpreserved", "action": "persist original aliases and name type"},
        "Entity.SuccessorEntity":
            {"status": "unpreserved", "action": "persist all successors and event context"},
        "Entity.LegalAddress.AdditionalAddressLine":
            {"status": "unpreserved", "action": "preserve multiple address lines in source order"},
        "Entity.HeadquartersAddress.AdditionalAddressLine":
            {"status": "unpreserved", "action": "preserve multiple address lines in source order"},
        "Entity.OtherAddresses.OtherAddress":
            {"status": "unpreserved", "action": "preserve other addresses"},
        "Entity.OtherAddresses.OtherAddress[].AdditionalAddressLine":
            {"status": "unpreserved", "action": "preserve nested address lines"},
        "Entity.TransliteratedOtherAddresses.TransliteratedOtherAddress":
            {"status": "unpreserved", "action": "preserve transliterated addresses"},
        "Entity.TransliteratedOtherAddresses.TransliteratedOtherAddress[].AdditionalAddressLine":
            {"status": "unpreserved", "action": "preserve nested translated address lines"},
        "Entity.TransliteratedOtherEntityNames.TransliteratedOtherEntityName":
            {"status": "unpreserved", "action": "preserve translated names"},
        "Extension.gleif:Geocoding":
            {"status": "unpreserved", "action": "support both object and array of locations"},
        "Registration.OtherValidationAuthorities.OtherValidationAuthority":
            {"status": "unpreserved", "action": "preserve all validation authorities"},
    },
}


def compact_paths(audit):
    if audit.get("coverage") != "full_requested":
        raise ValueError("Full population audit required for approval; samples cannot become baselines")
    if not isinstance(audit.get("all_paths"), list) or not audit["all_paths"]:
        raise ValueError("Expected full cardinality audit JSON with all_paths")
    result = {}
    for item in audit["all_paths"]:
        path = item["path"]
        if path in result:
            raise ValueError(f"Duplicate path: {path}")
        result[path] = {
            "types": sorted(item["types"].keys()),
            "ever_multi": bool(item.get("arrays_with_multiple_items", 0)),
            "max_array_length": int(item.get("max_array_length", 0)),
        }
    if len(result) != audit.get("path_count"):
        raise ValueError("path_count does not match all_paths")
    return result


def make_baseline(audit):
    return {
        "format_version": 1,
        "level": audit["level"],
        "source": audit["source"],
        "records_scanned": audit["records_scanned"],
        "paths": compact_paths(audit),
        "notice": "Observed source-shape baseline; NOT an ingestion fidelity certificate.",
    }


def evaluate(audit, baseline=None):
    level = audit.get("level")
    if level not in POLICY:
        raise ValueError(f"Unknown audit level: {level}")
    current = compact_paths(audit)
    observed_multi = {
        path: info for path, info in current.items() if info["ever_multi"]
    }
    policy = POLICY[level]
    findings = []
    unreviewed = []
    for path in sorted(observed_multi):
        name = path.removeprefix("$.")
        if name not in policy:
            unreviewed.append(path)
            findings.append({"code": "UNREVIEWED_REPEATING_FIELD", "path": path})
    # Explicitly unpreserved fields are blocking until a real evidence layer
    # plus source-to-storage tests are implemented.
    blocked = [
        {"path": "$." + name, **entry}
        for name, entry in sorted(policy.items())
        if "$." + name in observed_multi
        and entry["status"] in {"unpreserved", "partially_flattened"}
    ]
    if baseline is not None:
        if baseline.get("level") != level or baseline.get("format_version") != 1:
            raise ValueError("Invalid or mismatched baseline")
        old = baseline.get("paths")
        if not isinstance(old, dict):
            raise ValueError("Baseline missing paths")
        for path, info in current.items():
            if path not in old:
                findings.append({"code": "NEW_FIELD_PATH", "path": path})
                continue
            fresh = set(info["types"]) - set(old[path]["types"])
            if fresh:
                findings.append({"code": "NEW_FIELD_TYPE", "path": path, "types": sorted(fresh)})
            if info["ever_multi"] and not old[path]["ever_multi"]:
                findings.append({"code": "NEW_REPEATING_FIELD", "path": path})
            if info["max_array_length"] > old[path]["max_array_length"]:
                findings.append({
                    "code": "LARGER_ARRAY_OBSERVED", "path": path,
                    "previous_max": old[path]["max_array_length"],
                    "current_max": info["max_array_length"],
                })
        for path in old.keys() - current.keys():
            findings.append({"code": "FIELD_PATH_DISAPPEARED", "path": path})
    return {
        "level": level,
        "source": audit.get("source"),
        "records_scanned": audit.get("records_scanned"),
        "path_count": len(current),
        "repeating_paths": len(observed_multi),
        "unreviewed_repeating_paths": unreviewed,
        "unpreserved_or_partially_flattened": blocked,
        "schema_drift": findings,
        "status": "BLOCKED" if blocked or findings or baseline is None else "PASS",
        "limitations": [
            "PASS is a structural/declared-disposition gate only, not proof of lossless ingestion.",
            "Source baselines are observed schemas, not a substitute for official GLEIF specifications.",
            "The current index intentionally omits information; preservation remains blocked until verified.",
        ],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--audit", required=True, help="Full Level 1 or Level 2 cardinality JSON")
    ap.add_argument("--baseline", help="Previously approved frozen JSON baseline")
    ap.add_argument("--baseline-out", help="Create candidate baseline from complete audit, not auto-approved")
    ap.add_argument("--out", help="Write gate report JSON")
    args = ap.parse_args()
    audit = json.loads(Path(args.audit).read_text(encoding="utf-8"))
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8")) if args.baseline else None
    if args.baseline_out:
        path = Path(args.baseline_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(make_baseline(audit), indent=2) + "\n", encoding="utf-8")
    report = evaluate(audit, baseline)
    body = json.dumps(report, indent=2)
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body + "\n", encoding="utf-8")
    print(body)
    if report["status"] != "PASS":
        print("Blocked: unresolved preservation and/or schema drift findings.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
