from __future__ import annotations
from models import Evidence, EntityCandidate, ProviderResult, RelationshipAssertion

TYPE_MAP = {
    "IS_DIRECTLY_CONSOLIDATED_BY": "DIRECT_ACCOUNTING_PARENT",
    "IS_ULTIMATELY_CONSOLIDATED_BY": "ULTIMATE_ACCOUNTING_PARENT",
}

def _v(obj, *path):
    for p in path:
        if not isinstance(obj, dict): return None
        obj = obj.get(p)
    return obj.get("$") if isinstance(obj, dict) and "$" in obj else obj

class GleifRelationshipRecordAdapter:
    name = "gleif"

    def from_record(self, wrapper, names=None, jurisdictions=None):
        names = names or {}; jurisdictions = jurisdictions or {}
        rr = wrapper.get("RelationshipRecord", wrapper)
        rel = rr.get("Relationship") or {}; reg = rr.get("Registration") or {}
        start = _v(rel, "StartNode", "NodeID"); end = _v(rel, "EndNode", "NodeID")
        raw_type = _v(rel, "RelationshipType"); pred = TYPE_MAP.get(raw_type)
        if not start or not end or not pred:
            raise ValueError(f"Unsupported/incomplete GLEIF RR record: {raw_type!r}")
        sname = names.get(start) or start; ename = names.get(end) or end
        sj = jurisdictions.get(start); ej = jurisdictions.get(end)
        status = (_v(rel, "RelationshipStatus") or "UNKNOWN").lower()
        result = ProviderResult(
            provider=self.name, query=sname, resolved_name=sname,
            provider_entity_id=f"lei:{start}",
            metadata={"resolved_lei": start, "root_jurisdiction": sj,
                      "source_shape": "gleif_rr_golden_copy_v1"})
        result.entities.append(EntityCandidate(
            provider=self.name, provider_entity_id=f"lei:{end}", legal_name=ename,
            jurisdiction=ej, attributes={"relationship_label":"parent", "lei":end}))
        evidence = Evidence(
            provider=self.name, evidence_type="structured_corporate_relationship",
            source_document_id=f"gleif-rr:{start}:{raw_type}:{end}",
            source_date=_v(reg, "LastUpdateDate"),
            extraction_method="gleif_rr_golden_copy",
            coverage="lei_relationship_records", raw_record=wrapper,
            attributes={
                "gleif_relationship_type": raw_type,
                "start_lei": start, "end_lei": end,
                "registration_status": _v(reg, "RegistrationStatus"),
                "validation_sources": _v(reg, "ValidationSources"),
                "validation_documents": _v(reg, "ValidationDocuments"),
                "validation_reference": _v(reg, "ValidationReference"),
                "managing_lou": _v(reg, "ManagingLOU"),
                "initial_registration_date": _v(reg, "InitialRegistrationDate"),
                "last_update_date": _v(reg, "LastUpdateDate"),
            })
        result.relationships.append(RelationshipAssertion(
            provider=self.name, subject_name=sname, predicate=pred, object_name=ename,
            jurisdiction=ej, relationship_status=status, evidence=[evidence],
            attributes={"child_lei":start, "parent_lei":end,
                        "child_jurisdiction":sj, "parent_jurisdiction":ej,
                        "corporate_relationship_confidence":"high",
                        "infrastructure_attribution_confidence":"unknown",
                        "gleif_relationship_type":raw_type}))
        if start not in names or end not in names:
            result.warnings.append("One or more LEIs lack Level 1 name enrichment; LEI used as canonical display name.")
        return result
