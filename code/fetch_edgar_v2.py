"""
Fetch subsidiary data from SEC EDGAR (Exhibit 21 of 10-K filings).

SEC's filing/metadata lookups ARE clean JSON APIs, no key needed. But the
Exhibit 21 document itself (the actual subsidiary list) has no standardized
format across filers — sometimes an HTML table, sometimes a flat text list,
formatting varies filing to filing. This script gets you to the raw text of
that document reliably; turning it into structured rows is inherently
best-effort and worth a human sanity-check, same as the manual pull was.

SEC REQUIRES a descriptive User-Agent header (name + contact email) on all
requests to data.sec.gov and sec.gov, or you'll get blocked. Pass --user-agent
or set SEC_USER_AGENT env var.

Usage:
    python src/fetch_edgar.py --company "SentinelOne" \\
        --user-agent "Steve <you@example.com>" \\
        --out data/raw/edgar_sentinelone.json
"""
import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error
from html.parser import HTMLParser

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
FILING_INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/index.json"
FILING_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{filename}"


def fetch_json(url: str, user_agent: str):
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_text(url: str, user_agent: str):
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


LEGAL_SUFFIXES = {
    "corp", "corporation", "inc", "incorporated", "company", "co",
    "limited", "ltd", "plc",
}


def normalize_company_name(name: str) -> str:
    """Normalize a company name for conservative SEC entity matching.

    This intentionally avoids fuzzy matching. It removes punctuation and common
    English legal suffixes so names such as "Sony Group Corporation" and
    SEC's "SONY GROUP CORP" resolve to the same normalized form.
    """
    text = name.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = [t for t in text.split() if t]
    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def _dedupe_by_cik(entries):
    """Collapse duplicate SEC ticker rows that refer to the same CIK."""
    by_cik = {}
    for entry in entries:
        cik = str(entry["cik_str"])
        existing = by_cik.get(cik)
        if existing is None:
            merged = dict(entry)
            merged["tickers"] = [entry.get("ticker")] if entry.get("ticker") else []
            by_cik[cik] = merged
        else:
            ticker = entry.get("ticker")
            if ticker and ticker not in existing["tickers"]:
                existing["tickers"].append(ticker)
    return list(by_cik.values())


def find_cik(company_name: str, user_agent: str):
    """Resolve a company query against SEC's company/ticker mapping.

    Resolution order is deliberately conservative:
      1. direct CIK
      2. exact ticker
      3. exact SEC legal title
      4. exact normalized legal title
      5. normalized substring fallback

    Results are deduplicated by CIK so multiple tickers for the same filer do
    not appear as multiple companies.
    """
    data = fetch_json(TICKERS_URL, user_agent)
    entries = list(data.values())
    query = company_name.strip()

    # Direct CIK lookup (allow zero-padded CIKs).
    if query.isdigit():
        q_cik = str(int(query))
        return _dedupe_by_cik(
            [e for e in entries if str(e["cik_str"]) == q_cik]
        )

    # Exact ticker lookup.
    ticker_matches = [
        e for e in entries
        if str(e.get("ticker", "")).casefold() == query.casefold()
    ]
    if ticker_matches:
        return _dedupe_by_cik(ticker_matches)

    # Exact SEC title lookup.
    exact_title = [
        e for e in entries
        if str(e.get("title", "")).strip().casefold() == query.casefold()
    ]
    if exact_title:
        return _dedupe_by_cik(exact_title)

    normalized_query = normalize_company_name(query)
    if not normalized_query:
        return []

    normalized_exact = [
        e for e in entries
        if normalize_company_name(str(e.get("title", ""))) == normalized_query
    ]
    if normalized_exact:
        return _dedupe_by_cik(normalized_exact)

    # Last-resort compatibility with the original behavior, but compare the
    # normalized forms and deduplicate by CIK.
    substring_matches = [
        e for e in entries
        if normalized_query in normalize_company_name(str(e.get("title", "")))
    ]
    return _dedupe_by_cik(substring_matches)


