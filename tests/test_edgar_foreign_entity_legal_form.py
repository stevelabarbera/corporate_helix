#!/usr/bin/env python3
"""
Regression test for the M&A-S1 saturation baseline ENTITY_RECOGNITION_MISS
on Tenable's Alsid SAS acquisition (tenable-2, deepest stage
LOCATOR_CAPTURED).

Root cause: EDGAR filings almost always state a foreign counterparty's
legal form explicitly ("Alsid SAS, a company organized under the laws of
France"), but the pre-existing ENT_LEGALFORM pattern only covered the
opposite clause order ("..., a Delaware corporation" -- jurisdiction
before legal-form word). Neither RegexBackend nor LegalRulesBackend (both
built on the shared _entity_matches() helper) could see "Alsid SAS" at
all, so only spaCy's NER voted for it (weight 1.0), which fell below the
1.5 fusion threshold -- the org was silently dropped, with no indication
this was a foreign-entity-specific gap rather than a random miss.

Confirmed directly against Tenable's real 8-K text (accession
0001660280-21-000016, Item 1.01, 2021-02-10) fetched live from EDGAR.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from parsers.edgar_ma_extractor import EdgarMAExtractor, _entity_matches

REAL_ALSID_TEXT = (
    'On February 10, 2021, Tenable Network Security Ireland Limited '
    '(the "Purchaser"), an Irish private company limited by shares and '
    'indirect wholly-owned subsidiary or Tenable Holdings, Inc. '
    '("Tenable"), entered into a share purchase agreement (the "Purchase '
    'Agreement") by and among the Purchaser, Alsid SAS, a company '
    'organized under the laws of France ("Alsid"), the shareholders and '
    "warrantholders of Alsid."
)


def test_foreign_entity_under_laws_of_clause_recognized():
    ents = [name for name, _ in _entity_matches(REAL_ALSID_TEXT)]
    assert "Alsid SAS" in ents


def test_foreign_entity_clears_fusion_threshold_in_full_ensemble():
    ext = EdgarMAExtractor(allow_degraded=True)
    result = ext.parse_section(REAL_ALSID_TEXT, item="1.01")
    fused = result["fused"]
    assert "Alsid SAS" in fused["orgs"]
    assert fused["aliases"].get("Alsid") == "Alsid SAS"


def test_domestic_delaware_corporation_phrasing_still_works():
    # Make sure the new reversed-order pattern didn't crowd out or
    # duplicate the original (and still-needed) ENT_LEGALFORM order.
    text = "Paramount Global, a Delaware corporation, entered into an agreement."
    ents = [name for name, _ in _entity_matches(text)]
    assert "Paramount Global" in ents
