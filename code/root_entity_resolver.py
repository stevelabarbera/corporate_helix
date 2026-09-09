#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass, field
import re
import sqlite3
from pathlib import Path
from typing import Any


def connect(path: str) -> sqlite3.Connection:
    if not Path(path).is_file():
        raise FileNotFoundError(f"Database not found: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def normalize_name(value: str) -> str:
    value = value.casefold().strip()
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def name_tokens(value: str) -> list[str]:
    return normalize_name(value).split()


def _contains_token_phrase(company: str, legal_name: str | None) -> bool:
    """
    Match the normalized query as one or more complete tokens.

    "NTT" matches:
      NTT DATA
      NTT Ltd.
      ABC NTT Holdings

    It does NOT match:
      Anttila
      Planttech
      Advantte
    """
    if not legal_name:
        return False

    q = name_tokens(company)
    n = name_tokens(legal_name)

    if not q or len(q) > len(n):
        return False

    width = len(q)
    return any(n[i:i + width] == q for i in range(len(n) - width + 1))


def _name_similarity(query: str, legal_name: str | None) -> float:
    if not legal_name:
        return 0.0

    q = normalize_name(query)
    n = normalize_name(legal_name)

    if q == n:
        return 1.0

    q_tokens = name_tokens(query)
    n_tokens = name_tokens(legal_name)

    if q_tokens and len(q_tokens) <= len(n_tokens):
        width = len(q_tokens)
        if any(n_tokens[i:i + width] == q_tokens for i in range(len(n_tokens) - width + 1)):
            # Exact token/phrase occurrence. Prefer names beginning with the query.
            return 0.95 if n_tokens[:width] == q_tokens else 0.90

    qset = set(q_tokens)
    nset = set(n_tokens)
    if not qset:
        return 0.0

    return min(0.74, len(qset & nset) / len(qset))


@dataclass
class RootCandidate:
    lei: str
    legal_name: str | None
    jurisdiction: str | None
    entity_status: str | None
    matched_seed_count: int = 0
    total_seed_count: int = 0
    coverage: float = 0.0
    direct_parent_votes: int = 0
    ultimate_parent_votes: int = 0
    max_depth: int = 0
    terminal_votes: int = 0
    name_match: float = 0.0
    score: float = 0.0
    seed_leis: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "lei": self.lei,
            "legal_name": self.legal_name,
            "jurisdiction": self.jurisdiction,
            "entity_status": self.entity_status,
            "matched_seed_count": self.matched_seed_count,
            "total_seed_count": self.total_seed_count,
            "coverage": round(self.coverage, 4),
            "direct_parent_votes": self.direct_parent_votes,
            "ultimate_parent_votes": self.ultimate_parent_votes,
            "max_depth": self.max_depth,
            "terminal_votes": self.terminal_votes,
            "name_match": round(self.name_match, 4),
            "score": round(self.score, 4),
            "seed_leis": list(self.seed_leis),
        }


@dataclass
class RootResolution:
    query: str
    status: str
    confidence: str
    root: RootCandidate | None
    candidates: list[RootCandidate]
    seed_matches: list[dict[str, Any]]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "status": self.status,
            "confidence": self.confidence,
            "reason": self.reason,
            "root": self.root.to_dict() if self.root else None,
            "candidates": [c.to_dict() for c in self.candidates],
            "seed_matches": self.seed_matches,
        }


def find_seed_matches(
    lei_conn: sqlite3.Connection,
    company: str,
    limit: int = 100,
    scan_limit: int = 5000,
) -> list[dict[str, Any]]:
    """
    Level 1 seed discovery.

    SQL LIKE is used only as a coarse retrieval mechanism. Results must then
    pass normalized token/phrase matching before they are allowed into the
    corporate graph. This prevents short acronyms such as NTT from matching
    arbitrary substrings inside unrelated names.
    """
    q = normalize_name(company)

    exact = lei_conn.execute(
        """
        SELECT *
        FROM lei_entities
        WHERE legal_name_normalized = ?
        ORDER BY CASE WHEN entity_status = 'ACTIVE' THEN 0 ELSE 1 END, legal_name
        LIMIT ?
        """,
        (q, limit),
    ).fetchall()

    rows = list(exact)

    if not rows:
        coarse = lei_conn.execute(
            """
            SELECT *
            FROM lei_entities
            WHERE legal_name_normalized LIKE ?
            ORDER BY CASE WHEN entity_status = 'ACTIVE' THEN 0 ELSE 1 END, legal_name
            LIMIT ?
            """,
            (f"%{q}%", scan_limit),
        ).fetchall()

        # Critical trust boundary: substring retrieval does not itself make a
        # seed. The company query must appear as complete normalized token(s).
        rows = [
            row for row in coarse
            if _contains_token_phrase(company, row["legal_name"])
        ][:limit]

    result = []
    for row in rows:
        d = dict(row)
        d["name_match"] = _name_similarity(company, d.get("legal_name"))
        result.append(d)

    result.sort(
        key=lambda r: (
            -(r.get("name_match") or 0.0),
            0 if r.get("entity_status") == "ACTIVE" else 1,
            r.get("legal_name") or "",
        )
    )
    return result


