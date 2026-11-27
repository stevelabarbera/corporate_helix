"""GLEIF->SEC research probing must not imply acquisition or authorize pivots."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from iterative_expansion import HelixFact
from ma_bidirectional import investigate_l2_leads
from providers.gleif_relationship_provider import EDGE_FACT_TYPE


def seed():
    return HelixFact(
        fact_type="COMPANY", value="Bayer Aktiengesellschaft",
        identifier=None, source="SEED", confidence="HIGH",
        status="ACCEPTED", pivot_eligible=True,
    )


def edge(child_name, child_lei, parent_lei="LEI-BAYER",
         rel="IS_ULTIMATELY_CONSOLIDATED_BY",
         reg="PUBLISHED"):
    return HelixFact(
        fact_type=EDGE_FACT_TYPE,
        value=f"{child_lei}|{rel}|{parent_lei}",
        subject="Bayer Aktiengesellschaft",
        source="GLEIF_L2", confidence="MEDIUM", status="REVIEW",
        pivot_eligible=False,
        metadata={
            "child":{"lei":child_lei,"legal_name":child_name},
            "parent":{"lei":parent_lei,"legal_name":"Bayer Aktiengesellschaft"},
            "relationship_type":rel,
            "identity_anchor_lei":parent_lei,
        },
        evidence=[{
            "type":"GLEIF_L2_ACCOUNTING_RELATIONSHIP",
            "period_valid":True, "relationship_status":"ACTIVE",
            "relationship_start":"2019-09-03",
            "registration_status":reg,
        }],
    )


def sec_fact(counterparty, event_type="ACQUIRED", pivot="Monsanto Company"):
    return HelixFact(
        fact_type="LEGAL_ENTITY", value=counterparty,
        source="EDGAR_MA", confidence="MEDIUM", status="REVIEW",
        pivot_eligible=False,
        evidence=[{
            "type":"EDGAR_MA_EVENT",
            "event_type":event_type, "status":"COMPLETED",
            "pivot_name":pivot, "accession":"0001",
            "filing_date":"2018-06-07",
        }],
    )


class ReverseDiscoveryTests(unittest.TestCase):
    def test_pair_event_is_reported_as_review_only(self):
        calls=[]
        def sec(pivot, iteration):
            calls.append(pivot)
            return [sec_fact("Bayer Aktiengesellschaft")]
        result = investigate_l2_leads(
            seed=seed(),
            facts=[edge("Monsanto Company","LEI-MONSANTO")],
            edgar_provider=sec, max_probes=1,
        )
        self.assertEqual(result["leads_found"],1)
        self.assertEqual(result["leads_probed"],1)
        lead=result["leads"][0]
        self.assertEqual(lead["decision"],"SEC_TRANSACTION_CANDIDATE_FOUND_REVIEW")
        self.assertEqual(lead["sec_events"][0]["event_type"],"ACQUIRED")
        self.assertFalse(calls[0].pivot_eligible)
        self.assertEqual(calls[0].metadata["identifiers"]["lei"],"LEI-MONSANTO")
        self.assertFalse(result["policy"]["gleif_l2_is_acquisition"])

    def test_no_sec_event_is_not_negative_proof(self):
        result=investigate_l2_leads(
            seed=seed(), facts=[edge("Monsanto Company","LEI-MONSANTO")],
            edgar_provider=lambda p,n: [], max_probes=1,
        )
        self.assertEqual(
            result["leads"][0]["decision"],
            "NO_SEC_PAIR_EVENT_FOUND_COVERAGE_UNKNOWN",
        )

    def test_unrelated_event_does_not_count(self):
        result=investigate_l2_leads(
            seed=seed(), facts=[edge("Monsanto Company","LEI-MONSANTO")],
            edgar_provider=lambda p,n: [sec_fact("Unrelated Corporation")],
            max_probes=1,
        )
        self.assertEqual(
            result["leads"][0]["decision"],
            "NO_SEC_PAIR_EVENT_FOUND_COVERAGE_UNKNOWN",
        )

    def test_missing_or_wrong_pivot_does_not_count(self):
        result=investigate_l2_leads(
            seed=seed(), facts=[edge("Monsanto Company","LEI-MONSANTO")],
            edgar_provider=lambda p,n: [
                sec_fact("Bayer Aktiengesellschaft", pivot="Other Inc.")],
            max_probes=1,
        )
        self.assertEqual(result["leads"][0]["sec_events"],[])

    def test_limit_and_dedupe_direct_ultimate_relationships(self):
        calls=[]
        def sec(p,n):
            calls.append(p.value)
            return []
        result=investigate_l2_leads(
            seed=seed(), facts=[
                edge("Monsanto Company","LEI-MONSANTO"),
                edge("Monsanto Company","LEI-MONSANTO",
                     rel="IS_DIRECTLY_CONSOLIDATED_BY"),
                edge("Abiomed, Inc.","LEI-ABIOMED"),
            ],
            edgar_provider=sec, max_probes=1,
        )
        self.assertEqual(result["leads_found"],2)
        self.assertEqual(result["leads_probed"],1)
        self.assertEqual(result["leads_deferred"],1)
        self.assertEqual(len(calls),1)
        monsanto=next(x for x in result["leads"]
                     if x["related_name"]=="Monsanto Company")
        self.assertEqual(len(monsanto["relationship_fact_keys"]),2)

    def test_no_cik_is_distinct_from_no_transaction(self):
        def no_cik(p, n):
            p.metadata["sec_probe"] = {
                "status": "NO_SEC_IDENTITY", "cik": None,
                "filings_retrieved": 0, "sections_retrieved": 0,
            }
            return []
        result = investigate_l2_leads(
            seed=seed(), facts=[edge("Monsanto Company", "LEI-MONSANTO")],
            edgar_provider=no_cik, max_probes=1,
        )
        lead = result["leads"][0]
        self.assertEqual(lead["decision"], "NO_SEC_IDENTITY")
        self.assertIsNone(lead["sec_probe"]["cik"])

    def test_cik_found_but_no_filings(self):
        def empty(p, n):
            p.metadata["sec_probe"] = {
                "status": "NO_SEC_FILINGS", "cik": "0000123456",
                "filings_retrieved": 0, "sections_retrieved": 0,
            }
            return []
        result = investigate_l2_leads(
            seed=seed(), facts=[edge("Monsanto Company", "LEI-MONSANTO")],
            edgar_provider=empty, max_probes=1,
        )
        self.assertEqual(result["leads"][0]["decision"],
                         "NO_SEC_FILINGS_RETRIEVED")

    def test_filings_examined_without_pair_event(self):
        def searched(p, n):
            p.metadata["sec_probe"] = {
                "status": "FILINGS_RETRIEVED", "cik": "0000123456",
                "filings_retrieved": 4, "sections_retrieved": 8,
            }
            return []
        result = investigate_l2_leads(
            seed=seed(), facts=[edge("Monsanto Company", "LEI-MONSANTO")],
            edgar_provider=searched, max_probes=1,
        )
        self.assertEqual(result["leads"][0]["decision"],
                         "SEC_FILINGS_EXAMINED_NO_PAIR_EVENT")
        self.assertEqual(result["leads"][0]["sec_probe"]["sections_retrieved"], 8)

    def test_newer_published_relationship_precedes_old_alphabetical(self):
        old = edge("A Old Company", "LEI-OLD")
        old.evidence[0]["relationship_start"] = "2016-01-01"
        new = edge("Z Recent Company", "LEI-NEW")
        new.evidence[0]["relationship_start"] = "2025-01-01"
        calls = []
        def sec(p, n):
            calls.append(p.value)
            return []
        report = investigate_l2_leads(
            seed=seed(), facts=[old, new], edgar_provider=sec,
            max_probes=1,
        )
        self.assertEqual(calls, ["Z Recent Company"])
        self.assertEqual(report["leads"][0]["research_priority"], 1)

    def test_probe_exception_reports_stage_and_does_not_promote(self):
        def failed(p, n):
            p.metadata["sec_probe"] = {
                "status": "CIK_RESOLVED_FETCH_PENDING",
                "cik": "0000123456",
            }
            raise RuntimeError("SEC 503")
        report = investigate_l2_leads(
            seed=seed(), facts=[edge("Monsanto Company", "LEI-MONSANTO")],
            edgar_provider=failed, max_probes=1,
        )
        lead = report["leads"][0]
        self.assertEqual(lead["decision"], "SEC_PROBE_ERROR")
        self.assertEqual(lead["sec_probe"]["cik"], "0000123456")
        self.assertEqual(lead["sec_events"], [])

    def test_parent_filing_exact_child_match_when_child_has_no_cik(self):
        parent_event = sec_fact("Monsanto Company", pivot="Bayer Aktiengesellschaft")
        report = investigate_l2_leads(
            seed=seed(), facts=[edge("Monsanto Company", "LEI-MONSANTO"),
                                parent_event],
            edgar_provider=lambda p,n: [], max_probes=0,
        )
        lead = report["leads"][0]
        self.assertEqual(lead["decision"], "NOT_PROBED")
        self.assertEqual(lead["parent_side_decision"],
                         "SEC_PARENT_TRANSACTION_CANDIDATE_REVIEW")
        self.assertEqual(len(lead["parent_sec_events"]), 1)
        self.assertEqual(lead["parent_sec_events"][0]["accession"], "0001")

    def test_parent_filing_unrelated_child_is_not_linked(self):
        parent_event = sec_fact("Unrelated Corporation",
                                pivot="Bayer Aktiengesellschaft")
        report = investigate_l2_leads(
            seed=seed(), facts=[edge("Monsanto Company", "LEI-MONSANTO"),
                                parent_event],
            edgar_provider=lambda p,n: [], max_probes=0,
        )
        self.assertEqual(report["leads"][0]["parent_sec_events"], [])

    def test_parent_filing_wrong_filing_pivot_is_not_linked(self):
        parent_event = sec_fact("Monsanto Company", pivot="Other Company")
        report = investigate_l2_leads(
            seed=seed(), facts=[edge("Monsanto Company", "LEI-MONSANTO"),
                                parent_event],
            edgar_provider=lambda p,n: [], max_probes=0,
        )
        self.assertEqual(report["leads"][0]["parent_sec_events"], [])

    def test_disabled_never_calls_sec(self):
        def sec(p,n):
            self.fail("SEC must not run when probes disabled")
        result=investigate_l2_leads(
            seed=seed(), facts=[edge("Monsanto Company","LEI-MONSANTO")],
            edgar_provider=sec, max_probes=0,
        )
        self.assertEqual(result["leads_probed"],0)
        self.assertEqual(result["leads"][0]["decision"],"NOT_PROBED")

    def test_nontransaction_event_is_not_discovery(self):
        result=investigate_l2_leads(
            seed=seed(), facts=[edge("Monsanto Company","LEI-MONSANTO")],
            edgar_provider=lambda p,n: [
                sec_fact("Bayer Aktiengesellschaft",event_type="SUBSIDIARY_OF")],
            max_probes=1,
        )
        self.assertEqual(result["leads"][0]["sec_events"],[])


if __name__ == "__main__":
    unittest.main()
