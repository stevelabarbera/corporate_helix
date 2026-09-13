#!/usr/bin/env python3
from __future__ import annotations
import re
from typing import Any, Iterable

LOCATOR_VERSION = "EDGAR_LONGFORM_MA_V1"

_SIGNAL_PATTERNS = (
    ("ACQUIRE", re.compile(r"\bacquir(?:e|ed|es|ing)\b", re.I)),
    ("ACQUISITION", re.compile(r"\bacquisition(?:s)?\b", re.I)),
    ("BUSINESS_COMBINATION", re.compile(r"\bbusiness combinations?\b", re.I)),
    ("MERGER", re.compile(r"\bmerg(?:er|ers|ed|ing)\b", re.I)),
    ("PURCHASE_PRICE", re.compile(r"\bpurchase price(?: allocation)?\b", re.I)),
    ("DIVESTITURE", re.compile(r"\bdivest(?:ed|iture|itures|ing|ment|ments)?\b", re.I)),
    ("SALE", re.compile(r"\b(?:completed|completion of|entered into)\b.{0,80}\bsale of\b", re.I)),
    ("SOLD", re.compile(r"\bsold\b", re.I)),
)

def _find_hits(text: str) -> list[dict[str, Any]]:
    hits = []
    for kind, pattern in _SIGNAL_PATTERNS:
        for m in pattern.finditer(text):
            hits.append({"kind": kind, "term": m.group(0), "start": m.start(), "end": m.end()})
    return sorted(hits, key=lambda h: (h["start"], h["end"], h["kind"]))

def _merge_windows(windows: Iterable[tuple[int, int]], merge_gap_chars: int) -> list[tuple[int, int]]:
    ordered = sorted(windows)
    if not ordered:
        return []
    merged = [[ordered[0][0], ordered[0][1]]]
    for start, end in ordered[1:]:
        prev = merged[-1]
        if start <= prev[1] + merge_gap_chars:
            prev[1] = max(prev[1], end)
        else:
            merged.append([start, end])
    return [(a, b) for a, b in merged]

def _split_large_region(start: int, end: int, max_region_chars: int, split_overlap_chars: int) -> list[tuple[int, int]]:
    if end - start <= max_region_chars:
        return [(start, end)]
    out = []
    cursor = start
    step = max(1, max_region_chars - split_overlap_chars)
    while cursor < end:
        chunk_end = min(end, cursor + max_region_chars)
        out.append((cursor, chunk_end))
        if chunk_end >= end:
            break
        cursor += step
    return out

def locate_ma_regions(
    text: str,
    *,
    form: str,
    before_chars: int = 1400,
    after_chars: int = 1800,
    merge_gap_chars: int = 250,
    max_region_chars: int = 12000,
    split_overlap_chars: int = 500,
) -> list[dict[str, Any]]:
    """Locate candidate M&A regions without asserting that an event occurred."""
    if not text:
        return []
    hits = _find_hits(text)
    if not hits:
        return []
    windows = [
        (max(0, h["start"] - before_chars), min(len(text), h["end"] + after_chars))
        for h in hits
    ]
    merged = _merge_windows(windows, merge_gap_chars)
    regions = []
    region_number = 0
    for merged_start, merged_end in merged:
        for start, end in _split_large_region(merged_start, merged_end, max_region_chars, split_overlap_chars):
            region_hits = [h for h in hits if h["start"] < end and h["end"] > start]
            if not region_hits:
                continue
            region_number += 1
            regions.append({
                "item": "LONGFORM_MA_CANDIDATE",
                "kind": "LONGFORM_MA_CANDIDATE",
                "form": form,
                "text": text[start:end],
                "start_char": start,
                "end_char": end,
                "locator_version": LOCATOR_VERSION,
                "locator_terms": sorted({h["kind"] for h in region_hits}),
                "locator_hits": region_hits,
                "region_number": region_number,
            })
    return regions
