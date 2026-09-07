from __future__ import annotations
import json, re
from pathlib import Path
from typing import Any
from models import Evidence, EntityCandidate, ProviderResult, RelationshipAssertion

STATUS_PATTERNS = {
    "dormant": re.compile(r"\(\s*dormant\s*\)\s*$", re.I),
    "non_operational": re.compile(r"\(\s*non[- ]operational\s*\)\s*$", re.I),
}
FKA_RE = re.compile(r"\(\s*fka\s+(.+?)\s*\)\s*$", re.I)

def _nonempty(row):
    return [str(x).strip() for x in row if str(x).strip()]

def _clean_name(raw_name):
    name = raw_name.strip()
    former_names = []
    status = None
    fka = FKA_RE.search(name)
    if fka:
        former_names.append(fka.group(1).strip().rstrip("."))
        name = name[:fka.start()].strip()
    for status_name, pattern in STATUS_PATTERNS.items():
        if pattern.search(name):
            status = status_name
            name = pattern.sub("", name).strip()
            break
    return name, former_names, status

def _parse_percent(value):
    if not value: return None
    m = re.search(r"(\d{1,3}(?:\.\d+)?)", value.replace(",", ""))
    return float(m.group(1)) if m else None

def _infer_as_of(header_cells):
    text = " ".join(header_cells)
    m = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s*(\d{4})", text, re.I)
    if not m: return None
    months={"january":1,"february":2,"march":3,"april":4,"may":5,"june":6,"july":7,"august":8,"september":9,"october":10,"november":11,"december":12}
    return f"{int(m.group(3)):04d}-{months[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"

class EdgarJsonAdapter:
    name = "sec_edgar"

    def from_file(self, path, query=None):
        path = Path(path)
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        return self.from_dict(raw, query or raw.get("company",""))

    def from_dict(self, raw, query):
        company = raw.get("company") or query
        cik = str(raw.get("cik","")) or None
        result = ProviderResult(provider=self.name, query=query, resolved_name=company,
                                provider_entity_id=f"cik:{cik}" if cik else None,
                                metadata={"cik":cik})
        for filing in raw.get("filings",[]):
            form_type = filing.get("form_type") or ("10-K" if filing.get("exhibit_url") else "unknown")
            method = filing.get("extraction_method") or ("exhibit_21" if filing.get("exhibit_url") else "unknown")
            source_url = filing.get("document_url") or filing.get("exhibit_url")
            rows = filing.get("extracted_rows") or []
            if not rows:
                result.warnings.append(f"{filing.get('accession','unknown filing')} produced no extracted rows")
                continue
            if form_type.startswith("20-F"):
                self._consume_20f(result, company, rows, source_url, filing, method)
            else:
                self._consume_ex21(result, company, rows, source_url, filing, method, form_type)
        return result

    def _consume_20f(self, result, parent, rows, source_url, filing, method):
        header = _nonempty(rows[0])
        as_of = _infer_as_of(header)
        for raw_row in rows[1:]:
            cells = _nonempty(raw_row)
            if len(cells) < 2: continue
            name = cells[0]
            jurisdiction = cells[1] if len(cells)>=2 else None
            ownership = cells[2] if len(cells)>=3 else None
            clean_name, former_names, status = _clean_name(name)
            ev = Evidence(provider=self.name, evidence_type="corporate_relationship",
                          source_url=source_url, source_document_id=filing.get("accession"),
                          source_date=filing.get("filing_date"), as_of_date=as_of,
                          extraction_method=method, coverage="significant_subsidiaries",
                          raw_record=raw_row, attributes={"form_type":"20-F","source_header":header})
            result.entities.append(EntityCandidate(provider=self.name, provider_entity_id=None,
                                                   legal_name=clean_name, jurisdiction=jurisdiction,
                                                   status=status, former_names=former_names,
                                                   attributes={"ownership_percent":_parse_percent(ownership)}))
            result.relationships.append(RelationshipAssertion(provider=self.name,
                                                              subject_name=parent,
                                                              predicate="HAS_SUBSIDIARY",
                                                              object_name=clean_name,
                                                              jurisdiction=jurisdiction,
                                                              ownership_percent=_parse_percent(ownership),
                                                              relationship_status=status,
                                                              former_names=former_names,
                                                              evidence=[ev],
                                                              attributes={"coverage":"significant_subsidiaries"}))

    def _consume_ex21(self, result, parent, rows, source_url, filing, method, form_type):
        raw_header = [str(x).strip() for x in rows[0]]
        header_l = [x.casefold() for x in raw_header]
        def find(needles):
            for i,h in enumerate(header_l):
                if any(n in h for n in needles): return i
            return None
        name_idx = find(("company name","legal name","subsidiary"))
        country_idx = find(("country","state/country of organization","state of incorporation","state of incorporation or formation"))
        rel_idx = find(("relationship",))
        address_idx = find(("address",))
        if name_idx is None: name_idx = 0

        for raw_row in rows[1:]:
            cells=[str(x).strip() for x in raw_row]
            if name_idx >= len(cells): continue
            raw_name=cells[name_idx]
            if not raw_name: continue
            if raw_name.casefold() in {"subsidiary","company name","legal name","name of company"}: continue
            clean_name, former_names, status = _clean_name(raw_name)
            get=lambda idx: cells[idx] if idx is not None and idx < len(cells) and cells[idx] else None
            jurisdiction=get(country_idx); relationship_label=get(rel_idx); address=get(address_idx)
            predicate="SELF_OR_ULTIMATE_PARENT" if relationship_label and "ultimate parent" in relationship_label.casefold() else "HAS_SUBSIDIARY"
            ev=Evidence(provider=self.name,evidence_type="corporate_relationship",
                        source_url=source_url,source_document_id=filing.get("accession"),
                        source_date=filing.get("filing_date"),extraction_method=method,
                        coverage="exhibit_21_disclosed_entities",raw_record=raw_row,
                        attributes={"form_type":form_type,"relationship_label":relationship_label,"source_header":raw_header})
            result.entities.append(EntityCandidate(provider=self.name,provider_entity_id=None,
                                                   legal_name=clean_name,jurisdiction=jurisdiction,
                                                   status=status,former_names=former_names,
                                                   addresses=[address] if address else [],
                                                   attributes={"relationship_label":relationship_label}))
            result.relationships.append(RelationshipAssertion(provider=self.name,
                                                              subject_name=parent,predicate=predicate,
                                                              object_name=clean_name,jurisdiction=jurisdiction,
                                                              relationship_status=status,former_names=former_names,
                                                              evidence=[ev],attributes={"relationship_label":relationship_label,"address":address}))
