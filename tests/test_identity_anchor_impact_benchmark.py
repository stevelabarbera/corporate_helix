#!/usr/bin/env python3
"""Local, synthetic checks for repeatable identity-anchor impact measurement."""
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
import benchmark_identity_anchor_impact as bench
from root_entity_resolver import RootCandidate, RootResolution


def decision(query, status, lei=None):
    root = RootCandidate(lei=lei, legal_name="Fixture Inc", jurisdiction="US",
                         entity_status="ACTIVE") if lei else None
    return RootResolution(
        query=query, status=status, confidence="MEDIUM", root=root,
        candidates=[RootCandidate(lei="C", legal_name="Candidate",
                                  jurisdiction="US", entity_status="ACTIVE")],
        seed_matches=[{"lei": "S"}], reason="synthetic fixture",
    )


class ImpactBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.lei, self.rr, self.alias = (d / x for x in ("lei.db", "rr.db", "alias.db"))
        with sqlite3.connect(self.lei) as db:
            db.executescript("""
                CREATE TABLE lei_entities (
                    lei TEXT PRIMARY KEY, legal_name TEXT,
                    legal_name_normalized TEXT, entity_status TEXT);
                INSERT INTO lei_entities VALUES
                ('A','Alpha Trading Limited','alpha trading limited','ACTIVE'),
                ('B','Beta Holdings Limited','beta holdings limited','ACTIVE'),
                ('C','Old Company LLC','old company llc','INACTIVE');
            """)
        with sqlite3.connect(self.rr) as db:
            db.executescript("""
                CREATE TABLE relationships (
                  child_lei TEXT, parent_lei TEXT, relationship_status TEXT,
                  relationship_type TEXT);
                INSERT INTO relationships VALUES
                  ('A','B','ACTIVE','IS_ULTIMATELY_CONSOLIDATED_BY');
            """)
        with sqlite3.connect(self.alias) as db:
            db.executescript("""
                CREATE TABLE source_observation (
                    observation_id INTEGER PRIMARY KEY, record_identifier TEXT);
                CREATE TABLE entity_name (
                    observation_id INTEGER, name TEXT);
                INSERT INTO source_observation VALUES(1,'B');
                INSERT INTO entity_name VALUES(1,'Previous Beta Holdings');
            """)

    def tearDown(self):
        self.tmp.cleanup()

    def test_generated_cohort_is_reproducible(self):
        first = bench.generate_cohort(str(self.lei), str(self.rr), str(self.alias))
        second = bench.generate_cohort(str(self.lei), str(self.rr), str(self.alias))
        self.assertEqual(first, second)
        self.assertTrue(any(x["stratum"] == "general_exact" for x in first))
        self.assertTrue(any(x["stratum"] == "known_risk" for x in first))
        self.assertTrue(any(x["stratum"] == "relationship_child_exact" for x in first))
        # Alpha appears in both the general and relationship sampling pools.
        # It must be assigned to the relationship stratum; Beta should
        # remain in the general exact-name stratum.
        strata = {x["query"]: x["stratum"] for x in first}
        self.assertEqual(strata["Alpha Trading Limited"], "relationship_child_exact")
        self.assertEqual(strata["Beta Holdings Limited"], "general_exact")
        self.assertEqual(len(first), len({bench.normalize_name(x["query"]) for x in first}))

    def test_auto_to_review_is_counted_not_called_accuracy(self):
        rows = [{"query": "Acme", "stratum": "general_exact"}]
        with patch.object(bench, "resolve_company_root",
                          return_value=decision("Acme", "REVIEW_REQUIRED")):
            report = bench.compare_cases(
                rows, lambda company, **kw: decision(company, "AUTO_RESOLVED", "X"),
                str(self.lei), str(self.rr), str(self.alias),
            )
        self.assertEqual(report["counts"]["auto_to_review"], 1)
        self.assertEqual(report["counts"]["suppressed_root"], 1)
        self.assertEqual(report["counts"]["before_auto"], 1)
        self.assertEqual(report["counts"]["after_auto"], 0)
        self.assertEqual(report["cases"][0]["root_correctness"], "NOT_SCORED")

    def test_freeze_rejects_duplicates(self):
        p = Path(self.tmp.name) / "cohort.json"
        p.write_text('[{"query":"Acme","stratum":"general_exact"},'
                     '{"query":"ACME","stratum":"shortened_name"}]')
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            bench.load_cohort(p)

    def test_empty_cohort_rejected(self):
        p = Path(self.tmp.name) / "empty.json"
        p.write_text('{"cases":[]}')
        with self.assertRaisesRegex(ValueError, "non-empty"):
            bench.load_cohort(p)


if __name__ == "__main__":
    unittest.main()
