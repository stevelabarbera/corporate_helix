from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..models import Address, EntityCandidate, RelationshipEvidence


def _clean_name(name: str) -> tuple[str, list[str], str | None]:
    former: list[str] = []
    status = None
    m = re.search(r"\(fka\s+([^)]*)\)", name, flags=re.I)
    if m:
        former.append(m.group(1).strip())
        name = name[:m.start()] + name[m.end():]
    m = re.search(r"\((Dormant|Non[- ]operational)\)", name, flags=re.I)
    if m:
        status = m.group(1).lower().replace(" ", "-")
        name = name[:m.start()] + name[m.end():]
    return name.strip().rstrip("."), former, status


def load_edgar_exhibit(path: str | Path) -> tuple[list[EntityCandidate], list[RelationshipEvidence]]:
    data = json.loads(Path(path).read_text())
    company = data.get("company") or "Unknown parent"
    parent_id = f"edgar:cik:{data.get('cik', 'unknown')}"
    entities: list[EntityCandidate] = []
    relationships: list[RelationshipEvidence] = []
    entity_ids: dict[tuple[str, str | None], str] = {}
    relationship_seen: set[tuple[str, str]] = set()

    for filing in data.get("filings", []) or []:
        accession = filing.get("accession")
        source_ref = filing.get("exhibit_url") or accession
        rows = filing.get("extracted_rows", []) or []
        for idx, row in enumerate(rows):
            if idx == 0 or not isinstance(row, list) or len(row) < 2:
                continue
            raw_name = str(row[0]).strip()
            country = str(row[1]).strip() or None
            relationship = str(row[2]).strip() if len(row) > 2 else "Entity"
            address_text = str(row[3]).strip() if len(row) > 3 else ""
            name, former_names, embedded_status = _clean_name(raw_name)
            key = (name.casefold(), country)
            provider_id = f"edgar:{accession}:{idx}"

            if key not in entity_ids:
                entity_ids[key] = provider_id
                entities.append(EntityCandidate(
                    provider="edgar",
                    provider_id=provider_id,
                    legal_name=name,
                    other_names=former_names,
                    legal_address=Address(lines=[address_text], country=country) if address_text else None,
                    jurisdiction=country,
                    entity_status=embedded_status,
                    raw={"row": row, "filing_date": filing.get("filing_date"), "source": source_ref},
                ))

            # The parent row itself is identity evidence, not a subsidiary edge.
            if relationship.lower() == "ultimate parent" or name.casefold() == company.rstrip(".").casefold():
                continue
            canonical_child_id = entity_ids[key]
            rel_key = (canonical_child_id, parent_id)
            if rel_key in relationship_seen:
                continue
            relationship_seen.add(rel_key)
            relationships.append(RelationshipEvidence(
                provider="edgar",
                child_id=canonical_child_id,
                parent_id=parent_id,
                relationship_type="SUBSIDIARY_ASSERTION",
                relationship_status="ACTIVE" if embedded_status not in {"dormant", "non-operational"} else embedded_status.upper(),
                source_reference=source_ref,
            ))
    return entities, relationships
