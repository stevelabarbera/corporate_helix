"""
Fetch LEI entity data and ownership relationships from the GLEIF API.

Free, no API key required. Base: https://api.gleif.org/api/v1

Two things GLEIF gives you that EDGAR structurally can't:
1. Not limited to SEC's "principal/significant subsidiaries" disclosure
   threshold — GLEIF returns every LEI-registered child, direct and ultimate.
2. Explicit "reporting exceptions" when a parent relationship isn't
   reported (e.g. child opted out, or the parent itself has no LEI) —
   this is NOT the same as "no parent exists." We surface the exception
   reason rather than silently treating it as a standalone entity.

Coverage caveat in the other direction: GLEIF only knows about entities
that registered for an LEI (generally required for financial/regulatory
activity). Small non-financial subsidiaries may simply not be in GLEIF at
all — that's a gap EDGAR/OpenCorporates/registries fill instead.

Usage:
    python src/fetch_gleif.py --company "Sony Group" --out data/raw/gleif_sony.json
    python src/fetch_gleif.py --lei 5493003BQVOSC6NCLQ85 --out data/raw/gleif_sony.json
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

BASE = "https://api.gleif.org/api/v1"
PAGE_SIZE = 200  # GLEIF max per page


def fetch_json(url: str):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.api+json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        if e.code == 429:
            print("Rate limited by GLEIF. Waiting 5s and retrying once...", file=sys.stderr)
            time.sleep(5)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        raise


def search_entities(name: str, size: int = 20):
    """Fulltext search across legal names. Returns list of candidate records."""
    params = {"filter[fulltext]": name, "page[size]": size}
    url = f"{BASE}/lei-records?{urllib.parse.urlencode(params)}"
    data = fetch_json(url)
    if not data:
        return []

    results = []
    for entry in data.get("data", []):
        attrs = entry.get("attributes", {})
        entity = attrs.get("entity", {})
        legal_name = entity.get("legalName", {}).get("name")
        results.append({
            "lei": entry.get("id"),
            "legal_name": legal_name,
            "jurisdiction": entity.get("jurisdiction"),
            "legal_form": entity.get("legalForm", {}).get("id"),
            "status": entity.get("status"),
            "registration_status": attrs.get("registration", {}).get("status"),
            "headquarters_country": entity.get("headquartersAddress", {}).get("country"),
        })
    return results


def get_record(lei: str):
    """Full LEI record, including relationships links section."""
    data = fetch_json(f"{BASE}/lei-records/{lei}")
    return data.get("data") if data else None


def summarize_related_record(record: dict):
    if not record:
        return None
    attrs = record.get("attributes", {})
    entity = attrs.get("entity", {})
    return {
        "lei": record.get("id"),
        "legal_name": entity.get("legalName", {}).get("name"),
        "jurisdiction": entity.get("jurisdiction"),
        "status": entity.get("status"),
    }


def get_relationship_or_exception(lei: str, relationship: str):
    """
    relationship: 'direct-parent' or 'ultimate-parent'
    Returns {'type': 'parent', 'entity': {...}} or
            {'type': 'exception', 'reason': '...', 'category': '...'}
            or None if the relationship link isn't present at all.
    """
    record = get_record(lei)
    if not record:
        return None

    rel = record.get("relationships", {}).get(relationship, {})
    links = rel.get("links", {})

    if "lei-record" in links or "related" in links:
        related_url = links.get("related") or links.get("lei-record")
        related_data = fetch_json(related_url) if related_url.startswith("http") else fetch_json(f"{BASE}{related_url}")
        related_record = related_data.get("data") if related_data else None
        return {"type": "parent", "entity": summarize_related_record(related_record)}

    if "reporting-exception" in links:
        exc_url = links["reporting-exception"]
        exc_data = fetch_json(exc_url if exc_url.startswith("http") else f"{BASE}{exc_url}")
        if exc_data and exc_data.get("data"):
            exc_attrs = exc_data["data"].get("attributes", {})
            return {
                "type": "exception",
                "reason": exc_attrs.get("reason"),
                "category": exc_attrs.get("category"),
            }
        return {"type": "exception", "reason": "unspecified", "category": None}

    return None


def get_children(lei: str, relationship: str):
    """relationship: 'direct-children' or 'ultimate-children'. Paginated."""
    children = []
    url = f"{BASE}/lei-records/{lei}/{relationship}?page[size]={PAGE_SIZE}"

    while url:
        data = fetch_json(url)
        if not data:
            break
        for entry in data.get("data", []):
            attrs = entry.get("attributes", {})
            entity = attrs.get("entity", {})
            children.append({
                "lei": entry.get("id"),
                "legal_name": entity.get("legalName", {}).get("name"),
                "jurisdiction": entity.get("jurisdiction"),
                "legal_form": entity.get("legalForm", {}).get("id"),
                "status": entity.get("status"),
            })
        next_link = data.get("links", {}).get("next")
        url = next_link if next_link else None
        if url:
            time.sleep(0.2)  # polite pagination pacing

    return children


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", help="Company name to search for")
    parser.add_argument("--lei", help="Skip search, use this LEI directly")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    if not args.company and not args.lei:
        print("Provide --company or --lei", file=sys.stderr)
        sys.exit(1)

    if args.lei:
        lei = args.lei
        record = get_record(lei)
        if not record:
            print(f"No LEI record found for {lei}", file=sys.stderr)
            sys.exit(1)
        entity_summary = summarize_related_record(record)
        matches_note = None
    else:
        candidates = search_entities(args.company)
        if not candidates:
            print(f"No GLEIF matches for '{args.company}'", file=sys.stderr)
            sys.exit(1)
        if len(candidates) > 1:
            print(f"Multiple GLEIF matches for '{args.company}':", file=sys.stderr)
            for c in candidates:
                print(f"  - {c['legal_name']} (LEI {c['lei']}, {c['jurisdiction']}, status {c['status']})", file=sys.stderr)
            print("Using first match. Re-run with --lei to target a specific one.", file=sys.stderr)
        entity_summary = candidates[0]
        lei = entity_summary["lei"]
        matches_note = [c["lei"] for c in candidates]

    print(f"Resolved LEI: {lei} ({entity_summary.get('legal_name')})", file=sys.stderr)

    direct_parent = get_relationship_or_exception(lei, "direct-parent")
    ultimate_parent = get_relationship_or_exception(lei, "ultimate-parent")
    direct_children = get_children(lei, "direct-children")
    ultimate_children = get_children(lei, "ultimate-children")

    output = {
        "query_company": args.company,
        "resolved_lei": lei,
        "entity": entity_summary,
        "other_search_matches": matches_note,
        "direct_parent": direct_parent,
        "ultimate_parent": ultimate_parent,
        "direct_children": direct_children,
        "ultimate_children": ultimate_children,
        "direct_children_count": len(direct_children),
        "ultimate_children_count": len(ultimate_children),
    }

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(
        f"Wrote {len(direct_children)} direct children, "
        f"{len(ultimate_children)} ultimate children, to {args.out}"
    )
    print("NOTE: GLEIF only covers LEI-registered entities — combine with EDGAR/registries for full coverage.")


if __name__ == "__main__":
    main()
