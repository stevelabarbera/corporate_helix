#!/usr/bin/env python3
"""GLEIF L2 accounting relationship evidence for the M&A expansion engine.

A unique exact canonical L1 identity is an identity anchor even when the
*corporate root* proposal is REVIEW_REQUIRED.  A GLEIF accounting parent is
not an acquisition; every emitted edge is REVIEW and never pivot-eligible.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable

from iterative_expansion import HelixFact
from expansion_bridges import LEGAL_ENTITY_FACT_TYPE, ROOT_FACT_TYPE
from root_entity_resolver import (
    _relationship_applies_now, _parse_relationship_date, normalize_name,
    resolve_company_root,
)

L2_TYPES = {"IS_DIRECTLY_CONSOLIDATED_BY", "IS_ULTIMATELY_CONSOLIDATED_BY"}
EDGE_FACT_TYPE = "CORPORATE_RELATIONSHIP"


def unique_exact_lei(result: Any, name: str) -> str | None:
    """Anchor the *queried entity*, not its graph-selected ultimate parent."""
    matches = {
        str(s["lei"]) for s in (getattr(result, "seed_matches", None) or [])
        if s.get("lei") and not s.get("match_source")
        and normalize_name(s.get("legal_name") or "") == normalize_name(name)
    }
    return next(iter(matches)) if len(matches) == 1 else None


def typed_pivot_lei(pivot: HelixFact) -> str | None:
    """Never interpret SEC CIK (or arbitrary identifier) as an LEI."""
    declared = pivot.metadata.get("identifiers") or {}
    if declared.get("lei"):
        return str(declared["lei"])
    identifier = (pivot.identifier or "").strip()
    # GLEIF LEIs are 20-character alphanumeric identifiers, not 10-digit CIKs.
    if len(identifier) == 20 and identifier.isascii() and identifier.isalnum():
        return identifier.upper()
    return None


def edge_fact(row: dict[str, Any], *, pivot: HelixFact, as_of: date,
              names: dict[str, str | None]) -> HelixFact:
    child, parent = row["child_lei"], row["parent_lei"]
    relation = row["relationship_type"]
    applicable = _relationship_applies_now(row, as_of)
    try:
        start = _parse_relationship_date(row.get("relationship_start"))
        end = _parse_relationship_date(row.get("relationship_end"))
        period_valid = not (start and end and start > end)
    except ValueError:
        period_valid = False
    evidence = {
        "type": "GLEIF_L2_ACCOUNTING_RELATIONSHIP",
        "source": row.get("source_file") or "GLEIF_L2",
        "record_id": row.get("id"),
        "child_lei": child,
        "parent_lei": parent,
        "relationship_type": relation,
        "relationship_status": row.get("relationship_status"),
        "relationship_start": row.get("relationship_start"),
        "relationship_end": row.get("relationship_end"),
        "accounting_start": row.get("accounting_start"),
        "accounting_end": row.get("accounting_end"),
        "document_filing_start": row.get("document_filing_start"),
        "document_filing_end": row.get("document_filing_end"),
        "registration_status": row.get("registration_status"),
        "initial_registration_date": row.get("initial_registration_date"),
        "last_update_date": row.get("last_update_date"),
        "validation_sources": row.get("validation_sources"),
        "validation_documents": row.get("validation_documents"),
        "validation_reference": row.get("validation_reference"),
        "as_of_date": as_of.isoformat(),
        "eligible_by_current_snapshot_as_of": applicable,
        "historical_status_proven": False,
        "period_valid": period_valid,
    }
    return HelixFact(
        fact_type=EDGE_FACT_TYPE,
        # Identifier-free unique edge key; do not merge direct and ultimate.
        value=f"{child}|{relation}|{parent}",
        subject=pivot.value,
        identifier=None,
        source="GLEIF_L2",
        confidence="MEDIUM" if applicable else "LOW",
        status="REVIEW",
        pivot_eligible=False,
        evidence=[evidence],
        metadata={
            "child": {"lei": child, "legal_name": names.get(child)},
            "parent": {"lei": parent, "legal_name": names.get(parent)},
            "relationship_type": relation,
            "identity_anchor_lei": typed_pivot_lei(pivot),
            "discovered_from": pivot.value,
            "review_reason": "ACCOUNTING_RELATIONSHIP_NOT_MA_EVENT",
            "infrastructure_attribution_confidence": "UNKNOWN",
        },
    )


class GleifRelationshipEvidenceProvider:
    """Read-only L1/L2 edge producer; safe to call on non-pivot SEC leads.

    The provider queries both parent and child directions and limits fanout.
    It does not infer acquisition, historical control, or ASM authorization.
    """

    def __init__(self,
                 lei_index: str = "data/processed/gleif_lei.sqlite",
                 rr_index: str = "data/processed/gleif_rr.sqlite",
                 *, as_of_date: str | date | None = None,
                 max_edges: int = 150,
                 resolve_fn: Callable[..., Any] = resolve_company_root,
                 accepted_pivot_types: Iterable[str] = (
                     ROOT_FACT_TYPE, LEGAL_ENTITY_FACT_TYPE,
                 )):
        self.lei_index = lei_index
        self.rr_index = rr_index
        self.as_of = (
            as_of_date if isinstance(as_of_date, date)
            else date.fromisoformat(as_of_date) if as_of_date else date.today()
        )
        self.max_edges = max(1, int(max_edges))
        self.resolve_fn = resolve_fn
        self.accepted_pivot_types = {t.upper() for t in accepted_pivot_types}
        self._identity_cache: dict[str, str | None] = {}
        self.coverage: list[dict[str, Any]] = []

    def _resolve_exact_lei(self, pivot: HelixFact) -> str | None:
        explicit = typed_pivot_lei(pivot)
        if explicit:
            return explicit
        key = normalize_name(pivot.value)
        if key not in self._identity_cache:
            result = self.resolve_fn(
                pivot.value, self.lei_index, self.rr_index,
                as_of_date=self.as_of,
            )
            self._identity_cache[key] = unique_exact_lei(result, pivot.value)
        return self._identity_cache[key]

    def __call__(self, pivot: HelixFact, iteration: int) -> list[HelixFact]:
        if pivot.fact_type.strip().upper() not in self.accepted_pivot_types:
            return []
        lei = self._resolve_exact_lei(pivot)
        if not lei:
            self.coverage.append({"query": pivot.value, "status": "NO_UNIQUE_EXACT_LEI"})
            return []
        db = Path(self.rr_index).resolve()
        if not db.is_file():
            raise FileNotFoundError(f"GLEIF relationship index not found: {db}")
        conn = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """SELECT * FROM relationships
                   WHERE (child_lei=? OR parent_lei=?)
                   AND relationship_type IN (?,?)
                   ORDER BY child_lei, parent_lei, relationship_type
                   LIMIT ?""",
                (lei, lei, *sorted(L2_TYPES), self.max_edges + 1),
            ).fetchall()
            truncated = len(rows) > self.max_edges
            rows = rows[:self.max_edges]
            other = {v for r in rows for v in (r["child_lei"], r["parent_lei"])}
            names: dict[str, str | None] = {}
            l1 = Path(self.lei_index).resolve()
            if not l1.is_file():
                raise FileNotFoundError(f"GLEIF L1 index not found: {l1}")
            lc = sqlite3.connect(f"{l1.as_uri()}?mode=ro", uri=True)
            lc.row_factory = sqlite3.Row
            try:
                for other_lei in sorted(other):
                    item = lc.execute(
                        "SELECT legal_name FROM lei_entities WHERE lei=?",
                        (other_lei,),
                    ).fetchone()
                    names[other_lei] = item["legal_name"] if item else None
            finally:
                lc.close()
        finally:
            conn.close()
        self.coverage.append({
            "query": pivot.value, "anchor_lei": lei,
            "status": "TRUNCATED" if truncated else "CHECKED",
            "returned_edges": len(rows),
            "max_edges": self.max_edges,
        })
        return [edge_fact(dict(row), pivot=pivot, as_of=self.as_of, names=names)
                for row in rows]
