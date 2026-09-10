#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from parsers.csv_parser import load_csv_evidence


def _write(tmp: Path, content: str) -> Path:
    p = tmp / "evidence.csv"
    p.write_text(content, encoding="utf-8")
    return p


def test_basic_round_trip_produces_entities_and_subjects():
    csv_text = (
        "entity_lei,entity_name,domain,capability,provider,availability,observed_value,supports_attribution\n"
        "LEI-A,Example Inc.,example.com,RDAP_WHOIS,asm-tool,PROVIDED,Example Inc.,true\n"
    )
    with tempfile.TemporaryDirectory() as d:
        path = _write(Path(d), csv_text)
        entities, subjects = load_csv_evidence(path)
        assert len(entities) == 1 and entities[0].entity_lei == "LEI-A"
        assert len(subjects) == 1
        assert subjects[0]["domain"] == "example.com"
        assert subjects[0]["observations"][0]["capability"] == "RDAP_WHOIS"
        assert subjects[0]["observations"][0]["supports_attribution"] is True
    print("PASS test_basic_round_trip_produces_entities_and_subjects")


def test_multiple_rows_same_subject_group_into_one():
    csv_text = (
        "entity_lei,entity_name,domain,capability,availability\n"
        "LEI-A,Example Inc.,example.com,RDAP_WHOIS,PROVIDED\n"
        "LEI-A,Example Inc.,example.com,IP_ASN_OWNERSHIP,PROVIDED\n"
    )
    with tempfile.TemporaryDirectory() as d:
        path = _write(Path(d), csv_text)
        entities, subjects = load_csv_evidence(path)
        assert len(subjects) == 1
        assert len(subjects[0]["observations"]) == 2
    print("PASS test_multiple_rows_same_subject_group_into_one")


def test_blank_supports_attribution_stays_none_not_false():
    csv_text = (
        "entity_lei,entity_name,domain,capability,supports_attribution\n"
        "LEI-A,Example Inc.,example.com,TLS_CERTIFICATE,\n"
    )
    with tempfile.TemporaryDirectory() as d:
        path = _write(Path(d), csv_text)
        _, subjects = load_csv_evidence(path)
        assert subjects[0]["observations"][0]["supports_attribution"] is None
    print("PASS test_blank_supports_attribution_stays_none_not_false")


def test_boolean_variants_accepted():
    csv_text = (
        "entity_lei,entity_name,domain,capability,supports_attribution\n"
        "LEI-A,Example Inc.,a.example,RDAP_WHOIS,TRUE\n"
        "LEI-A,Example Inc.,b.example,RDAP_WHOIS,0\n"
        "LEI-A,Example Inc.,c.example,RDAP_WHOIS,yes\n"
        "LEI-A,Example Inc.,d.example,RDAP_WHOIS,no\n"
    )
    with tempfile.TemporaryDirectory() as d:
        path = _write(Path(d), csv_text)
        _, subjects = load_csv_evidence(path)
        by_domain = {s["domain"]: s["observations"][0]["supports_attribution"] for s in subjects}
        assert by_domain == {"a.example": True, "b.example": False, "c.example": True, "d.example": False}
    print("PASS test_boolean_variants_accepted")


def test_missing_required_column_raises():
    csv_text = "entity_lei,entity_name\nLEI-A,Example Inc.\n"
    with tempfile.TemporaryDirectory() as d:
        path = _write(Path(d), csv_text)
        try:
            load_csv_evidence(path)
            assert False, "expected ValueError"
        except ValueError as e:
            assert "domain" in str(e)
    print("PASS test_missing_required_column_raises")


def test_entity_name_only_row_is_accepted():
    # No entity_lei at all -- entity_name alone must be enough to key on.
    csv_text = (
        "entity_name,domain,capability\n"
        "Example Inc.,example.com,RDAP_WHOIS\n"
    )
    with tempfile.TemporaryDirectory() as d:
        path = _write(Path(d), csv_text)
        entities, subjects = load_csv_evidence(path)
        assert entities[0].entity_lei is None
        assert entities[0].entity_name == "Example Inc."
    print("PASS test_entity_name_only_row_is_accepted")


def test_ingest_cli_auto_detects_csv_by_extension():
    from ingest_supplied_evidence import load_supplied_evidence
    csv_text = (
        "entity_lei,entity_name,domain,capability,availability,supports_attribution\n"
        "LEI-A,Example Inc.,example.com,CUSTOMER_ASSERTION,PROVIDED,true\n"
    )
    with tempfile.TemporaryDirectory() as d:
        path = _write(Path(d), csv_text)
        entities, subjects = load_supplied_evidence(path)
        assert len(entities) == 1 and len(subjects) == 1
    print("PASS test_ingest_cli_auto_detects_csv_by_extension")


if __name__ == "__main__":
    suite = [
        test_basic_round_trip_produces_entities_and_subjects,
        test_multiple_rows_same_subject_group_into_one,
        test_blank_supports_attribution_stays_none_not_false,
        test_boolean_variants_accepted,
        test_missing_required_column_raises,
        test_entity_name_only_row_is_accepted,
        test_ingest_cli_auto_detects_csv_by_extension,
    ]
    failed = 0
    for test in suite:
        try:
            test()
        except Exception as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
    print(f"{len(suite)-failed} passed / {failed} failed")
    raise SystemExit(1 if failed else 0)
