from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from ..models import Address, EntityCandidate, LegalEntityEvent, RelationshipEvidence


def _scalar(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        if "$" in value:
            text = str(value["$"]).strip()
            return text or None
        return None
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        return text or None
    return None


def _items(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _find_records(node: Any, required_key: str) -> Iterable[dict[str, Any]]:
    if isinstance(node, dict):
        if required_key in node:
            yield node
        for value in node.values():
            yield from _find_records(value, required_key)
    elif isinstance(node, list):
        for item in node:
            yield from _find_records(item, required_key)


def _address(node: Any, address_type: str | None = None) -> Address | None:
    if not isinstance(node, dict):
        return None
    lines: list[str] = []
    first = _scalar(node.get("FirstAddressLine"))
    if first:
        lines.append(first)
    for extra in _items(node.get("AdditionalAddressLine")):
        val = _scalar(extra)
        if val:
            lines.append(val)
    addr = Address(
        lines=lines,
        city=_scalar(node.get("City")),
        region=_scalar(node.get("Region")),
        country=_scalar(node.get("Country")),
        postal_code=_scalar(node.get("PostalCode")),
        mail_routing=_scalar(node.get("MailRouting")),
        address_type=address_type or node.get("@type"),
    )
    return addr if addr.compact() else None


def _name_values(entity: dict[str, Any]) -> list[str]:
    names: list[str] = []
    blocks = [
        ("OtherEntityNames", "OtherEntityName"),
        ("TransliteratedOtherEntityNames", "TransliteratedOtherEntityName"),
    ]
    for block_name, item_name in blocks:
        block = entity.get(block_name)
        if not isinstance(block, dict):
            continue
        for item in _items(block.get(item_name)):
            val = _scalar(item)
            if val and val not in names:
                names.append(val)
    return names


def _other_addresses(entity: dict[str, Any]) -> list[Address]:
    out: list[Address] = []
    blocks = [
        ("OtherAddresses", "OtherAddress"),
        ("TransliteratedOtherAddresses", "TransliteratedOtherAddress"),
    ]
    for block_name, item_name in blocks:
        block = entity.get(block_name)
        if not isinstance(block, dict):
            continue
        for item in _items(block.get(item_name)):
            addr = _address(item)
            if addr:
                out.append(addr)
    return out


def _events(entity: dict[str, Any]) -> list[LegalEntityEvent]:
    block = entity.get("LegalEntityEvents")
    if not isinstance(block, dict):
        return []
    out: list[LegalEntityEvent] = []
    for raw in _items(block.get("LegalEntityEvent")):
        if not isinstance(raw, dict):
            continue
        event_type = _scalar(raw.get("LegalEntityEventType"))
        if not event_type:
            continue
        affected: list[dict[str, str | None]] = []
        fields = raw.get("AffectedFields") or {}
        if isinstance(fields, dict):
            for item in _items(fields.get("AffectedField")):
                if isinstance(item, dict):
                    affected.append({"field_xpath": item.get("@field_xpath"), "value": _scalar(item)})
        out.append(LegalEntityEvent(
            event_type=event_type,
            event_status=raw.get("@event_status"),
            group_type=raw.get("@group_type"),
            effective_date=_scalar(raw.get("LegalEntityEventEffectiveDate")),
            recorded_date=_scalar(raw.get("LegalEntityEventRecordedDate")),
            validation_documents=_scalar(raw.get("ValidationDocuments")),
            validation_reference=_scalar(raw.get("ValidationReference")),
            affected_fields=affected,
        ))
    return out


def _successors(entity: dict[str, Any]) -> tuple[list[str], list[str]]:
    ids: list[str] = []
    names: list[str] = []
    for raw in _items(entity.get("SuccessorEntity")):
        if not isinstance(raw, dict):
            continue
        sid = _scalar(raw.get("SuccessorLEI"))
        sname = _scalar(raw.get("SuccessorEntityName"))
        if sid and sid not in ids:
            ids.append(sid)
        if sname and sname not in names:
            names.append(sname)
    return ids, names


def _conformity(extension: Any) -> str | None:
    if not isinstance(extension, dict):
        return None
    block = extension.get("gleif:conformity")
    if not isinstance(block, dict):
        return None
    return _scalar(block.get("gleif:conformityflag"))


def parse_lei_record(record: dict[str, Any]) -> EntityCandidate | None:
    lei = _scalar(record.get("LEI"))
    entity = record.get("Entity")
    if not lei or not isinstance(entity, dict):
        return None

    reg_auth = entity.get("RegistrationAuthority") or {}
    legal_form = entity.get("LegalForm") or {}
    registration = record.get("Registration") or {}
    successor_ids, successor_names = _successors(entity)

    return EntityCandidate(
        provider="gleif",
        provider_id=lei,
        legal_name=_scalar(entity.get("LegalName")) or "",
        other_names=_name_values(entity),
        legal_address=_address(entity.get("LegalAddress"), "LEGAL_ADDRESS"),
        headquarters_address=_address(entity.get("HeadquartersAddress"), "HEADQUARTERS_ADDRESS"),
        other_addresses=_other_addresses(entity),
        jurisdiction=_scalar(entity.get("LegalJurisdiction")),
        registration_authority=_scalar(reg_auth.get("RegistrationAuthorityID")),
        registration_id=_scalar(reg_auth.get("RegistrationAuthorityEntityID")),
        category=_scalar(entity.get("EntityCategory")),
        subcategory=_scalar(entity.get("EntitySubCategory")),
        legal_form=_scalar(legal_form.get("EntityLegalFormCode")) or _scalar(legal_form.get("OtherLegalForm")),
        entity_status=_scalar(entity.get("EntityStatus")),
        entity_creation_date=_scalar(entity.get("EntityCreationDate")),
        registration_status=_scalar(registration.get("RegistrationStatus")),
        validation_status=_scalar(registration.get("ValidationSources")),
        initial_registration_date=_scalar(registration.get("InitialRegistrationDate")),
        last_update_date=_scalar(registration.get("LastUpdateDate")),
        next_renewal_date=_scalar(registration.get("NextRenewalDate")),
        successor_ids=successor_ids,
        successor_names=successor_names,
        events=_events(entity),
        conformity=_conformity(record.get("Extension")),
        raw=record,
    )


def parse_relationship_record(record: dict[str, Any]) -> RelationshipEvidence | None:
    rel = record.get("Relationship")
    if not isinstance(rel, dict):
        return None
    start = rel.get("StartNode") or {}
    end = rel.get("EndNode") or {}
    child = _scalar(start.get("NodeID"))
    parent = _scalar(end.get("NodeID"))
    rel_type = _scalar(rel.get("RelationshipType"))
    if not child or not rel_type:
        return None

    periods = rel.get("RelationshipPeriods") or {}
    first_period = next(iter(_items(periods.get("RelationshipPeriod"))), {})
    return RelationshipEvidence(
        provider="gleif",
        child_id=child,
        parent_id=parent,
        relationship_type=rel_type,
        relationship_status=_scalar(rel.get("RelationshipStatus")),
        start_date=_scalar(first_period.get("StartDate")) if isinstance(first_period, dict) else None,
        end_date=_scalar(first_period.get("EndDate")) if isinstance(first_period, dict) else None,
    )


def load_lei_file(path: str | Path) -> list[EntityCandidate]:
    # Fine for the daily delta and fixtures. The 12 GB Golden Copy needs a
    # streaming/indexing path; intentionally do not pretend json.loads scales there.
    data = json.loads(Path(path).read_text())
    out: list[EntityCandidate] = []
    seen: set[str] = set()
    for record in _find_records(data, "Entity"):
        entity = parse_lei_record(record)
        if entity and entity.provider_id not in seen:
            seen.add(entity.provider_id)
            out.append(entity)
    return out


def load_relationship_file(path: str | Path) -> list[RelationshipEvidence]:
    data = json.loads(Path(path).read_text())
    out: list[RelationshipEvidence] = []
    for record in _find_records(data, "Relationship"):
        rel = parse_relationship_record(record)
        if rel:
            out.append(rel)
    return out
