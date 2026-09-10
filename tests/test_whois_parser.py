#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from evidence_contract import EvidenceAvailability
from parsers.whois_parser import parse_whois_text

CLEAN_CORPORATE_WHOIS = """
Domain Name: SONY.COM
Registry Domain ID: 12345_DOMAIN_COM-VRSN
Registrar WHOIS Server: whois.markmonitor.com
Registrant Organization: Sony Corporation
Registrant State/Province: Tokyo
Registrant Country: JP
Admin Organization: Sony Corporation
Name Server: NS1.SONY.COM
"""

GDPR_REDACTED_WHOIS = """
Domain Name: EXAMPLE.COM
Registry Domain ID: 999_DOMAIN_COM-VRSN
Registrant Organization: REDACTED FOR PRIVACY
Registrant Name: REDACTED FOR PRIVACY
Registrant Email: Please query the RDDS service of the Registrar of Record
Name Server: NS1.EXAMPLE.COM
"""

PRIVACY_PROXY_WHOIS = """
Domain Name: PROXY-EXAMPLE.COM
Registrant Organization: Whois Privacy Protection Service, Inc.
Registrant Name: Whois Agent (on behalf of proxy-example.com owner)
"""

NO_REGISTRANT_FIELD_WHOIS = """
Domain Name: SPARSE.EXAMPLE
Registrar: Example Registrar LLC
Creation Date: 2020-01-01
Name Server: NS1.SPARSE.EXAMPLE
"""

CCTLD_STYLE_WHOIS = """
Domain Name: example.co.uk
Registrant:
    Example Ltd
Organisation: Example Ltd
Registered On: 01-Jan-2020
"""


def test_clean_corporate_registrant_is_provided():
    obs = parse_whois_text(CLEAN_CORPORATE_WHOIS, "sony.com")
    assert obs.availability is EvidenceAvailability.PROVIDED
    assert obs.observed_value == "Sony Corporation"
    print("PASS test_clean_corporate_registrant_is_provided")


def test_gdpr_redacted_is_inconclusive_not_missing_or_negative():
    obs = parse_whois_text(GDPR_REDACTED_WHOIS, "example.com")
    assert obs.availability is EvidenceAvailability.INCONCLUSIVE
    assert obs.supports_attribution is None
    print("PASS test_gdpr_redacted_is_inconclusive_not_missing_or_negative")


def test_privacy_proxy_service_is_inconclusive():
    obs = parse_whois_text(PRIVACY_PROXY_WHOIS, "proxy-example.com")
    assert obs.availability is EvidenceAvailability.INCONCLUSIVE
    print("PASS test_privacy_proxy_service_is_inconclusive")


def test_no_registrant_field_is_missing():
    obs = parse_whois_text(NO_REGISTRANT_FIELD_WHOIS, "sparse.example")
    assert obs.availability is EvidenceAvailability.MISSING
    print("PASS test_no_registrant_field_is_missing")


def test_cctld_style_organisation_field_is_recognized():
    obs = parse_whois_text(CCTLD_STYLE_WHOIS, "example.co.uk")
    assert obs.availability is EvidenceAvailability.PROVIDED
    assert obs.observed_value == "Example Ltd"
    print("PASS test_cctld_style_organisation_field_is_recognized")


def test_expected_entity_match_sets_supports_attribution_true():
    obs = parse_whois_text(CLEAN_CORPORATE_WHOIS, "sony.com", expected_entity_name="Sony Corporation")
    assert obs.supports_attribution is True
    print("PASS test_expected_entity_match_sets_supports_attribution_true")


def test_expected_entity_mismatch_sets_supports_attribution_false():
    obs = parse_whois_text(CLEAN_CORPORATE_WHOIS, "sony.com", expected_entity_name="Unrelated Third Party LLC")
    assert obs.supports_attribution is False
    print("PASS test_expected_entity_mismatch_sets_supports_attribution_false")


def test_without_expected_entity_supports_attribution_stays_none():
    obs = parse_whois_text(CLEAN_CORPORATE_WHOIS, "sony.com")
    assert obs.supports_attribution is None
    print("PASS test_without_expected_entity_supports_attribution_stays_none")


if __name__ == "__main__":
    suite = [
        test_clean_corporate_registrant_is_provided,
        test_gdpr_redacted_is_inconclusive_not_missing_or_negative,
        test_privacy_proxy_service_is_inconclusive,
        test_no_registrant_field_is_missing,
        test_cctld_style_organisation_field_is_recognized,
        test_expected_entity_match_sets_supports_attribution_true,
        test_expected_entity_mismatch_sets_supports_attribution_false,
        test_without_expected_entity_supports_attribution_stays_none,
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
