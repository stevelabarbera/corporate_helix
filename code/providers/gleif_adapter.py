from __future__ import annotations

import json
from pathlib import Path

from models import Evidence, EntityCandidate, ProviderResult, RelationshipAssertion


class GleifJsonAdapter:
    """Adapt the compact JSON emitted by code/fetch_gleif.py into M1 canonical evidence."""

    name = "gleif"

    def from_file(self, path, query=None):
        path = Path(path)
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        return self.from_dict(raw, query=query)

    def from_dict(self, raw, query=None):
        root = raw.get("entity") or {}
        root_name = root.get("legal_name") or query or raw.get("query_company") or raw.get("resolved_lei")
        root_lei = root.get("lei") or raw.get("resolved_lei")
        result = ProviderResult(
            provider=self.name,
            query=query or raw.get("query_company") or root_name or "",
            resolved_name=root_name,
            provider_entity_id=f"lei:{root_lei}" if root_lei else None,
            metadata={
                "resolved_lei": root_lei,
                "root_jurisdiction": root.get("jurisdiction"),
                "root_status": root.get("status"),
                "root_legal_form": root.get("legal_form"),
                "source_shape": "fetch_gleif_api_summary_v1",
                "other_search_matches": raw.get("other_search_matches"),
            },
        )

        if not root_name:
            result.warnings.append("GLEIF result has no resolved legal name")
            return result

        self._consume_parent(result, root, raw.get("direct_parent"), "DIRECT_ACCOUNTING_PARENT")
        self._consume_parent(result, root, raw.get("ultimate_parent"), "ULTIMATE_ACCOUNTING_PARENT")

        for child in raw.get("direct_children") or []:
            self._consume_child(result, root, child, "DIRECT_ACCOUNTING_PARENT")
        for child in raw.get("ultimate_children") or []:
            self._consume_child(result, root, child, "ULTIMATE_ACCOUNTING_PARENT")

        for label, value in (("direct_parent", raw.get("direct_parent")), ("ultimate_parent", raw.get("ultimate_parent"))):
            if value and value.get("type") == "exception":
                result.warnings.append(
                    f"{label} reporting exception: {value.get('reason') or 'unspecified'} "
                    f"({value.get('category') or 'uncategorized'})"
                )

        return result

    def _entity(self, item, relationship_label=None):
        lei = item.get("lei")
        attrs = {
            "relationship_label": relationship_label,
            "legal_form": item.get("legal_form"),
            "registration_status": item.get("registration_status"),
            "headquarters_country": item.get("headquarters_country"),
        }
        return EntityCandidate(
            provider=self.name,
            provider_entity_id=f"lei:{lei}" if lei else None,
            legal_name=item.get("legal_name") or lei or "UNKNOWN",
            jurisdiction=item.get("jurisdiction"),
            status=item.get("status"),
            attributes={k: v for k, v in attrs.items() if v is not None},
        )

    def _evidence(self, relationship_type, child, parent):
        return Evidence(
            provider=self.name,
            evidence_type="structured_corporate_relationship",
            source_document_id=(child.get("lei") or parent.get("lei")),
            extraction_method="gleif_api_relationship",
            coverage="lei_registered_entities",
            raw_record={"child": child, "parent": parent, "relationship_type": relationship_type},
            attributes={
                "relationship_type": relationship_type,
                "child_lei": child.get("lei"),
                "parent_lei": parent.get("lei"),
            },
        )

    def _relationship(self, result, child, parent, relationship_type):
        child_name = child.get("legal_name") or child.get("lei")
        parent_name = parent.get("legal_name") or parent.get("lei")
        if not child_name or not parent_name:
            result.warnings.append(f"Skipped incomplete {relationship_type} relationship")
            return

        # Ensure related LEIs become graph nodes, but do not duplicate the provider root.
        root_lei = result.metadata.get("resolved_lei")
        seen_ids = {e.provider_entity_id for e in result.entities if e.provider_entity_id}
        for item, label in ((child, "child"), (parent, "parent")):
            lei = item.get("lei")
            provider_id = f"lei:{lei}" if lei else None
            if lei and lei == root_lei:
                continue
            if provider_id and provider_id in seen_ids:
                continue
            result.entities.append(self._entity(item, relationship_label=label))
            if provider_id:
                seen_ids.add(provider_id)
        result.relationships.append(
            RelationshipAssertion(
                provider=self.name,
                subject_name=child_name,
                predicate=relationship_type,
                object_name=parent_name,
                # Current M2 schema has one relationship jurisdiction field and uses it
                # to resolve object identity. Parent jurisdiction is therefore the safest
                # canonical value here; LEIs remain authoritative provider IDs on nodes.
                jurisdiction=parent.get("jurisdiction"),
                relationship_status="current",
                evidence=[self._evidence(relationship_type, child, parent)],
                attributes={
                    "child_lei": child.get("lei"),
                    "parent_lei": parent.get("lei"),
                    "child_jurisdiction": child.get("jurisdiction"),
                    "parent_jurisdiction": parent.get("jurisdiction"),
                    "corporate_relationship_confidence": "high",
                    "infrastructure_attribution_confidence": "unknown",
                },
            )
        )

    def _consume_parent(self, result, root, rel, relationship_type):
        if not rel or rel.get("type") != "parent" or not rel.get("entity"):
            return
        self._relationship(result, root, rel["entity"], relationship_type)

    def _consume_child(self, result, root, child, relationship_type):
        self._relationship(result, child, root, relationship_type)
