#!/usr/bin/env python3
"""Collect SEC passages for one structure-disclosure change.

This collector retrieves candidate documents and quotes; it does not infer a
corporate event. Output is a guarded structure-change evidence packet.
"""

import argparse
import hashlib
import json
import os
import re
import urllib.request
from pathlib import Path

from adjudication.structure_change_packet import build_structure_change_packet
from providers.edgar_resolver import strip_html


SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SUBMISSIONS_ARCHIVE_URL = "https://data.sec.gov/submissions/{name}"
DOCUMENT_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/index.json"
FORMS = {"8-K", "8-K/A", "10-Q", "10-Q/A", "10-K", "10-K/A"}


def get_json(url, user_agent):
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())


def get_text(url, user_agent):
    request = urllib.request.Request(
        url, headers={"User-Agent": user_agent, "Accept-Encoding": "identity"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", "replace")


def _value(records, field, index, default=""):
    values = records.get(field) or []
    return values[index] if index < len(values) else default


def _records(records, start, end):
    found = []
    for index, form in enumerate(records.get("form") or []):
        date = _value(records, "filingDate", index)
        if form not in FORMS or not (start <= date <= end):
            continue
        accession = _value(records, "accessionNumber", index)
        primary = _value(records, "primaryDocument", index)
        if not accession or not primary:
            continue
        found.append({
            "form": form,
            "filing_date": date,
            "accession": accession,
            "primary_document": primary,
            "items": _value(records, "items", index),
        })
    return found


def _archive_overlaps(metadata, start, end):
    first = str(metadata.get("filingFrom") or "")
    last = str(metadata.get("filingTo") or "")
    if not first or not last:
        return True
    return first <= end and last >= start


def filing_metadata(cik, user_agent, start, end, *, json_loader=get_json):
    cik10 = str(int(cik)).zfill(10)
    submissions = json_loader(SUBMISSIONS_URL.format(cik=cik10), user_agent)
    filings = submissions.get("filings") or {}
    result = _records(filings.get("recent") or {}, start, end)
    for metadata in filings.get("files") or []:
        if not _archive_overlaps(metadata, start, end):
            continue
        name = metadata.get("name")
        if name:
            archived = json_loader(SUBMISSIONS_ARCHIVE_URL.format(name=name), user_agent)
            result.extend(_records(archived, start, end))
    deduped = {row["accession"]: row for row in result}
    return sorted(deduped.values(), key=lambda row: (row["filing_date"], row["accession"]))


def _terms(change):
    values = {change.get("identity_key") or ""}
    for side in ("previous_disclosure", "current_disclosure"):
        values.update((change.get(side) or {}).get("names") or [])
    return sorted({v.strip() for v in values if v and v.strip()}, key=len, reverse=True)


def _term_pattern(term):
    tokens = re.findall(r"[a-z0-9]+", term.casefold())
    if not tokens:
        return None
    return re.compile(r"\b" + r"[^a-z0-9]+".join(map(re.escape, tokens)) + r"\b", re.I)


def relevant_passages(text, terms, *, radius=900, max_passages=8):
    matches = []
    for term in terms:
        pattern = _term_pattern(term)
        if pattern:
            matches.extend((match.start(), match.end(), term) for match in pattern.finditer(text))
    matches.sort()
    windows = []
    for start, end, term in matches:
        left = max(0, start - radius)
        right = min(len(text), end + radius)
        if windows and left <= windows[-1][1]:
            windows[-1] = (windows[-1][0], max(windows[-1][1], right), windows[-1][2] | {term})
        else:
            windows.append((left, right, {term}))
        if len(windows) >= max_passages:
            break
    return [{
        "start_char": left,
        "end_char": right,
        "matched_terms": sorted(found, key=str.casefold),
        "text": text[left:right].strip(),
    } for left, right, found in windows]


def _document_url(cik, filing):
    return DOCUMENT_URL.format(
        cik=str(int(cik)),
        accession=filing["accession"].replace("-", ""),
        document=filing["primary_document"],
    )


def _index_url(cik, filing):
    return INDEX_URL.format(
        cik=str(int(cik)), accession=filing["accession"].replace("-", "")
    )


def _relevant_exhibit_name(name):
    lower = name.casefold()
    if not lower.endswith((".htm", ".html", ".txt")):
        return False
    compact = re.sub(r"[^a-z0-9]", "", lower.rsplit(".", 1)[0])
    return bool(re.search(r"(?:ex|exhibit)(?:2|21|99)(?:\d|$)", compact))


def filing_documents(cik, filing, user_agent, *, json_loader=get_json):
    names = [filing["primary_document"]]
    try:
        index = json_loader(_index_url(cik, filing), user_agent)
    except Exception:
        index = {}
    for item in ((index.get("directory") or {}).get("item") or []):
        name = str(item.get("name") or "")
        if name and _relevant_exhibit_name(name) and name not in names:
            names.append(name)
    return [{
        "document": name,
        "document_role": "PRIMARY" if name == filing["primary_document"] else "RELEVANT_EXHIBIT",
        "document_url": DOCUMENT_URL.format(
            cik=str(int(cik)), accession=filing["accession"].replace("-", ""), document=name,
        ),
    } for name in names]


def collect(change, cik, user_agent, *, json_loader=get_json, text_loader=get_text):
    start = change["previous_filing_date"]
    end = change["current_filing_date"]
    terms = _terms(change)
    evidence = []
    inspected = []
    errors = []
    for filing in filing_metadata(cik, user_agent, start, end, json_loader=json_loader):
        for document in filing_documents(cik, filing, user_agent, json_loader=json_loader):
            try:
                text = strip_html(text_loader(document["document_url"], user_agent))
            except Exception as exc:
                errors.append({
                    "accession": filing["accession"],
                    "document": document["document"],
                    "document_url": document["document_url"],
                    "error": f"{type(exc).__name__}: {exc}",
                })
                continue
            passages = relevant_passages(text, terms)
            inspected.append({
                **filing, **document, "passage_count": len(passages),
            })
            for passage in passages:
                raw_id = "|".join([
                    filing["accession"], document["document"],
                    str(passage["start_char"]), str(passage["end_char"]),
                    change["identity_key"],
                ])
                evidence.append({
                    "evidence_id": "secpass:" + hashlib.sha256(raw_id.encode()).hexdigest()[:20],
                    "accession": filing["accession"],
                    "filing_date": filing["filing_date"],
                    "form": filing["form"],
                    "items": filing.get("items") or "",
                    "document": document["document"],
                    "document_role": document["document_role"],
                    "source_url": document["document_url"],
                    **passage,
                })
    packet = build_structure_change_packet(change, evidence)
    packet["collection"] = {
        "cik": str(int(cik)).zfill(10),
        "window_start": start,
        "window_end": end,
        "search_terms": terms,
        "documents_inspected": inspected,
        "documents_inspected_count": len(inspected),
        "evidence_passage_count": len(evidence),
        "collection_errors": errors,
        "collection_error_count": len(errors),
    }
    return packet


def select_change(changes, identity_key, previous_date=None):
    matches = [
        change for change in changes.get("changes", [])
        if change.get("identity_key") == identity_key
        and (previous_date is None or change.get("previous_filing_date") == previous_date)
    ]
    if not matches:
        raise ValueError(f"No disclosure change found for {identity_key!r}")
    if len(matches) > 1:
        dates = ", ".join(change["previous_filing_date"] for change in matches)
        raise ValueError(f"Multiple changes found; pass --previous-date from: {dates}")
    return matches[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--changes", required=True)
    parser.add_argument("--identity-key", required=True)
    parser.add_argument("--previous-date")
    parser.add_argument("--cik")
    parser.add_argument("--user-agent", default=os.environ.get("SEC_USER_AGENT"))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    if not args.user_agent:
        raise SystemExit("Set SEC_USER_AGENT or pass --user-agent")
    changes = json.loads(Path(args.changes).read_text(encoding="utf-8"))
    change = select_change(changes, args.identity_key, args.previous_date)
    cik = args.cik or changes.get("cik")
    if not cik:
        raise SystemExit("CIK missing from changes file; pass --cik")
    packet = collect(change, cik, args.user_agent)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(packet, indent=2, ensure_ascii=False), encoding="utf-8")
    collection = packet["collection"]
    print(
        f"Wrote evidence packet: {collection['documents_inspected_count']} documents inspected, "
        f"{collection['evidence_passage_count']} passages -> {out}"
    )
    if collection["collection_error_count"]:
        print(f"Collection warnings: {collection['collection_error_count']} document(s) failed")
    print("No corporate event was inferred; packet status remains PENDING.")


if __name__ == "__main__":
    main()
