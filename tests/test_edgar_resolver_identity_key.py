#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from providers.edgar_resolver import identity_key


def test_leading_article_stripped():
    """identity_key must not distinguish 'The X Company' from 'X Co'.

    Regression for the M&A-S1 saturation baseline CIK_RESOLUTION_MISS on
    Disney: EDGAR's own registrant name for Disney's current CIK (1744489)
    is "Walt Disney Co" (no "The", "Co" not "Company"), while the study's
    company label is "The Walt Disney Company". Before this fix,
    identity_key("The Walt Disney Company") == "the walt disney" while
    identity_key("Walt Disney Co") == "walt disney" -- a permanent miss for
    an entity that otherwise resolves cleanly.
    """
    assert identity_key("The Walt Disney Company") == identity_key("Walt Disney Co")
    assert identity_key("The Walt Disney Company") == "walt disney"


def test_leading_article_only_stripped_at_start():
    # The article strip is anchored to the START of the string, so a "the"
    # appearing mid-name (not as a leading article) must be left alone.
    assert identity_key("Bank of the West") == "bank of the west"


def test_suffix_and_article_combine():
    assert identity_key("The Boeing Company") == identity_key("Boeing Co")


def test_no_leading_article_unaffected():
    assert identity_key("Twenty-First Century Fox, Inc.") == "twenty first century fox"


def test_stacked_corporate_suffixes_stripped_iteratively():
    """Regression for the M&A-S1 saturation baseline ENTITY_RECOGNITION_MISS
    on Lumen's Colt Technology Services divestiture.

    The extraction ensemble correctly found and scored "Colt Technology
    Services Group Limited" as an org (org_votes 2.75, well above the 1.5
    acceptance threshold) -- this was never a real NER failure. The gold
    label is the shorter "Colt Technology Services". A single suffix strip
    only removed "Limited" and left "group" dangling, so the two keys never
    matched. Suffix stripping must repeat until no more trailing
    corporate-form words match.
    """
    assert identity_key("Colt Technology Services Group Limited") == \
        identity_key("Colt Technology Services")
    assert identity_key("Colt Technology Services Group Limited") == \
        "colt technology services"


def test_stacked_suffix_does_not_over_strip_real_names():
    # "Group"/"Holdings" stripping should not eat load-bearing words that
    # happen to precede a genuine corporate-form suffix.
    assert identity_key("Apollo Global Management, Inc.") == "apollo global management"
    assert identity_key("Kraft Heinz Company") == "kraft heinz"
    assert identity_key("Northrop Grumman Corporation") == "northrop grumman"


def test_edgar_disambiguation_tag_stripped():
    """Regression for two real M&A-S1 saturation baseline CIK_RESOLUTION_MISS
    cases: Six Flags and (hypothesized, pending direct confirmation)
    Northrop Grumman.

    EDGAR appends a short bookkeeping tag to a registrant's own name when
    the plain name is ambiguous or has been reused across a corporate
    succession. Confirmed directly against the real company_tickers.json
    entry for CIK 1999001: "Six Flags Entertainment Corporation/NEW" --
    created at the 2024-07-01 Cedar Fair merger close, exactly matching
    the study's six_flags-2 gold event date. Before this fix, the trailing
    "/NEW" survived normalization and produced
    "six flags entertainment corporation new", which never matched the
    study's plain label "Six Flags Entertainment Corporation".
    """
    assert identity_key("Six Flags Entertainment Corporation/NEW") == \
        identity_key("Six Flags Entertainment Corporation")
    assert identity_key("Six Flags Entertainment Corporation/NEW") == \
        "six flags entertainment"

    # State-of-incorporation tag, as seen on Northrop Grumman's old-style
    # SGML filing headers ("NORTHROP GRUMMAN CORP /DE/"). Whether this is
    # actually what identity_key was being asked to match against for the
    # real CIK_RESOLUTION_MISS is still pending direct confirmation
    # against company_tickers.json (see docs/DECISIONS_EDGAR_MA.md
    # ADR-EDGAR-008) -- this test documents the intended behavior either
    # way, since the tag format itself is a known, general EDGAR pattern.
    assert identity_key("NORTHROP GRUMMAN CORP /DE/") == \
        identity_key("Northrop Grumman Corporation")


def test_edgar_disambiguation_tag_does_not_over_strip():
    # Don't eat a legitimate trailing short word that isn't a "/TAG".
    assert identity_key("Paramount Global") == "paramount global"
    assert identity_key("AT&T Inc.") == "at t"
