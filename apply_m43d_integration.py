#!/usr/bin/env python3
from pathlib import Path

path = Path("code/helix_company.py")

if not path.is_file():
    raise SystemExit("ERROR: run this from the corporate_helix repository root")

text = path.read_text()

import_anchor = "from pathlib import Path\n\n\nRELATIONSHIP_LABELS"
import_replacement = (
    "from pathlib import Path\n\n"
    "from root_entity_resolver import resolve_company_root\n\n\n"
    "RELATIONSHIP_LABELS"
)

if "from root_entity_resolver import resolve_company_root" not in text:
    if import_anchor not in text:
        raise SystemExit("ERROR: import anchor not found; helix_company.py differs from expected version")
    text = text.replace(import_anchor, import_replacement, 1)

old = '''    else:
        candidates = find_company(
            args.lei_index,
            args.company,
        )

        if not candidates:
            raise SystemExit(
                f'No GLEIF Level 1 matches found for "{args.company}".'
            )

        root = choose_root(
            candidates,
        )

        if root is None:
            print_candidates(candidates)

            print(
                "Root identity is ambiguous."
            )

            print(
                "Run again with:"
            )

            print()
            print(
                '  python3 code/helix_company.py '
                f'--company "{args.company}" '
                "--lei <LEI>"
            )

            raise SystemExit(2)

'''

new = '''    else:
        resolution = resolve_company_root(
            company=args.company,
            lei_db=args.lei_index,
            rr_db=args.rr_index,
        )

        if resolution.status != "AUTO_RESOLVED" or not resolution.root:
            print()
            print("=" * 72)
            print("CORPORATION HELIX — ROOT ENTITY RESOLUTION")
            print("=" * 72)
            print(f"Query      : {args.company}")
            print(f"Resolution : {resolution.status}")
            print(f"Confidence : {resolution.confidence}")
            print(f"Reason     : {resolution.reason}")
            print()
            print("Top root candidates:")

            for i, candidate in enumerate(resolution.candidates[:10], 1):
                print(f"[{i}] {candidate.legal_name or candidate.lei}")
                print(f"    LEI      : {candidate.lei}")
                print(
                    f"    Coverage : "
                    f"{candidate.matched_seed_count}/"
                    f"{candidate.total_seed_count} "
                    f"({candidate.coverage:.0%})"
                )
                print(f"    Score    : {candidate.score:.2f}")

            print()
            print("Root identity was not safe to select automatically.")
            print("Operator override:")
            print()
            print(
                '  python3 code/helix_company.py '
                f'--company "{args.company}" '
                "--lei <LEI>"
            )

            raise SystemExit(2)

        conn = connect(args.lei_index)
        root = lookup_lei(conn, resolution.root.lei)
        conn.close()

        if not root:
            raise SystemExit(
                "Resolved root LEI was not found in the local Level 1 index: "
                f"{resolution.root.lei}"
            )

'''

if old in text:
    text = text.replace(old, new, 1)
elif "resolution = resolve_company_root(" in text:
    print("M4.3D integration block already present; leaving it unchanged.")
else:
    raise SystemExit(
        "ERROR: expected root-selection block not found; "
        "helix_company.py differs from the known main-branch version"
    )

path.write_text(text)
print("Updated code/helix_company.py successfully.")
