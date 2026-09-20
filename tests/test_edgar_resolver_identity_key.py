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
