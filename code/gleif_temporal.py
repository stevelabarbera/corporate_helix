#!/usr/bin/env python3
"""Conservative GLEIF relationship current-support assessment.

Accounting periods are financial reporting windows, NOT ownership start/end.
A GLEIF snapshot cannot prove an exact historical control timeline.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from root_entity_resolver import _parse_relationship_date


def assess_relationship(row: dict[str, Any], as_of: date,
                        periods: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    periods = periods or []
    flags: list[str] = []
    def read(value: Any) -> date | None:
        try:
            return _parse_relationship_date(value)
        except (TypeError, ValueError):
            flags.append("INVALID_PERIOD_DATE")
            return None

    rel = [x for x in periods if x.get("period_type") == "RELATIONSHIP_PERIOD"]
    acct = [x for x in periods if x.get("period_type") == "ACCOUNTING_PERIOD"]
    if not rel and (row.get("relationship_start") or row.get("relationship_end")):
        rel = [{"start_date":row.get("relationship_start"),
                "end_date":row.get("relationship_end")}]
    if not acct and (row.get("accounting_start") or row.get("accounting_end")):
        acct = [{"start_date":row.get("accounting_start"),
                 "end_date":row.get("accounting_end")}]
    relationship_intervals = [(read(p.get("start_date")), read(p.get("end_date")))
                              for p in rel]
    accounting_intervals = [(read(p.get("start_date")), read(p.get("end_date")))
                            for p in acct]
    if any(start and end and start > end for start,end in
           relationship_intervals + accounting_intervals):
        flags.append("INVALID_PERIOD_ORDER")

    active = row.get("relationship_status") == "ACTIVE"
    published = row.get("registration_status") == "PUBLISHED"
    if not active:
        flags.append("RELATIONSHIP_STATUS_NOT_ACTIVE")
    if not published:
        flags.append("REGISTRATION_NOT_PUBLISHED")
    # A past explicit relationship END is meaningful; accounting END is not.
    explicit_ends = [end for start,end in relationship_intervals if end]
    has_open_eligible = any(
        (start is None or start <= as_of) and
        (end is None or end >= as_of)
        for start,end in relationship_intervals
    )
    if not rel:
        flags.append("NO_RELATIONSHIP_PERIOD")
    if explicit_ends and max(explicit_ends) < as_of and not has_open_eligible:
        flags.append("EXPLICIT_RELATIONSHIP_PERIOD_ENDED")
        state = "HISTORICAL_ONLY" if not active else "CURRENT_UNRESOLVED"
    elif any(start and start > as_of for start,end in relationship_intervals) and not has_open_eligible:
        flags.append("RELATIONSHIP_START_IN_FUTURE")
        state = "CURRENT_UNRESOLVED"
    elif not active or not published or "INVALID_PERIOD_ORDER" in flags or "INVALID_PERIOD_DATE" in flags:
        state = "CURRENT_UNRESOLVED"
    else:
        # Accounting ends are not evidence of divestiture. Old reporting or
        # absent accounting windows should not qualify as current supported.
        recent = any(
            start is not None and start <= as_of and end is not None
            and end <= as_of and (as_of - end).days <= 730
            for start,end in accounting_intervals
        ) or any(start is not None and start <= as_of and
                 (end is None or end >= as_of) for start,end in accounting_intervals)
        if not recent:
            flags.append("NO_RECENT_ACCOUNTING_SUPPORT")
            state = "CURRENT_UNRESOLVED"
        elif not has_open_eligible:
            flags.append("NO_CURRENT_RELATIONSHIP_PERIOD_SUPPORT")
            state = "CURRENT_UNRESOLVED"
        else:
            state = "CURRENT_SUPPORTED"

    return {
        "classification": state,
        "reasons": sorted(set(flags)),
        "as_of_date": as_of.isoformat(),
        "relationship_period_count": len(rel),
        "accounting_period_count": len(acct),
        "snapshot_ownership_proven": False,
        "asm_scope_authorized": False,
        "accounting_end_is_divestiture": False,
        "historical_control_proven": False,
    }
