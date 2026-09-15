# CONTEXT ADDENDUM — GLEIF Gazetteer Entity-Detection Backend

**Date:** 2026-09-15

Part of the EDGAR M&A historical context. Keep alongside
`CONTEXT_EVENT_EXTRACTION.md`, `CONTEXT_EVENT_EXTRACTION_HARDENING.md`,
`CONTEXT_EVENT_EXTRACTION_SIX_FLAGS.md`, and
`CONTEXT_EVENT_EXTRACTION_PARAMOUNT.md`.

## Why this exists

Six Flags and Paramount, tested back to back, surfaced three separate
regex/pattern-brittleness bugs in one sitting: a missing suffix (L.P.), a
missing verb tense, a hardcoded agreement-name phrase, and — the most
consequential one — a registrant name with no corporate suffix at all
("Paramount Global"). Every one of these was a real company, not a
hypothetical edge case, and every fix was "notice the specific gap, patch
the specific pattern." That approach doesn't scale; the next untested
company will find its own new gap the same way.

The alternative: instead of asking "does this text match a pattern that
usually surrounds a company name," ask "is this text a name we already
know is real" — checked directly against the local GLEIF LEI index
(`gleif_lei.sqlite`, 3.39M records, already built and already the
project's canonical identity source for the GLEIF ingestion work
([[gleif-ingestion]])). An exact match against a real registered legal
name needs no suffix heuristic, no verb-tense pattern, nothing about how
the surrounding sentence is phrased.

## What was built

`code/parsers/gleif_gazetteer_backend.py` — `GazetteerBackend`, matching
the same `name`/`parse(text) -> {"orgs": [...], "aliases": {...}}`
interface as `RegexBackend`/`SpacyBackend`/`LegalRulesBackend`, so it plugs
directly into the existing `fuse()` voting architecture as a fourth
backend rather than requiring any pipeline restructuring.

- **Matching**: an Aho-Corasick automaton (`pyahocorasick`) built once
  over every `legal_name` in `lei_entities`, keyed by its
  `legal_name_normalized` (casefolded) form, so a single pass over a
  filing's text finds every gazetteer hit in O(text length) regardless of
  how many millions of names are in the index.
- **Word-boundary filtering**: a raw Aho-Corasick match doesn't respect
  word boundaries ("Ford" inside "Fordham" would otherwise fire) --
  filtered by checking the characters immediately before/after each match
  aren't alphanumeric.
- **Overlap resolution**: when multiple real GLEIF entries could both
  match overlapping spans of the same mention (e.g. a hypothetical "Six
  Flags" entry and "Six Flags Entertainment Corporation" both matching the
  same text), a longest-match-wins sweep keeps only the longer, more
  specific match -- the same principle as maximal-munch tokenization.
- **Original casing preserved**: the emitted entity string is sliced from
  the filing's own original text, not the casefolded match or GLEIF's
  stored form -- what the filing actually said is the ground truth for
  what gets reported.
- **`bad_org()` reuse**: the same generic-term filter the other backends
  already rely on (rejects "the Company"/"Corporation" alone) applies here
  too, since GLEIF source data isn't guaranteed clean.
- **Caching**: the automaton is cached per `(path, mtime)` at module level,
  so constructing `EdgarMAExtractor(gazetteer_db_path=...)` repeatedly
  within one process (e.g. once per filing in a batch run) doesn't rebuild
  a multi-million-entry automaton every time.
- **DRY refactor along the way**: the alias-tail-parsing regex (recognizing
  `X, a Delaware corporation ("Alias")`-style parenthetical short names)
  was duplicated three times across the existing backends. Extracted into
  one shared `_aliases_from_tail()` helper, used by all four backends now.
  Verified this refactor alone changed no test outcomes before adding
  anything new.

## Wiring into EdgarMAExtractor

