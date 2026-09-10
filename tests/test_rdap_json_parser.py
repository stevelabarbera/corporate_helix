#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from evidence_contract import EvidenceAvailability, EvidenceCapability
from parsers.rdap_json_parser import parse_rdap_json

def entity(role, org=None):
    e = {"roles": [role]}
    if org is not None:
        e["vcardArray"] = ["vcard", [["org", {}, "text", org]]]
    return e

CORPORATE = {"ldhName": "SONY.COM", "entities": [entity("registrant", "Sony Corporation"), entity("registrar", "Example Registrar LLC")]}
REDACTED = {"ldhName": "example.com", "entities": [entity("registrant", "REDACTED FOR PRIVACY")]}
NO_REGISTRANT = {"ldhName": "example.net", "entities": [entity("registrar", "Registrar Corporation")]}
EMPTY_REGISTRANT = {"ldhName": "example.org", "entities": [entity("registrant")]}
MULTIPLE = {"ldhName": "shared.example", "entities": [entity("registrant", "Example Holdings LLC"), entity("registrant", "Example Operating Inc")]}

def test_clean_registrant_is_provided():
    obs = parse_rdap_json(CORPORATE)
    assert obs.capability is EvidenceCapability.RDAP_WHOIS
    assert obs.availability is EvidenceAvailability.PROVIDED
    assert obs.observed_value == "Sony Corporation"
    assert obs.subject == "sony.com"

def test_registrar_is_not_treated_as_owner():
    assert parse_rdap_json(CORPORATE).observed_value != "Example Registrar LLC"

def test_redacted_registrant_is_inconclusive():
    obs = parse_rdap_json(REDACTED)
    assert obs.availability is EvidenceAvailability.INCONCLUSIVE
    assert obs.supports_attribution is None

def test_missing_registrant_is_missing():
    assert parse_rdap_json(NO_REGISTRANT).availability is EvidenceAvailability.MISSING

def test_registrant_without_identity_is_inconclusive():
    assert parse_rdap_json(EMPTY_REGISTRANT).availability is EvidenceAvailability.INCONCLUSIVE

def test_multiple_registrants_are_inconclusive():
    obs = parse_rdap_json(MULTIPLE)
    assert obs.availability is EvidenceAvailability.INCONCLUSIVE
    assert "Example Holdings LLC" in obs.observed_value
    assert "Example Operating Inc" in obs.observed_value

def test_expected_entity_match_sets_true():
    assert parse_rdap_json(CORPORATE, expected_entity_name="Sony Corporation").supports_attribution is True

def test_expected_entity_mismatch_sets_false():
    assert parse_rdap_json(CORPORATE, expected_entity_name="Unrelated Corporation LLC").supports_attribution is False

def test_without_expected_entity_stays_none():
    assert parse_rdap_json(CORPORATE).supports_attribution is None
