#!/usr/bin/env python3
"""
Corporation Helix -- generic flat-file (CSV) evidence parser.

The JSON input shape ingest_supplied_evidence.py already accepts is fine
for a script or an ASM API export, but a human handing over "here's what
we found" is far more likely to reach for a spreadsheet. This is that
path: one row per observation, plain columns, no nesting -- and it
produces the exact same (entities, subjects) shape load_supplied_evidence()
does, so everything downstream (evidence_bridge, candidates_from_observations,
gap reporting) is unaware of which format the data originally came from.

Expected columns (header row required, any column order):

    entity_lei          -- required if entity_name is ambiguous/absent
    entity_name          -- required if entity_lei is absent
    domain               -- required
    capability            -- required: RDAP_WHOIS / IP_ASN_OWNERSHIP /
                             TLS_CERTIFICATE / DNS / HTTP_LEGAL_PRIVACY /
                             CUSTOMER_ASSERTION
    provider              -- optional, defaults to "flat-file"
    availability          -- optional, defaults to PROVIDED
                             (PROVIDED / MISSING / INCONCLUSIVE / CONTRADICTORY)
    observed_value        -- optional
    supports_attribution  -- optional: true/false/1/0/yes/no, blank = unset
    reference             -- optional

Blank cells are treated as "not specified," not as literal empty strings,
so a blank supports_attribution column correctly leaves that field as
None rather than being misread as a False.

No network calls anywhere in this file.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from domain_candidates import CorporateEntity

_TRUE = {"true", "1", "yes", "y"}
_FALSE = {"false", "0", "no", "n"}


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    value = value.strip().lower()
    if not value:
        return None
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ValueError(f"Unrecognized boolean value: {value!r} (use true/false/1/0/yes/no or leave blank)")


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def load_csv_evidence(path: Path) -> tuple[list[CorporateEntity], list[dict[str, Any]]]:
    """
    Read a flat evidence CSV and return (entities, subjects) in the same
    shape ingest_supplied_evidence.load_supplied_evidence() produces from
    JSON, so both formats feed the exact same downstream pipeline.
    """
    entities_by_key: dict[str, CorporateEntity] = {}
    subjects_by_key: dict[tuple[str | None, str], dict[str, Any]] = {}

    with Path(path).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSV file has no header row.")
        missing_required = {"domain", "capability"} - set(reader.fieldnames)
        if missing_required:
            raise ValueError(f"CSV is missing required column(s): {sorted(missing_required)}")

        for line_num, row in enumerate(reader, start=2):  # header is line 1
            entity_lei = _clean(row.get("entity_lei"))
            entity_name = _clean(row.get("entity_name"))
            domain = _clean(row.get("domain"))
            capability = _clean(row.get("capability"))

            if not domain:
                raise ValueError(f"Row {line_num}: missing required 'domain'")
            if not capability:
                raise ValueError(f"Row {line_num}: missing required 'capability'")
            if not entity_lei and not entity_name:
                raise ValueError(f"Row {line_num}: needs at least one of entity_lei/entity_name")

            entity_key = entity_lei or f"name:{entity_name}"
            if entity_key not in entities_by_key:
                entities_by_key[entity_key] = CorporateEntity(
                    entity_name=entity_name or entity_lei, entity_lei=entity_lei,
                )

            subject_key = (entity_lei, domain)
            subject = subjects_by_key.setdefault(subject_key, {
                "entity_lei": entity_lei,
                "entity_name": entity_name,
                "domain": domain,
                "observations": [],
            })
            subject["observations"].append({
                "capability": capability,
                "provider": _clean(row.get("provider")) or "flat-file",
                "availability": _clean(row.get("availability")) or "PROVIDED",
                "observed_value": _clean(row.get("observed_value")),
                "supports_attribution": _parse_bool(row.get("supports_attribution")),
                "reference": _clean(row.get("reference")),
            })

    return list(entities_by_key.values()), list(subjects_by_key.values())