def _parents_for(rr_conn: sqlite3.Connection, child_lei: str) -> list[dict[str, Any]]:
    rows = rr_conn.execute(
        """
        SELECT parent_lei, relationship_type, relationship_status
        FROM relationships
        WHERE child_lei = ?
          AND relationship_type IN (
              'IS_DIRECTLY_CONSOLIDATED_BY',
              'IS_ULTIMATELY_CONSOLIDATED_BY'
          )
        """,
        (child_lei,),
    ).fetchall()
    return [dict(r) for r in rows]


def walk_upward(
    rr_conn: sqlite3.Connection,
    seed_lei: str,
    max_depth: int = 12,
) -> dict[str, dict[str, Any]]:
    observed = {
        seed_lei: {
            "depth": 0,
            "direct": False,
            "ultimate": False,
            "terminal": False,
        }
    }
    frontier = [(seed_lei, 0)]
    best_depth = {seed_lei: 0}

    while frontier:
        current, depth = frontier.pop(0)
        if depth >= max_depth:
            continue

        parents = _parents_for(rr_conn, current)
        if not parents:
            observed[current]["terminal"] = True
            continue

        for rel in parents:
            parent = rel["parent_lei"]
            next_depth = depth + 1
            info = observed.setdefault(
                parent,
                {
                    "depth": next_depth,
                    "direct": False,
                    "ultimate": False,
                    "terminal": False,
                },
            )
            info["depth"] = min(info["depth"], next_depth)
            info["direct"] |= rel["relationship_type"] == "IS_DIRECTLY_CONSOLIDATED_BY"
            info["ultimate"] |= rel["relationship_type"] == "IS_ULTIMATELY_CONSOLIDATED_BY"

            previous = best_depth.get(parent)
            if previous is None or next_depth < previous:
                best_depth[parent] = next_depth
                frontier.append((parent, next_depth))

    return observed


def _lookup_many(lei_conn: sqlite3.Connection, leis: list[str]) -> dict[str, dict[str, Any]]:
    if not leis:
        return {}

    placeholders = ",".join("?" for _ in leis)
    rows = lei_conn.execute(
        f"SELECT * FROM lei_entities WHERE lei IN ({placeholders})",
        leis,
    ).fetchall()

    return {row["lei"]: dict(row) for row in rows}


