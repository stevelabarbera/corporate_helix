"""Integration tests: SEC candidates and GLEIF L2 share evidence without trust promotion."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from iterative_expansion import HelixFact
from ma_cross_source import run_integrated
from providers.gleif_relationship_provider import (
    EDGE_FACT_TYPE, GleifRelationshipEvidenceProvider, typed_pivot_lei,
)


def fact(name, *, source="SEED", typ="COMPANY", identifier=None,
         confidence="HIGH", status="ACCEPTED", pivot=True, evidence=None):
    return HelixFact(fact_type=typ, value=name, identifier=identifier,
                     source=source, confidence=confidence, status=status,
                     pivot_eligible=pivot, evidence=evidence or [])


class CrossSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.l1 = str(base / "l1.sqlite")
        self.l2 = str(base / "l2.sqlite")
        conn = sqlite3.connect(self.l1)
        conn.execute("CREATE TABLE lei_entities(lei TEXT, legal_name TEXT)")
        conn.executemany("INSERT INTO lei_entities VALUES (?,?)", [
            ("LEI-MONSANTO", "MONSANTO COMPANY"),
            ("LEI-BAYER", "Bayer Aktiengesellschaft"),
            ("LEI-OTHER", "Other Corporation"),
        ])
        conn.commit(); conn.close()
        conn = sqlite3.connect(self.l2)
        conn.execute("""CREATE TABLE relationships(
            id INTEGER, child_lei TEXT, parent_lei TEXT,
            relationship_type TEXT, relationship_status TEXT,
            relationship_start TEXT, relationship_end TEXT,
            accounting_start TEXT, source_file TEXT)""")
        conn.executemany("INSERT INTO relationships VALUES (?,?,?,?,?,?,?,?,?)", [
            (1, "LEI-MONSANTO", "LEI-BAYER", "IS_DIRECTLY_CONSOLIDATED_BY",
             "ACTIVE", "2019-09-03", None, "2025-01-01", "fixture"),
            (2, "LEI-MONSANTO", "LEI-BAYER", "IS_ULTIMATELY_CONSOLIDATED_BY",
             "ACTIVE", "2019-09-03", None, "2025-01-01", "fixture"),
        ])
        conn.commit(); conn.close()
        self.queries = []

        def resolve(name, l1, l2, *, as_of_date):
            self.queries.append(name)
            found = {
                "monsanto company": "LEI-MONSANTO",
                "bayer aktiengesellschaft": "LEI-BAYER",
            }.get(name.casefold())
            if not found:
                return SimpleNamespace(seed_matches=[], status="NO_MATCH")
            # Deliberate REVIEW_REQUIRED root for Monsanto; exact identity is
            # nevertheless anchored and permitted for an evidence-only edge.
            return SimpleNamespace(
                seed_matches=[{"lei":found, "legal_name":name.upper()
                               if found == "LEI-MONSANTO" else name}],
                status="REVIEW_REQUIRED" if found == "LEI-MONSANTO"
                       else "AUTO_RESOLVED",
            )
        self.resolve = resolve

    def tearDown(self):
        self.tmp.cleanup()

    def provider(self, **kwargs):
        return GleifRelationshipEvidenceProvider(
            self.l1, self.l2, as_of_date="2026-11-26",
            resolve_fn=self.resolve, **kwargs,
        )

    def test_sec_and_gleif_edges_join_without_promoting_trust(self):
        def sec(pivot, iteration):
            if pivot.value != "Monsanto Company":
                return []
            return [fact(
                "Bayer Aktiengesellschaft", source="EDGAR_MA",
                typ="LEGAL_ENTITY", status="REVIEW",
                confidence="MEDIUM", pivot=False,
                evidence=[{"type":"EDGAR_MA_EVENT","accession":"0001",
                           "event_type":"ACQUIRED","status":"COMPLETED",
                           "subject":"Bayer Aktiengesellschaft",
                           "object":"Monsanto Company",
                           "filing_date":"2018-06-07"}],
            )]

        result, audit = run_integrated(
            fact("Monsanto Company", identifier="0001110783"),
            sec, self.provider(), max_iterations=3,
        )
        edges = [x for x in result.facts if x.fact_type == EDGE_FACT_TYPE]
        self.assertEqual(len(edges), 2)
        self.assertEqual(audit["relationship_facts"], 2)
        self.assertEqual(len(audit["links"]), 2)
        self.assertTrue(all(x.status == "REVIEW" and not x.can_pivot()
                            for x in edges))
        self.assertTrue(all(x.metadata["child"]["lei"] == "LEI-MONSANTO"
                            for x in edges))
        self.assertTrue(all(x.metadata["parent"]["lei"] == "LEI-BAYER"
                            for x in edges))
        self.assertTrue(all(any(ev.get("type") == "SEC_GLEIF_CANDIDATE_ASSOCIATION"
                                for ev in x.evidence) for x in edges))
        self.assertFalse(audit["policy"]["gleif_infers_acquisition"])
        self.assertEqual(result.iterations_run, 1)

    def test_no_sec_event_still_yields_gleif_relationship_lead(self):
        result, audit = run_integrated(
            fact("Monsanto Company"), lambda p, n: [],
            self.provider(), max_iterations=2,
        )
        self.assertEqual(audit["relationship_facts"], 2)
        self.assertEqual(audit["links"], [])
        self.assertTrue(all(f.status == "REVIEW" for f in result.facts
                            if f.fact_type == EDGE_FACT_TYPE))

    def test_unresolvable_candidate_is_not_reconciled(self):
        def sec(p,n):
            return [fact("Alstom Power and Grid businesses",
                         source="EDGAR_MA", typ="LEGAL_ENTITY",
                         confidence="MEDIUM", status="REVIEW", pivot=False)]
        result, audit = run_integrated(
            fact("Other Corporation"), sec, self.provider(),
            max_iterations=2,
        )
        self.assertEqual(audit["relationship_facts"], 0)
        self.assertEqual(audit["links"], [])
        self.assertIn("NO_UNIQUE_EXACT_LEI",
                      [x["status"] for x in audit["gleif_coverage"]])

    def test_sec_cik_is_not_lei(self):
        self.assertIsNone(typed_pivot_lei(
            fact("Monsanto Company", identifier="0001110783")
        ))
        self.assertIsNone(typed_pivot_lei(
            fact("Monsanto Company", identifier=None)
        ))
        self.assertEqual(typed_pivot_lei(
            fact("Monsanto Company", identifier="NONUZEX43GHIPSVDD938")
        ), "NONUZEX43GHIPSVDD938")

    def test_future_l2_relation_cannot_backdate_acquisition(self):
        p = GleifRelationshipEvidenceProvider(
            self.l1, self.l2, as_of_date="2018-06-07",
            resolve_fn=self.resolve,
        )
        edges = p(fact("Monsanto Company"), 1)
        self.assertEqual(len(edges), 2)
        self.assertTrue(all(not x.evidence[0]["eligible_by_current_snapshot_as_of"]
                            for x in edges))
        self.assertTrue(all(not x.evidence[0]["historical_status_proven"]
                            for x in edges))
        self.assertTrue(all(not x.can_pivot() for x in edges))


if __name__ == "__main__":
    unittest.main()
