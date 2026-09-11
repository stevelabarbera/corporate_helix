#!/usr/bin/env python3
"""
Corporation Helix -- EDGAR M&A coverage/accuracy evaluation harness.

The discipline this enforces: gold events must be written from independent
sources BEFORE the system's output is looked at (see gold_established_blind
in each data/eval_gold/*.json file). This module only scores; it has no
opinion about how gold was produced, but every score it reports should be
read as meaningless if that discipline wasn't followed for the input.

Every miss is tagged with WHICH STAGE failed, not just that it failed:

    NOT_DISCOVERED       -- no system event matches this gold event's
                             counterparty at all (never found the filing,
                             or the filing was found but produced nothing
                             for this counterparty)
    EVENT_TYPE_MISMATCH  -- the counterparty matched, but the extracted
                             event_type doesn't correspond to any type this
                             gold event's type maps to (see EVENT_TYPE_EQUIV)
    STATUS_MISMATCH      -- counterparty and event type both matched, but
                             COMPLETED/PROPOSED/TERMINATED disagrees

This distinction is what turns "the parser missed something" into an
actionable finding: a NOT_DISCOVERED cluster points at coverage of event
categories the extractor has no pattern for at all (e.g. divestitures);
an EVENT_TYPE_MISMATCH or STATUS_MISMATCH cluster points at a real
detection existing but being classified wrong.

A precision-side count (system events with no matching gold event) is
also reported, but treated with more caution: it counts everything the
gold record didn't happen to include, which is a real signal only if the
gold record's `events` list itself claims to be a complete list for its
scoped date range -- see each gold file's own scoping notes.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from providers.edgar_resolver import identity_key


# Different gold labelers and different filing text will describe the same
# real-world event with different (but equivalent) primitive names. This
# equivalence table exists so scoring reflects real coverage, not just
# whether the exact same string was used on both sides.
EVENT_TYPE_EQUIV: dict[str, set[str]] = {
    "AGREED_TO_ACQUIRE": {"AGREED_TO_ACQUIRE"},
    "ACQUIRED": {"ACQUIRED", "MERGED_INTO"},
    "MERGED_INTO": {"MERGED_INTO", "ACQUIRED"},
    "DIVESTED_BUSINESS": {"DIVESTED_BUSINESS", "DIVESTED"},
    "TERMINATED": {"TERMINATED"},
}


class FailureStage(str, Enum):
    NONE = "NONE"  # matched, no failure
    NOT_DISCOVERED = "NOT_DISCOVERED"
    EVENT_TYPE_MISMATCH = "EVENT_TYPE_MISMATCH"
    STATUS_MISMATCH = "STATUS_MISMATCH"


@dataclass
class GoldEvent:
    id: str
    counterparty: str
    event_type: str
    status: str
    approx_date: str = ""
    notes: str = ""

    @classmethod
    def from_mapping(cls, d: dict[str, Any]) -> "GoldEvent":
        return cls(
            id=d.get("id", ""), counterparty=d.get("counterparty", ""),
            event_type=d.get("event_type", ""), status=d.get("status", ""),
            approx_date=d.get("approx_date", ""), notes=d.get("notes", ""),
        )


@dataclass
class SystemEvent:
    counterparty: str
    event_type: str
    status: str
    accession: str = ""


@dataclass
class MatchResult:
    gold_id: str
    counterparty: str
    stage: FailureStage
    gold_event_type: str = ""
    system_event_type: str = ""
    gold_status: str = ""
    system_status: str = ""


@dataclass
class CompanyScoreReport:
    company: str
    matches: list[MatchResult] = field(default_factory=list)
    unmatched_system_events: list[SystemEvent] = field(default_factory=list)

    @property
    def recall_hits(self) -> int:
        return sum(1 for m in self.matches if m.stage is FailureStage.NONE)

    @property
    def total_gold(self) -> int:
        return len(self.matches)

    @property
    def recall(self) -> float:
        return self.recall_hits / self.total_gold if self.total_gold else 0.0

    def stage_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for m in self.matches:
            counts[m.stage.value] = counts.get(m.stage.value, 0) + 1
        return counts


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """
    Wilson score interval for a binomial proportion -- more reliable than
    the naive normal approximation at small n, which is exactly the regime
    this evaluation starts in (a handful of companies, a handful of events
    each). Returns (low, high) at the given confidence level (default 95%).
    """
    if n == 0:
        return (0.0, 1.0)
    phat = successes / n
    denom = 1 + z**2 / n
    center = (phat + z**2 / (2 * n)) / denom
    margin = (z * math.sqrt((phat * (1 - phat) / n) + (z**2 / (4 * n**2)))) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def _event_types_equivalent(gold_type: str, system_type: str) -> bool:
    equivalents = EVENT_TYPE_EQUIV.get(gold_type, {gold_type})
    return system_type in equivalents


def score_company(
    company: str, gold_events: list[GoldEvent], system_events: list[SystemEvent]
) -> CompanyScoreReport:
    report = CompanyScoreReport(company=company)
    remaining_system = list(system_events)

    for gold in gold_events:
        gold_key = identity_key(gold.counterparty)
        candidates = [s for s in remaining_system if identity_key(s.counterparty) == gold_key]

        if not candidates:
            report.matches.append(MatchResult(
                gold_id=gold.id, counterparty=gold.counterparty,
                stage=FailureStage.NOT_DISCOVERED,
                gold_event_type=gold.event_type, gold_status=gold.status,
            ))
            continue

        type_matches = [s for s in candidates if _event_types_equivalent(gold.event_type, s.event_type)]
        if not type_matches:
            chosen = candidates[0]
            report.matches.append(MatchResult(
                gold_id=gold.id, counterparty=gold.counterparty,
                stage=FailureStage.EVENT_TYPE_MISMATCH,
                gold_event_type=gold.event_type, system_event_type=chosen.event_type,
                gold_status=gold.status, system_status=chosen.status,
            ))
            remaining_system.remove(chosen)
            continue

        status_matches = [s for s in type_matches if s.status == gold.status]
        if not status_matches:
            chosen = type_matches[0]
            report.matches.append(MatchResult(
                gold_id=gold.id, counterparty=gold.counterparty,
                stage=FailureStage.STATUS_MISMATCH,
                gold_event_type=gold.event_type, system_event_type=chosen.event_type,
                gold_status=gold.status, system_status=chosen.status,
            ))
            remaining_system.remove(chosen)
            continue

        chosen = status_matches[0]
        report.matches.append(MatchResult(
            gold_id=gold.id, counterparty=gold.counterparty, stage=FailureStage.NONE,
            gold_event_type=gold.event_type, system_event_type=chosen.event_type,
            gold_status=gold.status, system_status=chosen.status,
        ))
        remaining_system.remove(chosen)

    report.unmatched_system_events = remaining_system
    return report


def aggregate_reports(reports: list[CompanyScoreReport]) -> dict[str, Any]:
    total_hits = sum(r.recall_hits for r in reports)
    total_gold = sum(r.total_gold for r in reports)
    low, high = wilson_interval(total_hits, total_gold)

    stage_totals: dict[str, int] = {}
    for r in reports:
        for stage, count in r.stage_counts().items():
            stage_totals[stage] = stage_totals.get(stage, 0) + count

    return {
        "companies_evaluated": len(reports),
        "total_gold_events": total_gold,
        "recall_hits": total_hits,
        "recall": (total_hits / total_gold) if total_gold else 0.0,
        "recall_95pct_ci": {"low": round(low, 3), "high": round(high, 3)},
        "failure_stage_breakdown": stage_totals,
        "total_unmatched_system_events": sum(len(r.unmatched_system_events) for r in reports),
        "note": (
            "Confidence interval width reflects sample size. With this few "
            "gold events, treat the interval as the honest headline number, "
            "not the point estimate alone."
        ),
    }
