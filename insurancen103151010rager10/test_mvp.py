import json
import tempfile
import unittest
from pathlib import Path

from src.corphelix.providers.gleif import load_lei_file
from src.corphelix.providers.edgar import load_edgar_exhibit
from src.corphelix.providers.rdap import parse_domain_rdap
from src.corphelix.resolution.matcher import rank_candidates
from src.corphelix.resolution.normalize import normalize_name


class MVPTests(unittest.TestCase):
    def test_normalize_legal_forms(self):
        self.assertEqual(normalize_name("SentinelOne GmbH"), "sentinelone")
        self.assertEqual(normalize_name("SentinelOne CyberSecurity Spain, S.L."), "sentinelone cybersecurity spain")
        self.assertEqual(normalize_name("Google Ireland Holdings Unlimited Company"), "google ireland holdings unlimited company")

    def test_gleif_parser_and_domain_match(self):
        gleif = {
            "LEIRecords": {"LEIRecord": [
                {
                    "LEI": {"$": "TESTGOOGLEBELGIUM0001"},
                    "Entity": {
                        "LegalName": {"$": "GOOGLE BELGIUM"},
                        "LegalAddress": {"FirstAddressLine": {"$": "Chaussée d'Etterbeek 180"}, "City": {"$": "Brussel"}, "Country": {"$": "BE"}, "PostalCode": {"$": "1040"}},
                        "HeadquartersAddress": {"FirstAddressLine": {"$": "Chaussée d'Etterbeek 180"}, "City": {"$": "Brussel"}, "Country": {"$": "BE"}, "PostalCode": {"$": "1040"}},
                        "LegalJurisdiction": {"$": "BE"}, "EntityCategory": {"$": "GENERAL"}, "EntityStatus": {"$": "ACTIVE"}
                    },
                    "Registration": {"ValidationSources": {"$": "FULLY_CORROBORATED"}}
                },
                {
                    "LEI": {"$": "TESTDEEPMINDFUND00002"},
                    "Entity": {
                        "LegalName": {"$": "Google DeepMind AI Lab ETF"},
                        "LegalAddress": {"FirstAddressLine": {"$": "1209 Orange Street"}, "City": {"$": "Wilmington"}, "Region": {"$": "US-DE"}, "Country": {"$": "US"}, "PostalCode": {"$": "19801"}},
                        "HeadquartersAddress": {"FirstAddressLine": {"$": "111 SOUTH WACKER DRIVE"}, "City": {"$": "CHICAGO"}, "Region": {"$": "US-IL"}, "Country": {"$": "US"}, "PostalCode": {"$": "60606"}},
                        "LegalJurisdiction": {"$": "US"}, "EntityCategory": {"$": "FUND"}, "EntityStatus": {"$": "ACTIVE"}
                    }
                }
            ]}
        }
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "gleif.json"
            p.write_text(json.dumps(gleif))
            entities = load_lei_file(p)
        self.assertEqual(len(entities), 2)

        rdap = parse_domain_rdap({
            "ldhName": "example.be",
            "entities": [{
                "roles": ["registrant"],
                "vcardArray": ["vcard", [
                    ["version", {}, "text", "4.0"],
                    ["org", {}, "text", "Google Belgium"],
                    ["adr", {}, "text", ["", "", "Chaussée d'Etterbeek 180", "Brussel", "", "1040", "BE"]]
                ]]
            }]
        })
        ranked = rank_candidates(rdap, entities)
        self.assertEqual(ranked[0].entity.legal_name, "GOOGLE BELGIUM")
        self.assertEqual(ranked[0].decision, "strong_candidate")
        self.assertEqual(ranked[1].decision, "reject")

    def test_existing_edgar_output(self):
        path = Path("data/raw/edgar_sentinelone.json")
        entities, relationships = load_edgar_exhibit(path)
        # Filing has 29 entity rows after the parent/header; duplicate Spain is deduped.
        self.assertGreaterEqual(len(entities), 28)
        self.assertEqual(len(relationships), 28)
        scalyr = next(e for e in entities if e.legal_name == "Scalyr, LLC")
        self.assertIn("Scalyr, Inc.", scalyr.other_names)
        india = next(e for e in entities if e.legal_name == "SentinelOne India Private Limited")
        self.assertEqual(india.entity_status, "dormant")

    def test_gleif_real_shape_preserves_events_and_transliterations(self):
        gleif = {
            "records": [{
                "LEI": {"$": "TESTEVENT000000000001"},
                "Entity": {
                    "LegalName": {"$": "Example GmbH"},
                    "TransliteratedOtherEntityNames": {"TransliteratedOtherEntityName": [{"@type": "AUTO_ASCII_TRANSLITERATED_LEGAL_NAME", "$": "Example GMBH"}]},
                    "LegalAddress": {"FirstAddressLine": {"$": "Straße 1"}, "City": {"$": "Berlin"}, "Country": {"$": "DE"}},
                    "HeadquartersAddress": {"FirstAddressLine": {"$": "Straße 1"}, "City": {"$": "Berlin"}, "Country": {"$": "DE"}},
                    "LegalJurisdiction": {"$": "DE"},
                    "EntityCategory": {"$": "GENERAL"},
                    "EntityStatus": {"$": "INACTIVE"},
                    "SuccessorEntity": [{"SuccessorLEI": {"$": "SUCCESSOR000000000001"}}],
                    "LegalEntityEvents": {"LegalEntityEvent": [{
                        "@group_type": "STANDALONE", "@event_status": "COMPLETED",
                        "LegalEntityEventType": {"$": "MERGERS_AND_ACQUISITIONS"},
                        "LegalEntityEventEffectiveDate": {"$": "2026-06-30T00:00:00Z"}
                    }]}
                },
                "Registration": {"RegistrationStatus": {"$": "RETIRED"}, "ValidationSources": {"$": "FULLY_CORROBORATED"}}
            }]
        }
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "gleif.json"
            p.write_text(json.dumps(gleif))
            entities = load_lei_file(p)
        self.assertEqual(len(entities), 1)
        e = entities[0]
        self.assertIn("Example GMBH", e.other_names)
        self.assertEqual(e.successor_ids, ["SUCCESSOR000000000001"])
        self.assertEqual(e.events[0].event_type, "MERGERS_AND_ACQUISITIONS")
        self.assertEqual(e.registration_status, "RETIRED")


if __name__ == "__main__":
    unittest.main()
