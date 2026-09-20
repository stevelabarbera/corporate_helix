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
