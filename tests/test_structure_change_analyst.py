import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from adjudication.structure_change_packet import build_structure_change_packet
from analysts.structure_change_analyst import validate_structure_change_result


CHANGE = {
    "change_type": "DISAPPEARED_FROM_DISCLOSURE",
    "identity_key": "example subsidiary inc",
    "previous_filing_date": "2020-03-01",
    "current_filing_date": "2021-03-01",
}
EVIDENCE = [{
    "evidence_id": "sec:a:1",
    "accession": "a",
    "filing_date": "2020-08-01",
    "form": "8-K",
    "item": "2.01",
    "source_url": "https://www.sec.gov/example",
    "text": "On July 31, 2020, Example Corp completed the sale of Example Subsidiary Inc.",
}]


def packet():
    return build_structure_change_packet(CHANGE, EVIDENCE)


def valid_result():
    return {
        "decision": "SUPPORTED_DIVESTITURE",
        "confidence": "HIGH",
        "subject_identity_key": "example subsidiary inc",
        "supporting_evidence_ids": ["sec:a:1"],
        "conflicting_evidence_ids": [],
        "supporting_excerpt": EVIDENCE[0]["text"],
        "event_date": "2020-07-31",
        "rationale": "The supplied Item 2.01 explicitly reports completion of the sale.",
    }


def test_accepts_supported_result_but_keeps_it_advisory():
    result = validate_structure_change_result(valid_result(), packet(), model="test")
    assert result["decision"] == "SUPPORTED_DIVESTITURE"
    assert result["advisory_only"] is True
    assert result["creates_trusted_graph_edges"] is False


def test_accepts_explicitly_supported_merger():
    raw = valid_result()
    raw.update({
        "decision": "SUPPORTED_MERGER",
        "supporting_excerpt": EVIDENCE[0]["text"],
        "rationale": "The supplied evidence explicitly states the merger.",
    })
    result = validate_structure_change_result(raw, packet(), model="test")
    assert result["decision"] == "SUPPORTED_MERGER"
    assert result["advisory_only"] is True


def test_rejects_unknown_evidence_id():
    raw = valid_result()
    raw["supporting_evidence_ids"] = ["invented"]
    with pytest.raises(ValueError, match="Unknown evidence IDs"):
        validate_structure_change_result(raw, packet())


def test_rejects_invented_excerpt():
    raw = valid_result()
    raw["supporting_excerpt"] = "The subsidiary was definitely sold."
    with pytest.raises(ValueError, match="not verbatim"):
        validate_structure_change_result(raw, packet())


def test_rejects_subject_mismatch():
    raw = valid_result()
    raw["subject_identity_key"] = "different company"
    with pytest.raises(ValueError, match="does not match"):
        validate_structure_change_result(raw, packet())


def test_insufficient_evidence_can_abstain_without_citation():
    raw = valid_result()
    raw.update({
        "decision": "INSUFFICIENT_EVIDENCE",
        "confidence": "LOW",
        "supporting_evidence_ids": [],
        "supporting_excerpt": "",
        "event_date": None,
    })
    result = validate_structure_change_result(raw, packet())
    assert result["decision"] == "INSUFFICIENT_EVIDENCE"


def test_packet_rejects_duplicate_evidence_ids():
    with pytest.raises(ValueError, match="unique"):
        build_structure_change_packet(CHANGE, EVIDENCE + EVIDENCE)


def test_packet_contract_does_not_alias_global_allowed_decisions():
    first = packet()
    first["model_contract"]["allowed_decisions"].remove("SUPPORTED_MERGER")
    second = packet()
    assert "SUPPORTED_MERGER" in second["model_contract"]["allowed_decisions"]
