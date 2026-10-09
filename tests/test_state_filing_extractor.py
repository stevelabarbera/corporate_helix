#!/usr/bin/env python3
"""
Tests for state_filing_extractor.py and state_filing_provider.py.

Fixture text below is NOT copied from any real filing -- it's written to
match the real, statute-fixed DGCL Sec. 251 paragraph structure (numbered
FIRST/SECOND/THIRD clauses, the standard merge/effective-time/DGCL-
citation phrasing) confirmed against two real filed Certificates of
Merger pulled from their SEC 8-K exhibits during development:
  - Axion Acquisition Corp. / Axion International, Inc. (2008)
  - Allis-Chalmers Energy Inc. / Wellco Sub Company (2011)
Company names and dates here are invented so these tests exercise the
pattern logic, not any particular company's real transaction.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from parsers.state_filing_extractor import extract_certificate_of_merger
from providers.state_filing_provider import StateFilingProvider

IMMEDIATE_EFFECTIVE_CERT = """
CERTIFICATE OF MERGER
OF
MERIDIAN ACQUISITION SUB, INC.
WITH AND INTO
NORTHGATE HOLDINGS, INC.

Pursuant to Section 251 of the General Corporation Law of the State of
Delaware, the undersigned corporation executed the following Certificate
of Merger:

FIRST: The name of each constituent corporation is Meridian Acquisition
Sub, Inc., a corporation of the State of Delaware, and Northgate
Holdings, Inc., a corporation of the State of Delaware.

SECOND: Meridian Acquisition Sub, Inc. will merge with and into Northgate
Holdings, Inc.

THIRD: The name of the surviving corporation is Northgate Holdings, Inc.

FOURTH: The Agreement and Plan of Merger has been approved, adopted,
certified, executed and acknowledged by each constituent corporation.

FIFTH: The Merger shall become effective at the time this Certificate of
Merger is filed with the Secretary of State.

IN WITNESS WHEREOF, this Certificate of Merger has been executed on this
14th day of March, 2024.
"""

EXPLICIT_DATE_CERT = """
CERTIFICATE OF MERGER

Pursuant to Section 251 of the Delaware General Corporation Law.

FIRST: The surviving corporation is Pinnacle Robotics Corp., a
corporation of the State of Delaware.

SECOND: Cascade Sensor Technologies, Inc. shall be merged with and into
Pinnacle Robotics Corp.

THIRD: The name of the surviving corporation is Pinnacle Robotics Corp.

The Merger shall become effective on July 1, 2024 at 12:01 a.m.

Executed on June 15, 2024.
"""

INLINE_JURISDICTION_CERT = """
CERTIFICATE OF MERGER
OF
HARBORVIEW MERGER SUB INC.
WITH AND INTO
STONEBRIDGE LOGISTICS CORP.

Pursuant to Section 251 of the General Corporation Law of the State of
Delaware (the DGCL), the undersigned corporation certifies as follows:

FIRST: The name of the surviving corporation is Stonebridge Logistics
Corp., a Delaware corporation.

SECOND: Harborview Merger Sub Inc. will merge with and into Stonebridge
Logistics Corp.

FIFTH: The merger shall become effective at the time this Certificate of
Merger is filed with the Secretary of State.

