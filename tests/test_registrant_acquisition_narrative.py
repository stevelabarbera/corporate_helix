#!/usr/bin/env python3
"""Real CrowdStrike 10-K phrasings that used to be recognised as organizations but produced no event."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from parsers.edgar_longform_locator import locate_ma_regions
from providers.edgar_ma_provider import EdgarMAExpansionProvider

P = EdgarMAExpansionProvider(fetch_filings_fn=lambda _: {})


def _events(text):
    regs = locate_ma_regions(text, form="10-K")
    return [(e["event_type"], e["object"]) for e in P._parse_filing_section(regs[0]["text"], None)["raw_events"]]


@pytest.mark.parametrize("text,expected", [
    ("On March 26, 2024, the Company acquired 100 % of the equity interest of Flow Security Ltd. (“Flow Security”), "
     "a leading provider of data security solutions. The acquisition has been accounted for as a business combination.",
     [("ACQUIRED", "Flow Security Ltd.")]),
    ("On September 28, 2023, the Company acquired 100 % of the equity interest of Bionic Stork, Ltd. (“Bionic”), "
     "a privately-held company.", [("ACQUIRED", "Bionic Stork, Ltd.")]),
    ("On January 12, 2026, we entered into a definitive agreement to acquire 100%of the equity interest of Seraphic "
     "Algorithms Ltd. (“Seraphic”), a leader in browser runtime security. The acquisition closed on February 3, 2026.",
     [("AGREED_TO_ACQUIRE", "Seraphic Algorithms Ltd."), ("ACQUIRED", "Seraphic Algorithms Ltd.")]),
    ("On January 7, 2026, the Company entered into a definitive agreement to acquire 100 % of the equity interest of "
     "SGNL.AI, Inc., a leader in continuous identity. The acquisition closed on February 20, 2026.",
     [("AGREED_TO_ACQUIRE", "SGNL.AI, Inc."), ("ACQUIRED", "SGNL.AI, Inc.")]),
])
def test_narrative_phrasings_now_produce_events(text, expected):
    assert _events(text) == expected


def test_agreement_without_closing_language_is_not_called_acquired():
    text = ("On March 3, 2024, we entered into a definitive agreement to acquire Flow Security Ltd., a privately held "
            "company. The purchase price for the transaction will be approximately $115.0 million, subject to customary "
            "closing adjustments.")
    assert _events(text) == [("AGREED_TO_ACQUIRE", "Flow Security Ltd.")]


def test_literal_we_acquired_is_not_duplicated():
    text = ("On March 5, 2021, we acquired Humio Limited (“Humio”), a privately-held company that provides "
            "log management.")
    assert _events(text) == [("ACQUIRED", "Humio Limited")]