def resolve_company_root(
    company: str,
    lei_db: str = "data/processed/gleif_lei.sqlite",
    rr_db: str = "data/processed/gleif_rr.sqlite",
    seed_limit: int = 100,
    max_depth: int = 12,
) -> RootResolution:
    lei_conn = connect(lei_db)
    rr_conn = connect(rr_db)

    try:
        seeds = find_seed_matches(lei_conn, company, limit=seed_limit)

        if not seeds:
            return RootResolution(
                query=company,
                status="NO_MATCH",
                confidence="UNKNOWN",
                root=None,
                candidates=[],
                seed_matches=[],
                reason=(
                    "No GLEIF Level 1 legal names contained the query as a "
                    "complete normalized token/phrase."
                ),
            )

        paths = {}
        all_leis = set()

        for seed in seeds:
            path = walk_upward(rr_conn, seed["lei"], max_depth=max_depth)
            paths[seed["lei"]] = path
            all_leis.update(path)

        identities = _lookup_many(lei_conn, sorted(all_leis))

        # A lexical seed is graph-informative only when GLEIF provides at
        # least one upward relationship beyond the seed itself. Isolated
        # token matches remain visible, but they must not dilute corporate
        # convergence merely because no topology exists for them.
        informative_seed_leis = {
            seed["lei"]
            for seed in seeds
            if any(
                lei != seed["lei"]
                for lei in paths[seed["lei"]]
            )
        }

        total_seeds = len(seeds)
        topology_seed_count = len(informative_seed_leis)
        candidates = []

        for candidate_lei in sorted(all_leis):
            voting_seeds = []
            direct_votes = 0
            ultimate_votes = 0
            terminal_votes = 0
            max_seen_depth = 0

            for seed in seeds:
                info = paths[seed["lei"]].get(candidate_lei)
                if not info:
                    continue

                # Only graph-informative seeds participate in topology
                # coverage/voting. Isolated lexical matches are preserved in
                # seed_matches but do not count as negative topology evidence.
                if seed["lei"] not in informative_seed_leis:
                    continue

                voting_seeds.append(seed["lei"])
                direct_votes += int(bool(info.get("direct")))
                ultimate_votes += int(bool(info.get("ultimate")))
                terminal_votes += int(bool(info.get("terminal")))
                max_seen_depth = max(max_seen_depth, int(info.get("depth") or 0))

            identity = identities.get(candidate_lei, {})
            coverage = (
                len(voting_seeds) / topology_seed_count
                if topology_seed_count
                else 0.0
            )
            name_match = _name_similarity(company, identity.get("legal_name"))
            active_bonus = 1.0 if identity.get("entity_status") == "ACTIVE" else 0.0

            # Graph convergence is intentionally dominant.
            score = (
                coverage * 100.0
                + ultimate_votes * 8.0
                + terminal_votes * 5.0
                + direct_votes * 2.0
                + min(max_seen_depth, 6) * 1.5
                + name_match * 6.0
                + active_bonus * 2.0
            )

            candidates.append(
                RootCandidate(
                    lei=candidate_lei,
                    legal_name=identity.get("legal_name"),
                    jurisdiction=identity.get("legal_jurisdiction"),
                    entity_status=identity.get("entity_status"),
                    matched_seed_count=len(voting_seeds),
                    total_seed_count=topology_seed_count,
                    coverage=coverage,
                    direct_parent_votes=direct_votes,
                    ultimate_parent_votes=ultimate_votes,
                    max_depth=max_seen_depth,
                    terminal_votes=terminal_votes,
                    name_match=name_match,
                    score=score,
                    seed_leis=voting_seeds,
                )
            )

        candidates.sort(
            key=lambda c: (
                -c.score,
                -c.coverage,
                -c.ultimate_parent_votes,
                -c.terminal_votes,
                c.legal_name or "",
            )
        )

        top = candidates[0] if candidates else None
        second = candidates[1] if len(candidates) > 1 else None

        if top is None:
            return RootResolution(
                query=company,
                status="REVIEW_REQUIRED",
                confidence="LOW",
                root=None,
                candidates=[],
                seed_matches=seeds,
                reason="Seeds were found but no usable graph topology was produced.",
            )

        margin = top.score - second.score if second else top.score
        exact_active = [
            s for s in seeds
            if s.get("name_match") == 1.0 and s.get("entity_status") == "ACTIVE"
        ]

        topology_strong = (
            top.matched_seed_count >= 2
            and top.coverage >= 0.60
            and (top.ultimate_parent_votes >= 1 or top.terminal_votes >= 2)
            and margin >= 8.0
        )

        unique_exact = (
            len(exact_active) == 1
            and top.lei == exact_active[0]["lei"]
            and (second is None or margin >= 8.0)
        )

        if topology_strong:
            status = "AUTO_RESOLVED"
            confidence = "HIGH"
            reason = (
                f"{top.matched_seed_count}/{top.total_seed_count} graph-informative "
                f"matched legal entities converge on {top.lei}; topology includes "
                f"{top.ultimate_parent_votes} ultimate-parent vote(s) and "
                f"{top.terminal_votes} terminal-root vote(s)."
            )
        elif unique_exact:
            status = "AUTO_RESOLVED"
            confidence = "MEDIUM"
            reason = (
                "One active exact legal-name match remains the strongest root "
                "after relationship-graph inspection."
            )
        else:
            status = "REVIEW_REQUIRED"
            confidence = "MEDIUM" if top.coverage >= 0.50 else "LOW"
            reason = (
                "A leading root candidate exists, but graph convergence is not "
                "strong enough to select it automatically."
            )

        return RootResolution(
            query=company,
            status=status,
            confidence=confidence,
            root=top,
            candidates=candidates[:20],
            seed_matches=seeds,
            reason=reason,
        )

    finally:
        lei_conn.close()
        rr_conn.close()
