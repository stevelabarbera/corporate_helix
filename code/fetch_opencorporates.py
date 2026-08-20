"""
Fetch company search results from the OpenCorporates API.

Requires an API token — OpenCorporates now returns 503 on unauthenticated
requests. Get one at https://opencorporates.com/api_accounts/new (free tier
has a limited monthly call quota).

Set it as an env var before running:
    export OPENCORPORATES_API_TOKEN=your_token_here

Usage:
    python src/fetch_opencorporates.py --company "SentinelOne" --out data/raw/oc_sentinelone.json
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

BASE_URL = "https://api.opencorporates.com/v0.4/companies/search"


def search_companies(query: str, api_token: str, per_page: int = 30, max_pages: int = 5):
    """Page through OpenCorporates search results for a query string."""
    all_companies = []
    page = 1

    while page <= max_pages:
        params = {
            "q": query,
            "per_page": per_page,
            "page": page,
            "api_token": api_token,
        }
        url = f"{BASE_URL}?{urllib.parse.urlencode(params)}"

        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 503:
                print(
                    "503 from OpenCorporates — usually means a missing/invalid "
                    "api_token. Check OPENCORPORATES_API_TOKEN.",
                    file=sys.stderr,
                )
            elif e.code == 429:
                print("Rate limited (429). Try again later or reduce max_pages.", file=sys.stderr)
            else:
                print(f"HTTP error {e.code}: {e.reason}", file=sys.stderr)
            raise
        except urllib.error.URLError as e:
            print(f"Network error reaching OpenCorporates: {e.reason}", file=sys.stderr)
            raise

        results = data.get("results", {})
        companies = results.get("companies", [])
        if not companies:
            break

        for entry in companies:
            c = entry.get("company", entry)
            all_companies.append({
                "name": c.get("name"),
                "company_number": c.get("company_number"),
                "jurisdiction_code": c.get("jurisdiction_code"),
                "current_status": c.get("current_status"),
                "incorporation_date": c.get("incorporation_date"),
                "dissolution_date": c.get("dissolution_date"),
                "company_type": c.get("company_type"),
                "opencorporates_url": c.get("opencorporates_url"),
                "registered_address_in_full": c.get("registered_address_in_full"),
                "source_query": query,
            })

        total_pages = results.get("total_pages", 1)
        if page >= total_pages:
            break

        page += 1
        time.sleep(0.5)  # be polite to the API, avoid rate-limit bursts

    return all_companies


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", required=True, help="Company name to search for")
    parser.add_argument("--out", required=True, help="Output JSON path")
    parser.add_argument("--max-pages", type=int, default=5)
    args = parser.parse_args()

    api_token = os.environ.get("OPENCORPORATES_API_TOKEN")
    if not api_token:
        print(
            "OPENCORPORATES_API_TOKEN not set. Get a token at "
            "https://opencorporates.com/api_accounts/new and export it.",
            file=sys.stderr,
        )
        sys.exit(1)

    companies = search_companies(args.company, api_token, max_pages=args.max_pages)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(companies, f, indent=2)

    print(f"Wrote {len(companies)} results to {args.out}")


if __name__ == "__main__":
    main()
