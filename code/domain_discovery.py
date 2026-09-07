#!/usr/bin/env python3
from __future__ import annotations

"""M4.3B candidate-domain discovery bridge.

Two modes are supported:

1. Seeded mode (`--seeds`) preserves supplied search/provider URLs.
2. Batch mode (`--discover-all`) searches for candidate URLs for every Helix
   legal entity in the input file.

Every discovered URL is preserved only as CANDIDATE_DISCOVERY provenance.
Optionally, `--verify-official` fetches the page and emits identity-grade
OFFICIAL_WEBSITE evidence only when the page explicitly names the target legal
entity.

Candidate discovery != ownership evidence.
"""

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from domain_candidates import CorporateEntity, EvidenceType, load_entities, match_entity, normalize_domain
from providers.official_site import fetch_and_inspect
from providers.web_search import SearchResult, search_official_site_candidates


SearchFn = Callable[..., tuple[str, list[SearchResult]]]


def _load_seeds(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("seeds", [])
    if not isinstance(payload, list):
        raise ValueError("Seed input must be a JSON list or {'seeds': [...]}.")
    return [x for x in payload if isinstance(x, dict)]


def _seed_url(seed: dict[str, Any]) -> str:
    value = seed.get("url") or seed.get("reference")
    if not value:
        raise ValueError(f"Seed is missing url/reference: {seed!r}")
    return str(value)


def discover_all_entity_seeds(
    entities: list[CorporateEntity],
    *,
    max_results_per_entity: int = 5,
    timeout: int = 20,
    search_fn: SearchFn = search_official_site_candidates,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Discover candidate URLs for every entity without asserting ownership."""
    seeds: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for entity in entities:
        try:
            query, results = search_fn(
                entity.entity_name,
                limit=max_results_per_entity,
                timeout=timeout,
            )
        except Exception as exc:
            errors.append({
                "entity_lei": entity.entity_lei,
                "entity_name": entity.entity_name,
                "error": f"{type(exc).__name__}: {exc}",
            })
            continue

        seen_urls: set[str] = set()
        for result in results:
            if result.url in seen_urls:
                continue
            seen_urls.add(result.url)
            seeds.append({
                "entity_lei": entity.entity_lei,
                "entity_name": entity.entity_name,
                "url": result.url,
                "provider": "WEB_SEARCH",
                "query": query,
                "title": result.title,
            })

    return seeds, errors


def build_discovery_observations(
    entities: list[CorporateEntity],
    seeds: list[dict[str, Any]],
    *,
    verify_official: bool = False,
    timeout: int = 20,
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []

    for seed in seeds:
        entity = match_entity(entities, seed)
        url = _seed_url(seed)
        domain = normalize_domain(url)
        provider = str(seed.get("provider") or seed.get("source") or "SEARCH_DISCOVERY")

        discovery_observation = {
            "entity_lei": entity.entity_lei,
            "entity_name": entity.entity_name,
            "domain": domain,
            "provider": provider,
            "evidence_type": EvidenceType.CANDIDATE_DISCOVERY.value,
            "reference": url,
            "observed_value": seed.get("title") or domain,
            "subject_name": entity.entity_name,
            "subject_identifier": entity.entity_lei,
            "supports_attribution": None,
            "raw": {
                "discovery_provider": provider,
                "query": seed.get("query"),
                "title": seed.get("title"),
                "snippet": seed.get("snippet"),
            },
        }
        observations.append(discovery_observation)

        if not verify_official:
            continue

        try:
            inspected = fetch_and_inspect(url, entity.entity_name, timeout=timeout)
        except Exception as exc:
            # Discovery provenance remains valid even when live verification is
            # temporarily unavailable. Never convert a network failure into
            # attribution evidence or a negative ownership assertion.
            discovery_observation["raw"]["verification_error"] = f"{type(exc).__name__}: {exc}"
            continue

        if inspected.exact_legal_name_match:
            observations.append({
                "entity_lei": entity.entity_lei,
                "entity_name": entity.entity_name,
                "domain": inspected.domain,
                "provider": "OFFICIAL_SITE",
                "evidence_type": EvidenceType.OFFICIAL_WEBSITE.value,
                "reference": inspected.url,
                "observed_value": inspected.matched_name,
                "subject_name": entity.entity_name,
                "subject_identifier": entity.entity_lei,
                "supports_attribution": True,
                "raw": {
                    "match_method": inspected.match_method,
                    "title": inspected.title,
                    "http_status": inspected.status_code,
                },
            })

    return observations


def main() -> int:
    ap = argparse.ArgumentParser(description="Create M4.3B candidate-domain discovery observations.")
    ap.add_argument("--entities", required=True, type=Path)
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--seeds", type=Path, help="JSON seed/search-result input")
    source.add_argument(
        "--discover-all",
        action="store_true",
        help="Search for candidate URLs for every legal entity in --entities",
    )
    ap.add_argument("--max-results-per-entity", type=int, default=5)
    ap.add_argument("--verify-official", action="store_true", help="Fetch candidate URLs and require an explicit legal-name declaration")
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    entities = load_entities(args.entities)
    search_errors: list[dict[str, Any]] = []

    if args.discover_all:
        seeds, search_errors = discover_all_entity_seeds(
            entities,
            max_results_per_entity=max(1, args.max_results_per_entity),
            timeout=args.timeout,
        )
    else:
        seeds = _load_seeds(args.seeds)

    observations = build_discovery_observations(
        entities,
        seeds,
        verify_official=args.verify_official,
        timeout=args.timeout,
    )

    discovery_count = sum(x["evidence_type"] == EvidenceType.CANDIDATE_DISCOVERY.value for x in observations)
    official_count = sum(x["evidence_type"] == EvidenceType.OFFICIAL_WEBSITE.value for x in observations)
    entities_with_seeds = len({(s.get("entity_lei") or s.get("entity_name")) for s in seeds})
    entities_with_official = len({(x.get("entity_lei") or x.get("entity_name")) for x in observations if x["evidence_type"] == EvidenceType.OFFICIAL_WEBSITE.value})

    payload = {
        "observations": observations,
        "discovery_summary": {
            "entity_count": len(entities),
            "entities_with_candidates": entities_with_seeds,
            "entities_with_verified_official_site": entities_with_official,
            "seed_count": len(seeds),
            "candidate_discovery_observations": discovery_count,
            "verified_official_site_declarations": official_count,
            "search_error_count": len(search_errors),
        },
        "search_errors": search_errors,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Entities: {len(entities)}")
    print(f"Entities with candidate results: {entities_with_seeds}")
    print(f"Seeds: {len(seeds)}")
    print(f"Candidate discovery observations: {discovery_count}")
    print(f"Verified official-site declarations: {official_count}")
    print(f"Search errors: {len(search_errors)}")
    print(f"Wrote: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
