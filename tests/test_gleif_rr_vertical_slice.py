import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'code'))
from providers.gleif_rr_adapter import GleifRelationshipRecordAdapter
from normalization.pipeline import normalize_provider_result
from resolution.resolver import resolve_provider_results
from generate_corporate_seeds import generate

class TestGleifRRVerticalSlice(unittest.TestCase):
    def test_direct_parent_becomes_related_parent_seed(self):
        raw={"RelationshipRecord":{"Relationship":{"StartNode":{"NodeID":{"$":"LEI_CHILD"}},"EndNode":{"NodeID":{"$":"LEI_PARENT"}},"RelationshipType":{"$":"IS_DIRECTLY_CONSOLIDATED_BY"},"RelationshipStatus":{"$":"ACTIVE"}},"Registration":{"LastUpdateDate":{"$":"2026-08-17T00:00:00Z"},"RegistrationStatus":{"$":"PUBLISHED"}}}}
        r=GleifRelationshipRecordAdapter().from_record(raw,{"LEI_CHILD":"Child Inc.","LEI_PARENT":"Parent Inc."},{"LEI_CHILD":"US-DE","LEI_PARENT":"US-DE"}).to_dict()
        graph=resolve_provider_results([normalize_provider_result(r)])
        out=generate(graph)
        self.assertEqual(out['seed_count'],1)
        self.assertEqual(out['seeds'][0]['legal_name'],'Parent Inc.')
        self.assertEqual(out['seeds'][0]['relationship_evidence'][0]['predicate'],'DIRECT_ACCOUNTING_PARENT')
        self.assertEqual(out['seeds'][0]['infrastructure_attribution_confidence'],'unknown')
if __name__=='__main__': unittest.main()