class TableTextExtractor(HTMLParser):
    """Minimal HTML->text extractor that preserves row/cell boundaries as
    tabs/newlines so downstream normalization has a fighting chance, without
    pulling in a heavy HTML parsing dependency."""

    def __init__(self):
        super().__init__()
        self.rows = []
        self._current_row = []
        self._current_cell = []
        self._in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag in ("td", "th"):
            self._in_cell = True
            self._current_cell = []
        elif tag == "tr":
            self._current_row = []
        elif tag == "br":
            if self._in_cell:
                self._current_cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self._current_row.append("".join(self._current_cell).strip())
            self._in_cell = False
        elif tag == "tr":
            if any(c for c in self._current_row):
                self.rows.append(self._current_row)

    def handle_data(self, data):
        if self._in_cell:
            self._current_cell.append(data)


def extract_rows_from_html(html: str):
    parser = TableTextExtractor()
    parser.feed(html)
    if parser.rows:
        return parser.rows

    # No table found — fall back to stripping tags and returning non-empty lines.
    text = re.sub(r"<[^>]+>", "\n", html)
    text = re.sub(r"&nbsp;", " ", text)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return [[l] for l in lines]


def get_exhibit_21_docs(cik: str, user_agent: str, max_filings: int = 3):
    """Return list of {accession, filing_date, exhibit_url} for recent 10-Ks
    that include an EX-21 exhibit."""
    cik_padded = cik.zfill(10)
    subs = fetch_json(SUBMISSIONS_URL.format(cik=cik_padded), user_agent)
    recent = subs["filings"]["recent"]

    results = []
    for i, form in enumerate(recent["form"]):
        if form not in ("10-K", "10-K/A"):
            continue
        accession = recent["accessionNumber"][i]
        filing_date = recent["filingDate"][i]
        acc_nodash = accession.replace("-", "")
        cik_int = str(int(cik))

        index_url = FILING_INDEX_URL.format(cik_int=cik_int, acc_nodash=acc_nodash)
        try:
            index_data = fetch_json(index_url, user_agent)
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            print(f"Warning: couldn't fetch index for {accession}: {e}", file=sys.stderr)
            continue

        exhibit_file = None
        for item in index_data.get("directory", {}).get("item", []):
            name = item.get("name", "")
            if re.search(r"ex-?21", name, re.IGNORECASE):
                exhibit_file = name
                break

        if exhibit_file:
            results.append({
                "accession": accession,
                "filing_date": filing_date,
                "exhibit_url": FILING_DOC_URL.format(
                    cik_int=cik_int, acc_nodash=acc_nodash, filename=exhibit_file
                ),
            })

        if len(results) >= max_filings:
            break

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--user-agent",
        default=os.environ.get("SEC_USER_AGENT"),
        help="Required by SEC: 'Your Name <email@example.com>'",
    )
    parser.add_argument("--max-filings", type=int, default=1, help="How many 10-Ks to pull (most recent first)")
    args = parser.parse_args()

    if not args.user_agent:
        print(
            "SEC requires a descriptive User-Agent (name + email). "
            "Pass --user-agent or set SEC_USER_AGENT.",
            file=sys.stderr,
        )
        sys.exit(1)

    matches = find_cik(args.company, args.user_agent)
    if not matches:
        print(f"No CIK found for '{args.company}'", file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        print(f"Multiple matches for '{args.company}', using first: ", file=sys.stderr)
        for m in matches:
            print(f"  - {m['title']} (CIK {m['cik_str']}, tickers {', '.join(m.get('tickers', [m.get('ticker', '')]))})", file=sys.stderr)

    cik = str(matches[0]["cik_str"])
    company_title = matches[0]["title"]

    exhibits = get_exhibit_21_docs(cik, args.user_agent, max_filings=args.max_filings)
    if not exhibits:
        print(f"No EX-21 exhibits found in recent 10-K filings for CIK {cik}", file=sys.stderr)
        sys.exit(1)

    output = {"company": company_title, "cik": cik, "filings": []}
    for ex in exhibits:
        html = fetch_text(ex["exhibit_url"], args.user_agent)
        rows = extract_rows_from_html(html)
        output["filings"].append({
            "accession": ex["accession"],
            "filing_date": ex["filing_date"],
            "exhibit_url": ex["exhibit_url"],
            "extracted_rows": rows,
        })

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(output, f, indent=2)

    total_rows = sum(len(f["extracted_rows"]) for f in output["filings"])
    print(f"Wrote {len(output['filings'])} filing(s), {total_rows} extracted rows, to {args.out}")
    print("NOTE: extracted_rows is best-effort — Exhibit 21 has no standard format. Review before trusting.")


if __name__ == "__main__":
    main()