Opt-in only: `EdgarMAExtractor(gazetteer_db_path="path/to/gleif_lei.sqlite")`.
With no `gazetteer_db_path`, behavior is byte-for-byte identical to before
-- the import of `pyahocorasick`/`GazetteerBackend` is local to that branch,
so the base validated ensemble doesn't even need the package installed.
An explicit request that then fails (missing package, missing/corrupt db
file) raises immediately rather than silently running without it -- same
no-silent-degradation principle as the spaCy-load guard already in place.

Weighted at 1.5 (`GAZETTEER_WEIGHT`), matching the default fusion
threshold exactly -- a solo gazetteer hit is sufficient to establish an
org on its own, the same way spaCy+regex or spaCy+legal_rules already can
combine to clear it. Rationale: an exact match against a real registry
entry is categorically stronger evidence than a suffix/pattern heuristic --
it's identity against a canonical source, not similarity -- so requiring
corroboration from a weaker signal to trust it would be backwards.

**Deliberately NOT added to `VALIDATED_WEIGHTS` / the default 3-backend
ensemble yet.** It's a new capability, not a replacement for an existing
validated one, and the project's own rule for exactly this situation
("validated regex + spacy + legal_rules mode is required by default") is
that a new algorithm earns default status by going through the same real-
filing-text validation the original three did -- not by being additive
and probably-helpful.

## What's tested here vs. what still needs real validation

`tests/test_gleif_gazetteer_backend.py` (8 tests, all passing) covers the
matching *logic* only, using a synthetic fixture SQLite with a handful of
made-up rows (same schema and construction pattern as
`tests/test_gleif_identity_fallback_provider.py`'s existing fixture
convention) -- not real GLEIF data. This proves: suffix-less names match
correctly (the literal Paramount Global case, reproduced standalone),
word-boundary filtering works, overlap resolution picks the longer match,
generic terms get filtered, a missing db raises clearly, the automaton
caches correctly, and — end-to-end — `EdgarMAExtractor(gazetteer_db_path=...)`
actually resolves a suffix-less name through the real fusion path, not
just in the backend's isolated output.

None of this validates real-world coverage or false-positive rate against
the actual 3.39M-row index, which doesn't exist in this environment (a
local build artifact, correctly not committed to git given its size).
That validation is a "run it locally when ready" step, not something this
pass could do. Before folding it into the default ensemble, that pass
should answer:

1. **False-positive rate on real filing text.** Does the automaton fire on
   things that look like company names but aren't real M&A parties (e.g.
   a law firm name, a bank named as an underwriter, an unrelated company
   mentioned only in a risk-factor boilerplate paragraph)? The existing
   `financing`-guard and downstream event-inference logic only fires on
   orgs that participate in a recognized event pattern, which should
   filter most of this out naturally -- but worth confirming against real
   text, not assuming.
2. **Coverage against the existing gold/raw fixtures.** Re-run
   `run_coverage_eval.py` with `gazetteer_db_path` set for Lumen, Disney,
   Tenable, Six Flags, and Paramount -- does it change any scores (better
   or worse), and does it produce results consistent with what the
   suffix/legal-form/spaCy path already found for the cases that already
   work?
3. **Automaton build time and memory against the real 3.39M-row index** --
   this pass could only measure against a handful of synthetic rows.
4. **Multiple LEIs sharing a normalized legal name** (re-registrations,
   name reuse) -- the current implementation keeps whichever row SQLite
   returns first and discards the rest, since this backend only answers
   "is this a real name," not "which specific LEI." Worth confirming real
   GLEIF data doesn't make that ambiguity matter for anything downstream.

## How to resume

```bash
python3 -m pytest tests/                                    # confirm 221/221
pip install pyahocorasick                                    # or [gazetteer] extra
python3 -c "
from parsers.edgar_ma_extractor import EdgarMAExtractor
ex = EdgarMAExtractor(gazetteer_db_path='data/processed/gleif_lei.sqlite')
print(ex.mode)
"
```
Then re-run `run_coverage_eval.py` with the gazetteer wired in against the
real filing-text fixtures already on disk, and see what changes.
