#!/usr/bin/env python3
"""
Regression test for a real bug found via the Disney/Fox cold-run data
(CONTEXT.md M3.8.5 legal-text parser): the shared entity-name regex used
by RegexBackend and LegalRulesBackend could match an entire clause/sentence
instead of just the organization name, whenever the clause contained an
earlier capitalized word and no other corporate-suffix occurrence before
the real one. On real EDGAR text this produced organization names like
"Disney will make a cash payment to New Fox, Inc." instead of "New Fox,
Inc.", which then poisoned the alias map and (in that filing) suppressed
event detection entirely.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

_spec = importlib.util.spec_from_file_location(
    "m385", Path(__file__).resolve().parents[1] / "code" / "benchmark_m385_merger_coref.py"
)
m385 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m385)

# Real text pulled from data/raw/edgar_disney_fox_cold_m386.json
REAL_BAD_1 = (
    "Additionally, if the final estimate of such tax liabilities is lower than "
    "$8.5 billion, Disney will make a cash payment to New Fox, Inc. (\u201cNew Fox\u201d) "
    "reflecting the difference between such amount and $8.5 billion"
)
REAL_BAD_2 = (
    "On June 20, 2018, concurrently with the execution of the Amended and Restated "
    "Merger Agreement, Disney entered into an Amended and Restated Voting Agreement "
    "with Murdoch Family Trust and Cruden Financial Services LLC (collectively,"
)


def test_regex_backend_does_not_swallow_preceding_clause():
    backend = m385.RegexBackend()
    result = backend.parse(REAL_BAD_1)
    assert "New Fox, Inc." in result["orgs"], result["orgs"]
    assert not any(o.startswith("Disney will make") for o in result["orgs"]), result["orgs"]
    print("PASS test_regex_backend_does_not_swallow_preceding_clause")


def test_regex_backend_multi_word_connector_entity_still_matches():
    backend = m385.RegexBackend()
    result = backend.parse(REAL_BAD_2)
    assert "Murdoch Family Trust and Cruden Financial Services LLC" in result["orgs"], result["orgs"]
    assert not any(o.startswith("Voting Agreement with") for o in result["orgs"]), result["orgs"]
    print("PASS test_regex_backend_multi_word_connector_entity_still_matches")


def test_numeric_token_in_entity_name_still_matches():
    # "TWDC Holdco 613 Corp." -- a digit-led token mid-name must not break
    # the word chain.
    backend = m385.RegexBackend()
    result = backend.parse("The parties formed TWDC Holdco 613 Corp. for this purpose.")
    assert "TWDC Holdco 613 Corp." in result["orgs"], result["orgs"]
    print("PASS test_numeric_token_in_entity_name_still_matches")


def test_legal_rules_backend_same_fix_applies():
    # LegalRulesBackend shares the same ENT regex and must be fixed too --
    # this was originally duplicated code with the identical bug in both
    # classes.
    backend = m385.LegalRulesBackend()
    text = REAL_BAD_1 + ' (referred to herein as "New Fox")'
    result = backend.parse(text)
    assert not any(o.startswith("Disney will make") for o in result["orgs"]), result["orgs"]
    print("PASS test_legal_rules_backend_same_fix_applies")


def test_hyphenated_name_still_matches():
    backend = m385.RegexBackend()
    result = backend.parse("The merger with Twenty-First Century Fox, Inc. was completed.")
    assert "Twenty-First Century Fox, Inc." in result["orgs"], result["orgs"]
    print("PASS test_hyphenated_name_still_matches")


def test_company_suffix_is_recognized():
    # "The Walt Disney Company" has no Inc./Corp./LLC suffix at all -- its
    # legal name genuinely ends in the plain word "Company". Before this
    # fix, ANY company using this extremely common naming convention (Ford
    # Motor Company, The Boeing Company, The Coca-Cola Company, etc.) was
    # entirely invisible to entity extraction. Found via a real Disney 8-K,
    # not a hypothetical.
    backend = m385.RegexBackend()
    result = backend.parse('On December 13, 2017, The Walt Disney Company ("Disney") entered into an Agreement and Plan of Merger.')
    assert "The Walt Disney Company" in result["orgs"], result["orgs"]
    print("PASS test_company_suffix_is_recognized")


def test_generic_self_reference_the_company_is_not_a_false_positive():
    # The flip side of the fix above: "the Company" is a near-universal
    # generic self-reference convention in SEC filings and must NOT be
    # extracted as if it were a real, distinctly-named entity.
    backend = m385.RegexBackend()
    result = backend.parse("References in this report to the Company refer to the registrant and its subsidiaries.")
    assert "the Company" not in [o.casefold() for o in result["orgs"]]
    assert "The Company" not in result["orgs"]
    print("PASS test_generic_self_reference_the_company_is_not_a_false_positive")


def test_closing_phrasing_previously_announced_parenthetical():
    # Real text from Lumen/CenturyLink's actual closing 8-K: "completed its
    # previously-announced acquisition (the "Acquisition") of X" -- the
    # original pattern only matched "completed its acquisition of X" or
    # "completed the previously announced transaction with X", missing this
    # entirely despite orgs/aliases being extracted correctly.
    text = ('On November 1, 2017, CenturyLink, Inc. completed its previously-announced '
            'acquisition (the "Acquisition") of Level 3 Communications, Inc.')
    aliases = {}
    orgs = ["CenturyLink, Inc.", "Level 3 Communications, Inc."]
    events = m385.infer_events(text, aliases, orgs, "2.01")
    completed = m385.completed_only(events)
    assert any(
        e["event_type"] == "ACQUIRED" and e["subject"] == "CenturyLink, Inc."
        and e["object"] == "Level 3 Communications, Inc." for e in completed
    ), completed
    print("PASS test_closing_phrasing_previously_announced_parenthetical")


def test_closing_phrasing_previously_announced_no_hyphen():
    # Real text from Tenable's actual Ermetic closing 8-K: "previously
    # announced" without the hyphen, a slightly different real-world variant.
    text = ('Tenable, Inc. completed its previously announced acquisition (the "Acquisition") '
            'of Ermetic Ltd., a company organized under the laws of the State of Israel.')
    aliases = {}
    orgs = ["Tenable, Inc.", "Ermetic Ltd."]
    events = m385.infer_events(text, aliases, orgs, "2.01")
    completed = m385.completed_only(events)
    assert any(
        e["event_type"] == "ACQUIRED" and e["subject"] == "Tenable, Inc."
        and e["object"] == "Ermetic Ltd." for e in completed
    ), completed
    print("PASS test_closing_phrasing_previously_announced_no_hyphen")


def test_closing_phrasing_original_patterns_still_work():
    # Guard against regressing the two patterns that already worked.
    text1 = "Cisco completed its acquisition of Splunk Inc. today."
    events1 = m385.completed_only(m385.infer_events(text1, {}, ["Cisco", "Splunk Inc."], "2.01"))
    assert any(e["event_type"] == "ACQUIRED" and e["object"] == "Splunk Inc." for e in events1)

    text2 = "Disney completed the previously announced transaction with Fox Corp. for various assets."
    events2 = m385.completed_only(m385.infer_events(text2, {}, ["Disney", "Fox Corp."], "2.01"))
    assert any(e["event_type"] == "ACQUIRED" and e["object"] == "Fox Corp." for e in events2)
    print("PASS test_closing_phrasing_original_patterns_still_work")


def test_acquired_pattern_resolves_short_aliases():
    # Real bug found on real Tesla/SolarCity closing 8-K text: "Tesla
    # completed its previously announced acquisition of SolarCity" -- both
    # "Tesla" and "SolarCity" are SHORT ALIASES here, never appearing in
    # their full suffixed forms anywhere in this text. known_prefix()
    # alone (matching only literal org-list entries) can never resolve
    # either side. Unlike the two cases above, neither "Tesla" nor
    # "SolarCity" is itself a member of `orgs` -- only their full forms
    # are, and only the aliases dict connects the two.
    aliases = {"Tesla": "Tesla Motors, Inc.", "SolarCity": "SolarCity Corporation"}
    orgs = ["Tesla Motors, Inc.", "SolarCity Corporation"]
    text = (
        "As described above, on the Closing Date, Tesla completed its "
        "previously announced acquisition of SolarCity. As a result of "
        "the Merger, SolarCity became a wholly owned subsidiary of Tesla."
    )
    events = m385.completed_only(m385.infer_events(text, aliases, orgs, "2.01"))
    acquired = [e for e in events if e["event_type"] == "ACQUIRED"]
    assert acquired, events
    assert acquired[0]["subject"] == "Tesla Motors, Inc.", acquired
    assert acquired[0]["object"] == "SolarCity Corporation", acquired
    print("PASS test_acquired_pattern_resolves_short_aliases")


def test_acquired_pattern_does_not_over_capture_leading_preamble():
    # Regression guard for a real failure hit while building the fix
    # above: an earlier attempt captured the acquirer via a generic
    # character-class group immediately before "completed", which
    # swallowed leading date/preamble text ("On November 1, 2017,
    # CenturyLink, Inc." instead of just "CenturyLink, Inc.") because a
    # non-greedy quantifier still lets the regex engine choose the
    # earliest possible match start. The fix must resolve the acquirer by
    # exact adjacency against known orgs/aliases, never a generic capture.
    text = ("On November 1, 2017, CenturyLink, Inc. completed its previously-announced "
            "acquisition (the \"Acquisition\") of Level 3 Communications, Inc.")
    events = m385.completed_only(m385.infer_events(text, {}, ["CenturyLink, Inc.", "Level 3 Communications, Inc."], "2.01"))
    acquired = [e for e in events if e["event_type"] == "ACQUIRED"]
    assert acquired, events
    assert acquired[0]["subject"] == "CenturyLink, Inc.", acquired
    print("PASS test_acquired_pattern_does_not_over_capture_leading_preamble")


def test_agreed_to_acquire_allows_definitive_modifier():
    # Real bug found on real AIG/Validus text: "entered into A DEFINITIVE
    # agreement and plan of merger" -- the trigger regex expected the
    # agreement name immediately after "a[n]", with nothing in between.
    aliases = {}
    orgs = ["American International Group, Inc.", "Validus Holdings, Ltd.", "Venus Holdings Limited"]
    text = (
        'American International Group, Inc. ("AIG") entered into a definitive '
        'agreement and plan of merger (the "Merger Agreement") with Venus Holdings '
        'Limited, a wholly owned subsidiary of AIG ("Merger Sub") and Validus '
        'Holdings, Ltd. ("Validus").'
    )
    events = m385.completed_only(m385.infer_events(text, aliases, orgs, "1.01"))
    agreed = [e for e in events if e["event_type"] == "AGREED_TO_ACQUIRE"]
    assert agreed, events
    assert agreed[0]["subject"] == "American International Group, Inc.", agreed
    print("PASS test_agreed_to_acquire_allows_definitive_modifier")


def test_agreed_to_acquire_skips_shell_named_first_in_with_clause():
    # Real bug found on the same AIG/Validus text: "with Venus Holdings
    # Limited, a wholly owned subsidiary of AIG ('Merger Sub') and Validus
    # Holdings, Ltd." -- the shell is named FIRST in the "with X and Y"
    # list. A prefix-only match would grab the shell as target instead of
    # the real company named second. This also exercises the truncation
    # fix: "Validus Holdings, Ltd." ends in a period, which an earlier,
    # narrower capture cut off before, so the org string never matched.
    aliases = {}
    orgs = ["American International Group, Inc.", "Validus Holdings, Ltd.", "Venus Holdings Limited"]
    text = (
        'American International Group, Inc. ("AIG") entered into a definitive '
        'agreement and plan of merger (the "Merger Agreement") with Venus Holdings '
        'Limited, a wholly owned subsidiary of AIG ("Merger Sub") and Validus '
        'Holdings, Ltd. ("Validus"), pursuant to which Merger Sub will merge with '
        'and into Validus.'
    )
    events = m385.completed_only(m385.infer_events(text, aliases, orgs, "1.01"))
    agreed = [e for e in events if e["event_type"] == "AGREED_TO_ACQUIRE"]
    assert agreed, events
    assert agreed[0]["object"] == "Validus Holdings, Ltd.", agreed


def test_divested_business_pattern_did_not_exist_before_this_fix():
    # DIVESTED_BUSINESS had NEVER been implemented anywhere in the
    # extractor -- gold files for Lumen (3 events) and Disney (1 event)
    # had referenced it since before this session, guaranteeing
    # NOT_DISCOVERED regardless of parsing quality. Found while
    # investigating a real AT&T divestiture. Validated here against real
    # Disney text: "Disney and FCN agreed to sell FCN's interests in Fox
    # Sports Net, LLC ('FSN') to Buyer ... (the 'FSN Sale')" / "the FSN
    # Sale was completed". The real buyer named in the text, "Diamond
    # Sports Group, LLC", is disclosed as "a wholly owned subsidiary of
    # Sinclair Broadcast Group, Inc." -- the real counterparty that
    # matters is the parent, matching this deal's actual gold record.
    aliases = {
        "Disney": "The Walt Disney Company",
        "FCN": "Fox Cable Networks, LLC",
        "Buyer": "Diamond Sports Group, LLC",
        "Sinclair": "Sinclair Broadcast Group, Inc.",
        "FSN": "Fox Sports Net, LLC",
    }
    orgs = [
        "Diamond Sports Group, LLC",
        "Fox Cable Networks, LLC",
        "Fox Sports Net, LLC",
        "Sinclair Broadcast Group, Inc.",
        "The Walt Disney Company",
    ]
    text = (
        'As previously announced, on May 3, 2019, The Walt Disney Company ("Disney"), '
        'Fox Cable Networks, LLC ("FCN"), a Delaware limited liability company and a '
        'wholly owned subsidiary of Disney, and Diamond Sports Group, LLC ("Buyer"), a '
        'Delaware limited liability company and a wholly owned subsidiary of Sinclair '
        'Broadcast Group, Inc. ("Sinclair"), entered into an Equity Purchase Agreement '
        '(the "Purchase Agreement"). Pursuant to the Purchase Agreement, Disney and FCN '
        "agreed to sell FCN's interests in Fox Sports Net, LLC (\"FSN\") to Buyer for a "
        'purchase price equal to $9.6 billion in cash, subject to adjustments as set '
        'forth in the Purchase Agreement (the "FSN Sale").\n\n'
        'On August 23, 2019 (the "Closing Date"), upon the terms and conditions set '
        'forth in the Purchase Agreement, the FSN Sale was completed.'
    )
    events = m385.completed_only(m385.infer_events(text, aliases, orgs, "2.01"))
    divested = [e for e in events if e["event_type"] == "DIVESTED_BUSINESS"]
    assert divested, events
    assert divested[0]["subject"] == "The Walt Disney Company", divested
    assert divested[0]["object"] == "Sinclair Broadcast Group, Inc.", divested
    print("PASS test_divested_business_pattern_did_not_exist_before_this_fix")


def test_divested_business_does_not_truncate_on_decimal_point():
    # Real bug found building the pattern above: "$9.6 billion" has its
    # own period, which an earlier, punctuation-bounded capture attempt
    # misread as a sentence boundary, cutting the buyer's name off
    # mid-window. The fix uses a fixed-length window instead -- this test
    # guards specifically against that regression re-appearing.
    aliases = {"Buyer": "Acme Sports Holdings, LLC"}
    orgs = ["Acme Media Co.", "Acme Sports Holdings, LLC"]
    text = (
        "Acme Media Co. agreed to sell its interests in a subsidiary to Buyer "
        "for a purchase price equal to $9.6 billion in cash (the \"Deal Sale\"). "
        "The Deal Sale was completed on a later date."
    )
    events = m385.completed_only(m385.infer_events(text, aliases, orgs, "2.01"))
    divested = [e for e in events if e["event_type"] == "DIVESTED_BUSINESS"]
    assert divested, events
    assert divested[0]["object"] == "Acme Sports Holdings, LLC", divested
    print("PASS test_agreed_to_acquire_skips_shell_named_first_in_with_clause")


def test_10k_declarative_acquisition_pattern():
    # Real text from Tenable's actual 10-K Business Combinations footnote.
    # Distinct document style from every 8-K pattern above: first-person
    # ("we acquired X"), never names the acquirer explicitly. Before this
    # pattern existed, infer_events() produced zero events for this text
    # even though orgs/aliases were extracted correctly -- there was no 10-K
    # discovery capability in this codebase at all.
    text = (
        'In October 2023, we acquired Ermetic Ltd. ("Ermetic"), an innovative cloud-native '
        "application protection platform company. We acquired 100% of Ermetic equity through "
        "a share purchase agreement for total consideration of $243.8 million."
    )
    aliases = {"Ermetic": "Ermetic Ltd."}
    orgs = ["Ermetic Ltd."]
    events = m385.completed_only(m385.infer_events(text, aliases, orgs, None))
    assert any(
        e["event_type"] == "ACQUIRED" and e["subject"] == "REGISTRANT_SELF_REFERENCE"
        and e["object"] == "Ermetic Ltd." for e in events
    ), events
    print("PASS test_10k_declarative_acquisition_pattern")


def test_10k_pattern_resolves_short_alias_form():
    # Real text: "we acquired Bit Discovery" uses the short alias-defined
    # name, not the full legal name with suffix -- known_prefix() alone
    # can't match this (the raw capture is SHORTER than the real org
    # string), so this also exercises the alias-resolution fallback.
    text = (
        'In June 2022, we acquired Bit Discovery, Inc. ("Bit Discovery"), a leader in external '
        "attack surface management. We acquired 100% of Bit Discovery equity for $43.8 million in cash."
    )
    aliases = {"Bit Discovery": "Bit Discovery, Inc."}
    orgs = ["Bit Discovery, Inc."]
    events = m385.completed_only(m385.infer_events(text, aliases, orgs, None))
    assert any(
        e["event_type"] == "ACQUIRED" and e["object"] == "Bit Discovery, Inc." for e in events
    ), events
    print("PASS test_10k_pattern_resolves_short_alias_form")


def test_10k_pattern_does_not_fire_on_8k_style_text():
    # Guard: the new pattern must not spuriously match ordinary 8-K text
    # that happens to contain the word "acquired" in a different
    # construction.
    text = "Cisco completed its acquisition of Splunk Inc. today."
    events = m385.completed_only(m385.infer_events(text, {}, ["Cisco", "Splunk Inc."], "2.01"))
    self_ref_events = [e for e in events if e["subject"] == "REGISTRANT_SELF_REFERENCE"]
    assert self_ref_events == [], self_ref_events
    print("PASS test_10k_pattern_does_not_fire_on_8k_style_text")


def test_entity_regex_does_not_bleed_across_blank_line():
    # Real bug found on real Ford 10-K text: an ALL-CAPS section header on
    # its own line, followed by a blank line, followed by the actual
    # sentence -- "ACQUISITIONS AND DIVESTITURES\nCompany Excluding Ford
    # Credit\n\nElectriphi, Inc. (...)" -- was captured as ONE entity name
    # spanning the whole header (via RegexBackend alone), because \s (used
    # to join words within an entity name) treats a blank line identically
    # to a single space. The fix requires two consecutive newlines (a real
    # paragraph/section break) to stop the word-chain, while still
    # allowing ordinary single-line wrapping within one sentence.
    #
    # Tested through the full fused EdgarMAExtractor pipeline, not a
    # single backend in isolation: a residual single-backend artifact
    # ("ACQUISITIONS AND DIVESTITURES Company", from "Company" itself
    # being a valid suffix joined across the header's own internal single
    # newline) never survives fusion -- spaCy's NER doesn't corroborate a
    # section header as an ORG, so it falls below the vote threshold and
    # is correctly dropped before reaching event inference. That's the
    # behavior that actually matters in production.
    text = (
        "ACQUISITIONS AND DIVESTITURES\n"
        "Company Excluding Ford Credit\n"
        "\n"
        "Electriphi, Inc. (\u201cElectriphi\u201d). On June 18, 2021, we acquired "
        "Electriphi, a California-based provider of charging management and "
        "fleet monitoring software for electric vehicles."
    )
    from parsers.edgar_ma_extractor import EdgarMAExtractor
    ex = EdgarMAExtractor()
    result = ex.parse_section(text, "10-K")
    assert result["fused"]["orgs"] == ["Electriphi, Inc."], result["fused"]["orgs"]
    self_ref = [
        e for e in result["raw_events"]
        if e["subject"] == "REGISTRANT_SELF_REFERENCE" and e["object"] == "Electriphi, Inc."
    ]
    assert self_ref and self_ref[0]["status"] == "COMPLETED", result["raw_events"]
    print("PASS test_entity_regex_does_not_bleed_across_blank_line")


def test_entity_regex_still_joins_across_a_single_line_wrap():
    # The fix must not become so strict it breaks ordinary line-wrapped
    # entity names (a single newline mid-sentence, not a paragraph break).
    # norm() collapses all whitespace (including the newline) to a single
    # space in the final output, same as it always has -- this test is
    # about the JOIN still happening at all, not about preserving the
    # literal newline.
    text = "Six Flags Entertainment\nCorporation, a Delaware corporation, today announced results."
    backend = m385.RegexBackend()
    result = backend.parse(text)
    assert "Six Flags Entertainment Corporation" in result["orgs"], result["orgs"]
    print("PASS test_entity_regex_still_joins_across_a_single_line_wrap")


if __name__ == "__main__":
    suite = [
        test_regex_backend_does_not_swallow_preceding_clause,
        test_regex_backend_multi_word_connector_entity_still_matches,
        test_numeric_token_in_entity_name_still_matches,
        test_legal_rules_backend_same_fix_applies,
        test_hyphenated_name_still_matches,
        test_company_suffix_is_recognized,
        test_generic_self_reference_the_company_is_not_a_false_positive,
        test_closing_phrasing_previously_announced_parenthetical,
        test_closing_phrasing_previously_announced_no_hyphen,
        test_closing_phrasing_original_patterns_still_work,
        test_acquired_pattern_resolves_short_aliases,
        test_acquired_pattern_does_not_over_capture_leading_preamble,
        test_agreed_to_acquire_allows_definitive_modifier,
        test_agreed_to_acquire_skips_shell_named_first_in_with_clause,
        test_divested_business_pattern_did_not_exist_before_this_fix,
        test_divested_business_does_not_truncate_on_decimal_point,
        test_10k_declarative_acquisition_pattern,
        test_10k_pattern_resolves_short_alias_form,
        test_10k_pattern_does_not_fire_on_8k_style_text,
        test_entity_regex_does_not_bleed_across_blank_line,
        test_entity_regex_still_joins_across_a_single_line_wrap,
    ]
    failed = 0
    for test in suite:
        try:
            test()
        except Exception as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
    print(f"{len(suite)-failed} passed / {failed} failed")
    raise SystemExit(1 if failed else 0)
