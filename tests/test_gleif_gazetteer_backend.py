#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from parsers.gleif_gazetteer_backend import GazetteerBackend, build_automaton


def _make_gleif_db(tmp: Path, entities: list[tuple[str, str]]) -> str:
    """
    entities: list of (legal_name, lei) pairs. Builds a fake index with the
    same schema as the real gleif_lei.sqlite (see
    code/build_gleif_lei_index.py) -- this is a synthetic fixture for
    testing the matching logic only; it contains no real GLEIF data and is
    not a substitute for validating against the real 3M+ row index.
    """
    db_path = tmp / "gleif_lei.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        "CREATE TABLE lei_entities (lei TEXT PRIMARY KEY, legal_name TEXT, "
        "legal_name_normalized TEXT, legal_jurisdiction TEXT, entity_status TEXT);"
    )
    conn.executemany(
        "INSERT INTO lei_entities VALUES (?,?,?,?,?)",
        [(lei, name, name.casefold(), "US", "ACTIVE") for name, lei in entities],
    )
    conn.commit()
    conn.close()
    return str(db_path)


def test_matches_a_suffix_less_registrant_name():
    # The exact real-world case that motivated this backend: "Paramount
    # Global" carries no recognizable corporate suffix at all, so the
    # suffix-based ENT regex can never see it no matter how it's tuned.
    # A gazetteer match needs no suffix heuristic -- it just needs the
    # name to be a real registrant.
    with tempfile.TemporaryDirectory() as d:
        db = _make_gleif_db(Path(d), [("Paramount Global", "LEI-PARA")])
        backend = GazetteerBackend(db)
        result = backend.parse(
            'On July 7, 2024, Paramount Global, a Delaware corporation '
            '("Paramount" or the "Company"), entered into a Transaction Agreement.'
        )
        assert "Paramount Global" in result["orgs"]
        assert result["aliases"]["Paramount"] == "Paramount Global"
        assert result["aliases"]["Company"] == "Paramount Global"


def test_does_not_match_mid_word():
    # "Ford" must not fire on "Fordham" -- word-boundary check is the
    # whole point of the before/after character test, not an afterthought.
    with tempfile.TemporaryDirectory() as d:
        db = _make_gleif_db(Path(d), [("Ford Motor Company", "LEI-FORD")])
        backend = GazetteerBackend(db)
        result = backend.parse("Fordham University announced a new program.")
        assert result["orgs"] == []


def test_matches_whole_word_correctly():
    with tempfile.TemporaryDirectory() as d:
        db = _make_gleif_db(Path(d), [("Ford Motor Company", "LEI-FORD")])
        backend = GazetteerBackend(db)
        result = backend.parse("Ford Motor Company reported quarterly earnings.")
        assert result["orgs"] == ["Ford Motor Company"]


def test_prefers_longest_match_at_a_given_position():
    # If both "Six Flags" and "Six Flags Entertainment Corporation" were
    # (hypothetically) real GLEIF entries, a mention of the full name
    # should resolve to the full name, not the shorter prefix.
    with tempfile.TemporaryDirectory() as d:
        db = _make_gleif_db(
            Path(d),
            [
                ("Six Flags", "LEI-SHORT"),
                ("Six Flags Entertainment Corporation", "LEI-LONG"),
            ],
        )
        backend = GazetteerBackend(db)
        result = backend.parse("Six Flags Entertainment Corporation filed an 8-K.")
        assert result["orgs"] == ["Six Flags Entertainment Corporation"]


def test_generic_terms_filtered_by_bad_org():
    # bad_org() already filters "the Company"/"Corporation" etc. downstream
    # -- the gazetteer backend must apply the same filter, or noisy/bad
    # source data in the real index (a legal_name value that's just
    # "Company") would flood every filing with a spurious match.
    with tempfile.TemporaryDirectory() as d:
        db = _make_gleif_db(Path(d), [("Company", "LEI-BAD")])
        backend = GazetteerBackend(db)
        result = backend.parse("The Company entered into an agreement.")
        assert result["orgs"] == []


def test_missing_db_raises_actionable_error():
    try:
        GazetteerBackend("/nonexistent/path/gleif_lei.sqlite")
        assert False, "expected FileNotFoundError"
    except FileNotFoundError as exc:
        assert "gleif_lei.sqlite" in str(exc) or "not found" in str(exc)


def test_automaton_is_cached_across_backend_instances():
    with tempfile.TemporaryDirectory() as d:
        db = _make_gleif_db(Path(d), [("Acme Telemetry, Inc.", "LEI-ACME")])
        a1 = build_automaton(db)
        a2 = build_automaton(db)
        assert a1 is a2


def test_extractor_end_to_end_with_gazetteer_enabled():
    # Integration proof: EdgarMAExtractor(gazetteer_db_path=...) actually
    # resolves a suffix-less registrant name end-to-end through the real
    # fusion/voting path, not just the backend in isolation. This is the
    # exact real gap the gazetteer backend exists to close (see
    # CONTEXT_EVENT_EXTRACTION_PARAMOUNT.md, bug #4) -- verified here
    # without ENT_LEGALFORM at all, to show the gazetteer alone is
    # sufficient corroboration once real data is present.
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "code"))
    from parsers.edgar_ma_extractor import EdgarMAExtractor

    with tempfile.TemporaryDirectory() as d:
        db = _make_gleif_db(
            Path(d),
            [
                ("Paramount Global", "LEI-PARA"),
                ("Skydance Media, LLC", "LEI-SKY"),
            ],
        )
        extractor = EdgarMAExtractor(gazetteer_db_path=db)
        assert "GAZETTEER" in extractor.mode
        result = extractor.parse_section(
            'On July 7, 2024, Paramount Global, a Delaware corporation '
            '("Paramount" or the "Company"), entered into a Transaction '
            'Agreement (the "Transaction Agreement") with Skydance Media, '
            'LLC, a California limited liability company ("Skydance").',
            "1.01",
        )
        assert "Paramount Global" in result["fused"]["orgs"]
        assert "Skydance Media, LLC" in result["fused"]["orgs"]
