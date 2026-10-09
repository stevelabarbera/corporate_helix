import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from adjudication.structure_change_packet import build_structure_change_packet
from run_structure_change_analyst import LLM_REVIEW_STATUS, main, review_packet


CHANGE = {
    "change_type": "DISAPPEARED_FROM_DISCLOSURE",
    "identity_key": "target capital corporation",
    "previous_filing_date": "2020-03-11",
    "current_filing_date": "2021-03-10",
}
EVIDENCE = [{
    "evidence_id": "secpass:target",
    "text": "This entity was merged into Target Brands, Inc. effective February 2, 2020.",
}]
RESULT = {
    "decision": "SUPPORTED_MERGER",
    "confidence": "HIGH",
    "subject_identity_key": "target capital corporation",
    "supporting_evidence_ids": ["secpass:target"],
    "conflicting_evidence_ids": [],
    "supporting_excerpt": EVIDENCE[0]["text"],
    "event_date": "2020-02-02",
    "rationale": "The supplied disclosure explicitly states the merger.",
    "model": "test",
    "prompt_version": "test",
    "advisory_only": True,
    "creates_trusted_graph_edges": False,
}


class FakeAnalyst:
    def analyze(self, packet):
        return dict(RESULT)


def packet():
    return build_structure_change_packet(CHANGE, EVIDENCE)


def test_review_records_llm_result_without_finalizing_packet():
    source = packet()
    reviewed = review_packet(source, FakeAnalyst())

    assert source["adjudication"]["llm"] is None
    assert reviewed["adjudication"]["status"] == LLM_REVIEW_STATUS
    assert reviewed["adjudication"]["llm"]["decision"] == "SUPPORTED_MERGER"
    assert reviewed["adjudication"]["human"] is None
    assert reviewed["adjudication"]["final"] is None


def test_review_rejects_stale_embedded_contract():
    source = packet()
    source["model_contract"]["allowed_decisions"].remove("SUPPORTED_MERGER")
    with pytest.raises(ValueError, match="contract is stale"):
        review_packet(source, FakeAnalyst())


def test_review_refuses_to_replace_final_adjudication():
    source = packet()
    source["adjudication"]["final"] = {"decision": "SUPPORTED_MERGER"}
    with pytest.raises(ValueError, match="final adjudication"):
        review_packet(source, FakeAnalyst())


def test_cli_does_not_overwrite_existing_output(tmp_path, capsys):
    packet_path = tmp_path / "packet.json"
    output_path = tmp_path / "reviewed.json"
    packet_path.write_text(json.dumps(packet()))
    output_path.write_text("preserve me")

    assert main(["--packet", str(packet_path), "--out", str(output_path)]) == 2
    assert output_path.read_text() == "preserve me"
    assert "Output already exists" in capsys.readouterr().err
