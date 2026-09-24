import importlib.util
from pathlib import Path

P = Path(__file__).resolve().parents[1] / "code/eval/run_ma_s2_comparison.py"
spec = importlib.util.spec_from_file_location("ma_s2", P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def result(*events):
    return {"company_id": "issuer", "baseline_commit": "abc", "gold_events": list(events)}


def event(event_id, stage):
    return {"id": event_id, "counterparty": "Target, Inc.", "deepest_stage": stage}


def test_compare_results_reports_stage_movement():
    comparison = m.compare_results(
        result(event("advanced", "ENTITY_RECOGNIZED"),
               event("unchanged", "LOCATOR_CAPTURED"),
               event("regressed", "EVENT_EXTRACTED")),
        result(event("advanced", "EVENT_EXTRACTED"),
               event("unchanged", "LOCATOR_CAPTURED"),
               event("regressed", "ENTITY_RECOGNIZED")),
    )
    assert comparison["counts"] == {
        "ADVANCED": 1, "UNCHANGED": 1, "REGRESSED": 1, "ADDED": 0, "REMOVED": 0,
    }


def test_compare_results_keeps_added_and_removed_events_visible():
    comparison = m.compare_results(
        result(event("removed", "CIK_RESOLVED")),
        result(event("added", "CANDIDATE_EMITTED")),
    )
    assert comparison["counts"]["ADDED"] == 1
    assert comparison["counts"]["REMOVED"] == 1
    assert [row["event_id"] for row in comparison["events"]] == ["added", "removed"]


def test_load_result_at_ref_reads_immutable_s1_snapshot():
    baseline = m.load_result_at_ref(
        m.S1_SNAPSHOT_REF,
        m.BASELINE_RESULTS / "northrop_grumman.json",
    )
    assert baseline["company_id"] == "northrop_grumman"
    assert all(event["deepest_stage"] == "CIK_UNRESOLVED" for event in baseline["gold_events"])
