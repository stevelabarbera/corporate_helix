"""
Stream-search a (potentially multi-GB) GLEIF lei2 Golden Copy file for
entities matching target company name(s). Memory-safe via ijson streaming
— does not load the file into memory.

Usage:
    pip install ijson
    python src/gleif_bulk_search.py \\
        --file /path/to/lei2-golden-copy.json \\
        --names "sentinelone,sony,ntt data,lumen,comcast" \\
        --out data/processed/gleif_lei2_matches.json
"""
import argparse
import json
import sys
import ijson


def extract_value(field):
    """Golden Copy JSON wraps every leaf value as {'$': value, ...}."""
    if isinstance(field, dict):
        return field.get("$")
    return field


def record_matches(record, needles):
    entity = record.get("Entity", {})
    legal_name = extract_value(entity.get("LegalName", {}))
    if not legal_name:
        return False, None
    name_lower = legal_name.lower()
    for needle in needles:
        if needle in name_lower:
            return True, legal_name
    return False, None


def flatten_record(record):
    entity = record.get("Entity", {})
    legal_addr = entity.get("LegalAddress", {})
    hq_addr = entity.get("HeadquartersAddress", {})
    legal_form = entity.get("LegalForm", {})
    registration = record.get("Registration", {})

    return {
        "lei": extract_value(record.get("LEI", {})),
        "legal_name": extract_value(entity.get("LegalName", {})),
        "legal_jurisdiction": extract_value(entity.get("LegalJurisdiction", {})),
        "entity_status": extract_value(entity.get("EntityStatus", {})),
        "entity_category": extract_value(entity.get("EntityCategory", {})),
        "legal_form_code": extract_value(legal_form.get("EntityLegalFormCode", {})),
        "other_legal_form": extract_value(legal_form.get("OtherLegalForm", {})),
        "legal_address_country": extract_value(legal_addr.get("Country", {})),
        "legal_address_city": extract_value(legal_addr.get("City", {})),
        "hq_country": extract_value(hq_addr.get("Country", {})),
        "hq_city": extract_value(hq_addr.get("City", {})),
        "registration_status": extract_value(registration.get("RegistrationStatus", {})),
        "initial_registration_date": extract_value(registration.get("InitialRegistrationDate", {})),
        "last_update_date": extract_value(registration.get("LastUpdateDate", {})),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="Path to lei2 Golden Copy JSON file")
    parser.add_argument("--names", required=True, help="Comma-separated substrings to match (case-insensitive)")
    parser.add_argument("--out", required=True)
    parser.add_argument("--path", default="records.item", help="ijson path to stream items from")
    parser.add_argument("--progress-every", type=int, default=250000)
    args = parser.parse_args()

    needles = [n.strip().lower() for n in args.names.split(",") if n.strip()]
    if not needles:
        print("No search names provided.", file=sys.stderr)
        sys.exit(1)

    matches = []
    total_scanned = 0

    print(f"Streaming {args.file} — this may take a while for multi-GB files...", file=sys.stderr)

    with open(args.file, "rb") as f:
        for record in ijson.items(f, args.path):
            total_scanned += 1
            is_match, legal_name = record_matches(record, needles)
            if is_match:
                matches.append(flatten_record(record))

            if total_scanned % args.progress_every == 0:
                print(f"  ...scanned {total_scanned:,} records, {len(matches)} matches so far", file=sys.stderr)

    print(f"Done. Scanned {total_scanned:,} total records, found {len(matches)} matches.", file=sys.stderr)

    import os
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"search_terms": needles, "total_scanned": total_scanned, "matches": matches}, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(matches)} matches to {args.out}")


if __name__ == "__main__":
    main()
