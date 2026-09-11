#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code" / "eval"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from coverage_harness import (
    FailureStage,
    GoldEvent,
    SystemEvent,
    aggregate_reports,
    score_company,
    wilson_interval,
)


def test_exact_match_scores_none():
    gold = [GoldEvent("a", "Splunk Inc.", "ACQUIRED", "COMPLETED")]
    system = [SystemEvent("Splunk Inc.", "ACQUIRED", "COMPLETED")]
    report = score_company("Cisco", gold, system)
    assert report.matches[0].stage is FailureStage.NONE
    assert report.recall == 1.0


def test_missing_counterparty_is_not_discovered():
    gold = [GoldEvent("a", "Splunk Inc.", "ACQUIRED", "COMPLETED")]
    system = []
    report = score_company("Cisco", gold, system)
    assert report.matches[0].stage is FailureStage.NOT_DISCOVERED
    assert report.recall == 0.0


def test_wrong_event_type_is_tagged_distinctly_from_not_discovered():
    gold = [GoldEvent("a", "Splunk Inc.", "ACQUIRED", "COMPLETED")]
    system = [SystemEvent("Splunk Inc.", "AGREED_TO_ACQUIRE", "COMPLETED")]
    report = score_company("Cisco", gold, system)
    assert report.matches[0].stage is FailureStage.EVENT_TYPE_MISMATCH


def test_wrong_status_is_tagged_distinctly():
    gold = [GoldEvent("a", "Splunk Inc.", "ACQUIRED", "COMPLETED")]
    system = [SystemEvent("Splunk Inc.", "ACQUIRED", "PROPOSED")]
    report = score_company("Cisco", gold, system)
    assert report.matches[0].stage is FailureStage.STATUS_MISMATCH


def test_event_type_equivalence_merged_into_and_acquired():
    gold = [GoldEvent("a", "VMware, Inc.", "ACQUIRED", "COMPLETED")]
    system = [SystemEvent("VMware, Inc.", "MERGED_INTO", "COMPLETED")]
    report = score_company("Broadcom", gold, system)
    assert report.matches[0].stage is FailureStage.NONE


def test_name_matching_ignores_legal_suffix_and_case():
    gold = [GoldEvent("a", "splunk inc", "ACQUIRED", "COMPLETED")]
    system = [SystemEvent("Splunk Inc.", "ACQUIRED", "COMPLETED")]
    report = score_company("Cisco", gold, system)
    assert report.matches[0].stage is FailureStage.NONE


def test_unmatched_system_events_are_reported_separately():
    gold = [GoldEvent("a", "Splunk Inc.", "ACQUIRED", "COMPLETED")]
    system = [
        SystemEvent("Splunk Inc.", "ACQUIRED", "COMPLETED"),
        SystemEvent("Some Other Corp.", "ACQUIRED", "COMPLETED"),
    ]
    report = score_company("Cisco", gold, system)
    assert len(report.unmatched_system_events) == 1
    assert report.unmatched_system_events[0].counterparty == "Some Other Corp."


def test_wilson_interval_is_wide_at_small_n():
    low, high = wilson_interval(1, 3)
    assert high - low > 0.5  # small samples must produce an honest, wide interval


def test_wilson_interval_narrows_with_more_data():
    low_small, high_small = wilson_interval(50, 100)
    low_large, high_large = wilson_interval(500, 1000)
    assert (high_large - low_large) < (high_small - low_small)


def test_aggregate_reports_across_multiple_companies():
    r1 = score_company("A", [GoldEvent("a1", "X Inc.", "ACQUIRED", "COMPLETED")],
                        [SystemEvent("X Inc.", "ACQUIRED", "COMPLETED")])
    r2 = score_company("B", [GoldEvent("b1", "Y Inc.", "ACQUIRED", "COMPLETED")], [])
    agg = aggregate_reports([r1, r2])
    assert agg["companies_evaluated"] == 2
    assert agg["total_gold_events"] == 2
    assert agg["recall_hits"] == 1
    assert agg["recall"] == 0.5
    assert agg["failure_stage_breakdown"]["NOT_DISCOVERED"] == 1
    assert agg["failure_stage_breakdown"]["NONE"] == 1
