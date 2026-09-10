#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CODE = REPO / "code"
if str(CODE) not in sys.path:
    sys.path.insert(0, str(CODE))

import domain_discovery
from domain_candidates import CorporateEntity
from providers.official_site import OfficialSiteObservation, inspect_html

LEGAL = "NTT RESEARCH, INC."


def test_third_party_exact_name_is_not_official():
    html = f"""
    <html><head><title>{LEGAL} - Encyclopedia Entry</title></head>
    <body><h1>{LEGAL}</h1><p>{LEGAL} is a technology research company.</p></body></html>
    """
    result = inspect_html("https://en.wikipedia.org/wiki/NTT_Research", html, LEGAL)
    assert result.exact_legal_name_match is True
    assert result.official_declaration_match is False
    print("PASS test_third_party_exact_name_is_not_official")


def test_registered_office_declaration_is_official():
    html = f"""
    <html><body><h1>Legal information</h1>
    <p>{LEGAL}</p><p>Registered office: 123 Example Street. Company number 12345678.</p>
    </body></html>
    """
    result = inspect_html("https://research.example/legal", html, LEGAL)
    assert result.official_declaration_match is True
    print("PASS test_registered_office_declaration_is_official")


def test_copyright_footer_declaration_is_official():
    html = f"""
    <html><body><main>Research</main>
    <footer>Copyright 2026 {LEGAL}. All rights reserved.</footer>
    </body></html>
    """
    result = inspect_html("https://research.example/", html, LEGAL)
    assert result.official_declaration_match is True
    print("PASS test_copyright_footer_declaration_is_official")


def test_legal_path_alone_is_not_enough():
    html = f"""
    <html><body><h1>{LEGAL}</h1><p>Third-party company profile.</p></body></html>
    """
    result = inspect_html("https://directory.example/legal/company/ntt-research", html, LEGAL)
    assert result.exact_legal_name_match is True
    assert result.official_declaration_match is False
    print("PASS test_legal_path_alone_is_not_enough")


def test_denylisted_reference_domain_cannot_declare_even_with_marker_nearby():
    # This is the actual NTT-run failure mode (CONTEXT.md sec 34.1-34.2): a
    # third-party page mentions the target's exact legal name AND has its own
    # unrelated copyright/legal footer nearby. Before this fix, that combo
    # alone was enough to satisfy official_declaration_match.
    html = f"""
    <html><head><title>{LEGAL} - Wikipedia</title></head>
    <body><h1>{LEGAL}</h1><p>{LEGAL} is a technology research subsidiary.</p>
    <footer>Text is available under CC BY-SA. Copyright and related rights info.</footer>
    </body></html>
    """
    result = inspect_html("https://en.wikipedia.org/wiki/NTT_Research", html, LEGAL)
    assert result.exact_legal_name_match is True
    assert result.official_declaration_match is False
    assert result.declaration_reason == "third_party_reference_domain"
    print("PASS test_denylisted_reference_domain_cannot_declare_even_with_marker_nearby")


def test_genuine_self_declaration_on_non_listed_domain_still_passes():
    html = f"""
    <html><body><main>Research</main>
    <footer>Copyright 2026 {LEGAL}. All rights reserved.</footer></body></html>
    """
    result = inspect_html("https://research.example/", html, LEGAL)
    assert result.official_declaration_match is True
    print("PASS test_genuine_self_declaration_on_non_listed_domain_still_passes")


def test_unlisted_third_party_site_is_a_known_open_gap():
    # Honesty check, not a passing guarantee: a third-party site NOT on the
    # denylist, with its own copyright footer near the target's name, is
    # NOT caught by this fix. This test documents that limitation on
    # purpose so it can't silently regress into looking "fixed" -- if this
    # assertion starts failing, someone made the heuristic itself smarter
    # (see the module docstring: don't turn this into a classification
    # engine) rather than extending the explicit denylist, and that
    # decision deserves a deliberate review, not a silent test change.
    html = f"""
    <html><body><h1>{LEGAL}</h1><p>{LEGAL} profile.</p>
    <footer>Copyright 2026 SomeRandomDirectory.example. All rights reserved.</footer>
    </body></html>
    """
    result = inspect_html("https://www.somerandomdirectory.example/ntt-research", html, LEGAL)
    assert result.official_declaration_match is True  # known gap, not a target to fix here
    print("PASS test_unlisted_third_party_site_is_a_known_open_gap (documents an open limitation)")


