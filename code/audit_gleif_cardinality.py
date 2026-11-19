#!/usr/bin/env python3
"""Read-only GLEIF source cardinality inventory (Level 1 LEI2 or Level 2 RR).

Examines original source objects, not flattened SQLite rows. Inventory is
bounded by number of distinct paths and example count, and source records are
streamed one by one. Arrays are reported by *observed* cardinality; repeated
PeriodType values within the same RR record are also detected.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import zipfile


@contextmanager
def source_stream(path):
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            names = [x for x in archive.namelist() if x.lower().endswith(".json")]
            if len(names) != 1:
                raise ValueError(f"Expected exactly one JSON member, found {len(names)}")
            with archive.open(names[0]) as stream:
                yield stream
    else:
        with open(path, "rb") as stream:
            yield stream


def iter_source(path, level, allow_known_repair=False):
    import ijson
    if level == "rr":
        # Reuse existing source iterator for RR, whose line-oriented assumptions
        # must be audited independently before claiming complete parse coverage.
        from build_gleif_rr_index import records
        if zipfile.is_zipfile(path):
            yield from records(path)
        else:
            raise ValueError("RR mode currently requires the original JSON ZIP")
    else:
        from build_gleif_lei_index import RepairingBinaryReader
        with source_stream(path) as raw:
            reader = RepairingBinaryReader(raw) if allow_known_repair else raw
            for record in ijson.items(reader, "records.item"):
                yield record
            if allow_known_repair and reader.repairs:
                print(f"Known syntax repairs applied: {len(reader.repairs)}", file=sys.stderr)


class CardinalityInventory:
    def __init__(self, example_limit=3, max_paths=10000):
        self.example_limit = example_limit
        self.max_paths = max_paths
        self.paths = {}
        self.repeated_period_types = Counter()
        self.repeated_period_examples = []
        self.scanned = 0

    def _get(self, path):
        if path not in self.paths:
            if len(self.paths) >= self.max_paths:
                raise RuntimeError("Too many distinct source paths; raise --max-paths if expected")
            self.paths[path] = {
                "types": Counter(), "present_instances": 0,
                "array_instances": 0, "arrays_multi": 0, "arrays_empty": 0,
                "max_array_length": 0, "examples": [],
            }
        return self.paths[path]

    def _walk(self, obj, path, record_number):
        stat = self._get(path)
        stat["present_instances"] += 1
        if isinstance(obj, dict):
            stat["types"]["object"] += 1
            for key, value in obj.items():
                self._walk(value, f"{path}.{key}", record_number)
        elif isinstance(obj, list):
            stat["types"]["array"] += 1
            stat["array_instances"] += 1
            length = len(obj)
            stat["max_array_length"] = max(stat["max_array_length"], length)
            stat["arrays_multi"] += length > 1
            stat["arrays_empty"] += length == 0
            if length > 1 and len(stat["examples"]) < self.example_limit:
                stat["examples"].append({"record_number": record_number, "array_length": length})
            for item in obj:
                self._walk(item, f"{path}[]", record_number)
        else:
            stat["types"]["null" if obj is None else type(obj).__name__] += 1

    def _inspect_rr_periods(self, wrapper):
        rr = wrapper.get("RelationshipRecord", wrapper)
        rel = rr.get("Relationship") or {}
        periods = (rel.get("RelationshipPeriods") or {}).get("RelationshipPeriod") or []
        if isinstance(periods, dict):
            periods = [periods]
        buckets = defaultdict(list)
        for period in periods:
            if not isinstance(period, dict):
                continue
            kind = period.get("PeriodType")
            if isinstance(kind, dict):
                kind = kind.get("$")
            if kind is None:
                kind = "<missing>"
            buckets[str(kind)].append(period)
        for kind, values in buckets.items():
            if len(values) > 1:
                self.repeated_period_types[kind] += 1
                if len(self.repeated_period_examples) < self.example_limit:
                    self.repeated_period_examples.append({
                        "record_number": self.scanned, "period_type": kind,
                        "count": len(values),
                    })

    def observe(self, record, level):
        self.scanned += 1
        self._walk(record, "$", self.scanned)
        if level == "rr":
            self._inspect_rr_periods(record)

    def report(self, level, source, max_records):
        entries = []
        for path, stat in sorted(self.paths.items()):
            entries.append({
                "path": path,
                "types": dict(stat["types"]),
                "present_instances": stat["present_instances"],
                "array_instances": stat["array_instances"],
                "arrays_with_multiple_items": stat["arrays_multi"],
                "empty_arrays": stat["arrays_empty"],
                "max_array_length": stat["max_array_length"],
                "examples": stat["examples"],
            })
        return {
            "level": level, "source": str(Path(source).resolve()),
            "records_scanned": self.scanned,
            "coverage": "sampled" if max_records else "full_requested",
            "max_records_requested": max_records,
            "path_count": len(entries),
            "paths_with_multi_value_arrays": [
                x for x in entries if x["arrays_with_multiple_items"]
            ],
            "paths_with_multiple_shapes": [
                x for x in entries if len(x["types"]) > 1
            ],
            "repeated_rr_period_types": dict(self.repeated_period_types),
            "repeated_rr_period_examples": self.repeated_period_examples,
            "all_paths": entries,
            "limitations": [
                "Field cardinality is observed in this file or sample, not a guarantee of provider schema cardinality.",
                "A JSON list is not necessarily an entity relationship: schema review is required before normalization.",
                "RR mode reuses the existing ZIP parser and does not independently certify parser completeness.",
                "This inventory is structural; it does not certify semantic correctness or map values against SQLite.",
            ],
        }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--level", choices=("lei", "rr"), required=True)
    ap.add_argument("--source", required=True, help="GLEIF JSON or JSON ZIP; RR requires ZIP")
    ap.add_argument("--max-records", type=int, default=None,
                    help="Limit records for a fast sample (omit for full inventory)")
    ap.add_argument("--max-paths", type=int, default=10000)
    ap.add_argument("--example-limit", type=int, default=3)
    ap.add_argument("--allow-known-repair", action="store_true",
                    help="LEI only: enable logged legacy b'},.' source repair")
    ap.add_argument("--out", help="Optional report JSON file")
    args = ap.parse_args()
    if not Path(args.source).is_file():
        ap.error(f"Source not found: {args.source}")
    if args.max_records is not None and args.max_records <= 0:
        ap.error("--max-records must be positive")
    if args.example_limit < 0 or args.max_paths < 1:
        ap.error("Invalid examples or max-paths limit")
    inventory = CardinalityInventory(args.example_limit, args.max_paths)
    for record in iter_source(args.source, args.level, args.allow_known_repair):
        inventory.observe(record, args.level)
        if args.max_records and inventory.scanned >= args.max_records:
            break
        if inventory.scanned % 100000 == 0:
            print(f"Inspected {inventory.scanned:,} records", file=sys.stderr)
    report = inventory.report(args.level, args.source, args.max_records)
    result = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(result + "\n", encoding="utf-8")
    # Print a compact console summary; the full field inventory is in --out.
    print(json.dumps({
        k: report[k] for k in (
            "level", "records_scanned", "coverage", "path_count",
            "paths_with_multi_value_arrays", "paths_with_multiple_shapes",
            "repeated_rr_period_types", "repeated_rr_period_examples"
        )
    }, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
