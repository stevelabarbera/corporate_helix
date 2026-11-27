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
            "NO_SEC_PAIR_EVENT_FOUND_NOT_NEGATIVE_PROOF",
        )

    def test_unrelated_event_does_not_count(self):
        result=investigate_l2_leads(
            seed=seed(), facts=[edge("Monsanto Company","LEI-MONSANTO")],
            edgar_provider=lambda p,n: [sec_fact("Unrelated Corporation")],
            max_probes=1,
        )
        self.assertEqual(
            result["leads"][0]["decision"],
            "NO_SEC_PAIR_EVENT_FOUND_NOT_NEGATIVE_PROOF",
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
