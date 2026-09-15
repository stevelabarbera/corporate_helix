#!/usr/bin/env python3
"""
Gazetteer entity-detection backend for the EDGAR M&A extraction ensemble.

Every existing backend (RegexBackend, SpacyBackend, LegalRulesBackend)
detects a candidate entity by recognizing a PATTERN around its name --
a corporate suffix, a legal-form clause, spaCy's NER model. Real filing
text keeps finding patterns none of them anticipated (Six Flags' L.P.
suffix, Paramount's suffix-less "Paramount Global", differently-worded
agreement names). Every one of those was a real company we'd never seen
before, not a hypothetical.

This backend takes a fundamentally different approach: instead of
recognizing a *pattern*, it checks whether a span of text is a name we
already know is real, by matching directly against the local GLEIF LEI
index (`code/build_gleif_lei_index.py`'s `gleif_lei.sqlite`) -- the same
canonical-identity source Corporation Helix already uses everywhere else.
A real, already-registered legal entity name needs no suffix heuristic at
all here; it either is or isn't a legal_name in the index.

This does NOT replace the pattern-based backends. GLEIF's daily snapshot
can't contain an entity formed days before a filing (a brand-new merger
sub, a shell created solely to effect a transaction), or anything that's
fallen out of the local index since the last rebuild. The pattern-based
backends remain the fallback for exactly that case. This is corroborating
evidence for the common case, not a replacement for the tail case --
consistent with the project's own rule that string similarity alone never
proves identity: an exact match against a real registry entry is stronger
evidence than a suffix heuristic, but it is still one signal among several
in the fusion vote, not an automatic accept.

NOT part of the validated default ensemble (EdgarMAExtractor.VALIDATED_*)
yet. Wire it in explicitly via `gazetteer_db_path=` when constructing
EdgarMAExtractor. It needs to go through the same real-filing-text
validation the other three backends did (coverage_harness, real gold/raw
fixtures) before folding it into the default -- see
CONTEXT_EVENT_EXTRACTION_GAZETTEER.md for what that validation pass should
cover.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

try:
    import ahocorasick
except ImportError as _exc:  # pragma: no cover - exercised via ImportError path
    ahocorasick = None
    _AHOCORASICK_IMPORT_ERROR = _exc
else:
    _AHOCORASICK_IMPORT_ERROR = None

from parsers.edgar_ma_extractor import _aliases_from_tail, bad_org, norm

# A name this short (after casefolding) is far more likely to be bad GLEIF
# source data (a placeholder, an initialism collision) than a genuine,
# safely-matchable company name in free-running prose -- matching short
# strings in unstructured text produces disproportionate false positives
# regardless of source-data quality. Real registrant names in the filings
# tested so far ("3M", "CVS") are the shortest realistic case; this stays
# permissive enough for those while excluding single/double-letter noise.
_MIN_NAME_LENGTH = 3

_AUTOMATON_CACHE: dict[tuple[str, float], "ahocorasick.Automaton"] = {}
_AUTOMATON_CACHE_LOCK = threading.Lock()


def _is_word_char(ch: str | None) -> bool:
    return ch is not None and (ch.isalnum() or ch == "&")


def build_automaton(db_path: str | Path) -> "ahocorasick.Automaton":
    """
    Build (or return a cached) Aho-Corasick automaton over every
    legal_name in the GLEIF LEI index, keyed by its casefolded form so
    matching is case-insensitive without needing per-lookup casefolding.

    Cached per (path, mtime) so repeated EdgarMAExtractor construction
    within one process -- e.g. once per filing in a batch run -- doesn't
    rebuild a multi-million-entry automaton every time. The real index is
    a build artifact that only changes on an explicit rebuild, so mtime is
    a reliable cache-invalidation key here.
    """
    if ahocorasick is None:
        raise RuntimeError(
            "GazetteerBackend requires the 'pyahocorasick' package "
            "(pip install pyahocorasick)."
        ) from _AHOCORASICK_IMPORT_ERROR

    path = Path(db_path)
    if not path.is_file():
        raise FileNotFoundError(
            f"GLEIF LEI index not found at {path}. Build it first with "
            "code/build_gleif_lei_index.py."
        )

    cache_key = (str(path.resolve()), path.stat().st_mtime)
    with _AUTOMATON_CACHE_LOCK:
        cached = _AUTOMATON_CACHE.get(cache_key)
        if cached is not None:
            return cached

    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        automaton = ahocorasick.Automaton()
        rows = conn.execute(
            "SELECT legal_name, legal_name_normalized, lei FROM lei_entities "
            "WHERE legal_name IS NOT NULL AND legal_name_normalized IS NOT NULL"
        )
        seen_keys = set()
        for legal_name, legal_name_normalized, lei in rows:
            key = legal_name_normalized
            if len(key) < _MIN_NAME_LENGTH:
                continue
            if key in seen_keys:
                # Multiple LEIs can share a normalized legal name (rare,
                # but real -- e.g. re-registrations). First one wins; this
                # backend answers "is this a real name", not "which LEI".
                continue
            seen_keys.add(key)
            automaton.add_word(key, (legal_name, lei))
        automaton.make_automaton()
    finally:
        conn.close()

    with _AUTOMATON_CACHE_LOCK:
        _AUTOMATON_CACHE[cache_key] = automaton
    return automaton


class GazetteerBackend:
    """
    Matches text directly against the local GLEIF LEI index rather than a
    suffix/legal-form/NER pattern. See module docstring for why this is a
    corroborating backend, not a replacement.
    """

    name = "gazetteer"

    def __init__(self, db_path: str | Path):
        self.db_path = db_path
        self.automaton = build_automaton(db_path)

    def parse(self, text: str) -> dict:
        low = text.casefold()
        orgs, aliases = [], {}

        candidates: list[tuple[int, int, str]] = []  # (start, end_inclusive, legal_name)
        for end_idx, (legal_name, lei) in self.automaton.iter(low):
            start_idx = end_idx - len(legal_name) + 1
            before = low[start_idx - 1] if start_idx > 0 else None
            after = low[end_idx + 1] if end_idx + 1 < len(low) else None
            if _is_word_char(before) or _is_word_char(after):
                continue  # mid-word match, e.g. "Ford" inside "Fordham"
            candidates.append((start_idx, end_idx, legal_name))

        # Longest match wins wherever spans overlap -- e.g. "Six Flags"
        # and "Six Flags Entertainment Corporation" can both be real GLEIF
        # entries and both match the same mention; only the longer, more
        # specific one should survive. Sorting longest-first and skipping
        # any candidate whose span overlaps an already-accepted one is a
        # standard maximal-munch sweep.
        candidates.sort(key=lambda c: c[1] - c[0], reverse=True)
        accepted: list[tuple[int, int, str]] = []
        for start_idx, end_idx, legal_name in candidates:
            if any(not (end_idx < a_start or start_idx > a_end) for a_start, a_end, _ in accepted):
                continue
            accepted.append((start_idx, end_idx, legal_name))

        for start_idx, end_idx, _ in accepted:
            # Use the ORIGINAL text's casing for the emitted entity name,
            # not the casefolded match or the GLEIF-stored form -- a
            # filing's own capitalization is the ground truth for what
            # the extractor should report as "the text said".
            ent = norm(text[start_idx:end_idx + 1])
            if bad_org(ent):
                continue
            orgs.append(ent)
            for a in _aliases_from_tail(text, end_idx + 1):
                aliases[norm(a)] = ent

        return {"orgs": sorted(set(orgs)), "aliases": aliases}