def _entity():
    return CorporateEntity(
        entity_name=LEGAL,
        entity_lei="549300OXHX97T7TAJB83",
        relationships=["ULTIMATE_ACCOUNTING_CHILD"],
        corporate_confidence="HIGH",
        jurisdiction="US-DE",
        source="GLEIF",
    )


def test_domain_discovery_does_not_promote_plain_exact_name():
    entity = _entity()
    seeds = [{
        "entity_lei": entity.entity_lei,
        "entity_name": entity.entity_name,
        "url": "https://en.wikipedia.org/wiki/NTT_Research",
        "provider": "WEB_SEARCH",
        "title": LEGAL,
    }]
    original = domain_discovery.fetch_and_inspect
    try:
        domain_discovery.fetch_and_inspect = lambda *a, **k: OfficialSiteObservation(
            url=seeds[0]["url"],
            domain="en.wikipedia.org",
            title=LEGAL,
            page_text=LEGAL,
            matched_name=LEGAL,
            exact_legal_name_match=True,
            match_method="normalized_exact_legal_name",
            official_declaration_match=False,
            declaration_reason="exact_name_without_self_identification",
            status_code=200,
        )
        observations = domain_discovery.build_discovery_observations(
            [entity], seeds, verify_official=True
        )
    finally:
        domain_discovery.fetch_and_inspect = original
    assert [x["evidence_type"] for x in observations] == ["CANDIDATE_DISCOVERY"]
    print("PASS test_domain_discovery_does_not_promote_plain_exact_name")


def test_domain_discovery_promotes_qualified_declaration():
    entity = _entity()
    seeds = [{
        "entity_lei": entity.entity_lei,
        "entity_name": entity.entity_name,
        "url": "https://research.example/legal",
        "provider": "WEB_SEARCH",
        "title": "Legal",
    }]
    original = domain_discovery.fetch_and_inspect
    try:
        domain_discovery.fetch_and_inspect = lambda *a, **k: OfficialSiteObservation(
            url=seeds[0]["url"],
            domain="research.example",
            title="Legal",
            page_text=f"{LEGAL} Registered office",
            matched_name=LEGAL,
            exact_legal_name_match=True,
            match_method="normalized_exact_legal_name+self_identification",
            official_declaration_match=True,
            declaration_reason="nearby_self_identification:registered_office",
            status_code=200,
        )
        observations = domain_discovery.build_discovery_observations(
            [entity], seeds, verify_official=True
        )
    finally:
        domain_discovery.fetch_and_inspect = original
    assert [x["evidence_type"] for x in observations] == [
        "CANDIDATE_DISCOVERY", "OFFICIAL_WEBSITE"
    ]
    assert observations[1]["supports_attribution"] is True
    print("PASS test_domain_discovery_promotes_qualified_declaration")


if __name__ == "__main__":
    funcs = [
        test_third_party_exact_name_is_not_official,
        test_registered_office_declaration_is_official,
        test_copyright_footer_declaration_is_official,
        test_legal_path_alone_is_not_enough,
        test_denylisted_reference_domain_cannot_declare_even_with_marker_nearby,
        test_genuine_self_declaration_on_non_listed_domain_still_passes,
        test_unlisted_third_party_site_is_a_known_open_gap,
        test_domain_discovery_does_not_promote_plain_exact_name,
        test_domain_discovery_promotes_qualified_declaration,
    ]
    failed = 0
    for fn in funcs:
        try:
            fn()
        except Exception as exc:
            failed += 1
            print(f"FAIL {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"{len(funcs)-failed} passed / {failed} failed")
    raise SystemExit(1 if failed else 0)
