from __future__ import annotations

from difflib import SequenceMatcher

from ..models import CandidateMatch, EntityCandidate, InfrastructureIdentity, MatchSignal
from .normalize import normalize_address, normalize_name


def _sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _address_similarity(infra: InfrastructureIdentity, entity: EntityCandidate) -> float:
    left = [normalize_address(a.compact()) for a in infra.addresses if a.compact()]
    right = []
    for addr in (entity.legal_address, entity.headquarters_address, *entity.other_addresses):
        if addr and addr.compact():
            right.append(normalize_address(addr.compact()))
    if not left or not right:
        return 0.0
    return max(_sim(a, b) for a in left for b in right)


def score_candidate(infra: InfrastructureIdentity, entity: EntityCandidate) -> CandidateMatch:
    infra_names = [normalize_name(n) for n in infra.organization_names]
    entity_names = [normalize_name(entity.legal_name), *[normalize_name(n) for n in entity.other_names]]
    name_score = max((_sim(a, b) for a in infra_names for b in entity_names if a and b), default=0.0)
    address_score = _address_similarity(infra, entity)

    country_score: float | None = None
    if infra.country and entity.jurisdiction:
        country_score = 1.0 if infra.country.upper() in entity.jurisdiction.upper() or entity.jurisdiction.upper() in infra.country.upper() else 0.0

    signals = [
        MatchSignal("name", "match" if name_score >= 0.9 else "partial" if name_score >= 0.72 else "weak", name_score),
        MatchSignal("address", "match" if address_score >= 0.82 else "partial" if address_score >= 0.60 else "unknown" if address_score == 0 else "weak", address_score or None),
    ]
    if country_score is not None:
        signals.append(MatchSignal("country", "match" if country_score else "conflict", country_score))
    else:
        signals.append(MatchSignal("country", "unknown"))

    # Conservative MVP ranking. Name gets a candidate into consideration; a
    # second structured signal is required for a strong automatic decision.
    score = 0.62 * name_score + 0.28 * address_score + 0.10 * (country_score or 0.0)
    has_structured_support = address_score >= 0.70 or country_score == 1.0
    has_structured_conflict = country_score == 0.0 and infra.country is not None and entity.jurisdiction is not None

    if name_score >= 0.90 and has_structured_support and not has_structured_conflict:
        decision = "strong_candidate"
    elif name_score >= 0.80 and not has_structured_conflict:
        decision = "review"
    elif has_structured_conflict or name_score < 0.65:
        decision = "reject"
    else:
        decision = "weak_candidate"

    return CandidateMatch(infra.resource, entity, signals, decision, score)


def rank_candidates(infra: InfrastructureIdentity, entities: list[EntityCandidate], limit: int = 10) -> list[CandidateMatch]:
    scored = [score_candidate(infra, e) for e in entities]
    scored.sort(key=lambda x: x.rank_score, reverse=True)
    return scored[:limit]