Executed on September 3, 2025.
"""

NOT_A_CERTIFICATE = """
This Quarterly Report on Form 10-Q describes the Company's results of
operations for the period ended June 30, 2024. The Company acquired
substantially all of the assets of a privately held competitor during
the quarter.
"""


def test_returns_none_for_non_certificate_text():
    assert extract_certificate_of_merger(NOT_A_CERTIFICATE) is None


def test_extracts_dgcl_section():
    parsed = extract_certificate_of_merger(IMMEDIATE_EFFECTIVE_CERT)
    assert parsed["dgcl_section"] == "251"


def test_extracts_surviving_and_merging_entities():
    parsed = extract_certificate_of_merger(IMMEDIATE_EFFECTIVE_CERT)
    assert parsed["surviving_entity"] == "Northgate Holdings, Inc."
    assert parsed["merging_entity"] == "Meridian Acquisition Sub, Inc."


def test_surviving_entity_named_clause_wins_over_merge_clause_tail():
    # THIRD paragraph is the authoritative naming clause; confirms it's
    # consulted even when the merge clause in SECOND already captured a
    # (correct, in this fixture) name -- regression guard against a future
    # edit silently dropping the THIRD-paragraph preference.
    parsed = extract_certificate_of_merger(EXPLICIT_DATE_CERT)
    assert parsed["surviving_entity"] == "Pinnacle Robotics Corp."
    assert parsed["merging_entity"] == "Cascade Sensor Technologies, Inc."


def test_constituent_jurisdictions_captured():
    parsed = extract_certificate_of_merger(IMMEDIATE_EFFECTIVE_CERT)
    assert parsed["constituent_jurisdictions"]["Northgate Holdings, Inc."] == "Delaware"
    assert parsed["constituent_jurisdictions"]["Meridian Acquisition Sub, Inc."] == "Delaware"


def test_effective_on_filing_basis_when_no_explicit_date():
    parsed = extract_certificate_of_merger(IMMEDIATE_EFFECTIVE_CERT)
    assert parsed["effective_basis"] == "EFFECTIVE_ON_FILING"
    assert parsed["effective_date"] is None
    assert parsed["executed_date"] == "March 14, 2024"


def test_explicit_effective_date_captured_separately_from_executed_date():
    # The whole point of distinguishing these two dates: this fixture's
    # effective date (July 1) is more than two weeks after its execution
    # date (June 15) -- a caller that conflated them would misdate the
    # transaction by over two weeks.
    parsed = extract_certificate_of_merger(EXPLICIT_DATE_CERT)
    assert parsed["effective_basis"] == "EXPLICIT_DATE"
    assert parsed["effective_date"] == "July 1, 2024"
    assert parsed["effective_time"] == "12:01 a.m."
    assert parsed["executed_date"] == "June 15, 2024"


def test_provider_emits_merged_into_relationship_with_confidence_split():
    provider = StateFilingProvider()
    result = provider.from_text(IMMEDIATE_EFFECTIVE_CERT, source_document_id="DE-CoM-test-001")
    assert result is not None
    assert len(result.relationships) == 1
    rel = result.relationships[0]
    assert rel.subject_name == "Meridian Acquisition Sub, Inc."
    assert rel.predicate == "MERGED_INTO"
    assert rel.object_name == "Northgate Holdings, Inc."
    # Same corporate/infrastructure confidence split the GLEIF RR adapter
    # uses -- a state filing is strong identity evidence, zero infrastructure
    # evidence, and the two must never be conflated into one score.
    assert rel.attributes["corporate_relationship_confidence"] == "high"
    assert rel.attributes["infrastructure_attribution_confidence"] == "unknown"
    assert rel.attributes["signal_precedence"] == "pre_disclosure"


def test_provider_evidence_carries_source_document_id_and_date():
    provider = StateFilingProvider()
    result = provider.from_text(IMMEDIATE_EFFECTIVE_CERT, source_document_id="DE-CoM-test-001")
    evidence = result.relationships[0].evidence[0]
    assert evidence.evidence_type == "state_certificate_of_merger"
    assert evidence.source_document_id == "DE-CoM-test-001"
    # No explicit effective date in this fixture -- falls back to
    # executed_date rather than being left blank, since that's the best
    # known date, but effective_basis in attributes still distinguishes it
    # from a confirmed legal effective date.
    assert evidence.source_date == "March 14, 2024"
    assert evidence.attributes["effective_basis"] == "EFFECTIVE_ON_FILING"


def test_explicit_date_fixture_prefers_effective_date_as_source_date():
    provider = StateFilingProvider()
    result = provider.from_text(EXPLICIT_DATE_CERT, source_document_id="DE-CoM-test-002")
    evidence = result.relationships[0].evidence[0]
    assert evidence.source_date == "July 1, 2024"


def test_inline_jurisdiction_clause_does_not_bleed_into_name():
    # Real-filing variant: naming and jurisdiction stated in ONE sentence
    # ("...is X, a Delaware corporation") rather than split across
    # separate numbered paragraphs the way the two original reference
    # filings do it. A naive greedy-to-line-end capture has no reason to
    # stop before "a Delaware corporation" since every character in that
    # clause is itself a valid name character -- this was a real bug
    # caught while stress-testing against a second phrasing style, not a
    # hypothetical.
    parsed = extract_certificate_of_merger(INLINE_JURISDICTION_CERT)
    assert parsed["surviving_entity"] == "Stonebridge Logistics Corp."
    assert parsed["merging_entity"] == "Harborview Merger Sub Inc."
    assert parsed["constituent_jurisdictions"]["Stonebridge Logistics Corp."] == "Delaware"


def test_provider_returns_none_for_non_certificate_text():
    provider = StateFilingProvider()
    assert provider.from_text(NOT_A_CERTIFICATE) is None
