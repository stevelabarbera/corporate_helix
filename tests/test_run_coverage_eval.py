#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code" / "eval"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from run_coverage_eval import system_events_for_company


def _write_filing(tmp: Path, text: str) -> Path:
    data = {
        "company": "irrelevant -- filing text is what matters", "cik": "",
        "filings": [{"accession": "TEST-1", "filing_date": "2017-11-01", "form": "8-K",
                     "items": "2.01", "sections": [{"item": "2.01", "text": text}]}],
    }
    path = tmp / "fixture.json"
    path.write_text(json.dumps(data))
    return path


def test_current_name_alone_misses_a_pre_rebrand_filing():
    # The exact real bug found on Lumen: a filing from before a rebrand only
    # ever uses the old name, so querying with just the current name finds
    # nothing, even though the underlying parser would have worked fine.
    text = 'CenturyLink, Inc. completed its acquisition of Level 3 Communications, Inc. today.'
    with tempfile.TemporaryDirectory() as d:
        path = _write_filing(Path(d), text)
        events = system_events_for_company("Lumen Technologies, Inc.", [path])
        assert events == []


def test_alias_list_recovers_the_pre_rebrand_filing():
    # Same filing, now with the historical name supplied as an alias --
    # this is what actually closes the gap above.
    text = 'CenturyLink, Inc. completed its acquisition of Level 3 Communications, Inc. today.'
    with tempfile.TemporaryDirectory() as d:
        path = _write_filing(Path(d), text)
        events = system_events_for_company("Lumen Technologies, Inc.", [path], aliases=["CenturyLink, Inc."])
        assert len(events) == 1
        assert events[0].counterparty == "Level 3 Communications, Inc."
        assert events[0].event_type == "ACQUIRED"


def test_results_across_names_are_deduped_not_doubled():
    # If the SAME real filing happens to be discoverable under both the
    # current name and an alias (e.g. the filing text uses both names
    # somewhere), the same real event must not be double-counted just
    # because two different pivot names were tried against it.
    text = 'Example Corp. completed its acquisition of Target Inc. today.'
    with tempfile.TemporaryDirectory() as d:
        path = _write_filing(Path(d), text)
        events = system_events_for_company("Example Corp.", [path], aliases=["Example Corporation"])
        assert len(events) == 1
        assert events[0].counterparty == "Target Inc."
