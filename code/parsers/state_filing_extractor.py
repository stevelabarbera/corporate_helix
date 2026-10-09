#!/usr/bin/env python3
"""
State-level Certificate of Merger extraction.

Why this exists
----------------
EDGAR and GLEIF both depend on the transaction already having surfaced in a
federal securities filing or a reported LEI relationship. A Delaware (or
other state) Certificate of Merger is filed with the Secretary of State at
the moment a merger becomes legally effective -- which, for a public-company
deal, is very often the SAME closing event an 8-K Item 2.01 reports days
later, and for a private-to-private deal (see the Dokobit/Signicat gap
documented in CORPORATION_HELIX_CONTEXT.md) may be the ONLY structured
record that ever exists at all, since there is no SEC filer on either side
and GLEIF Level 2 relationship reporting is not mandatory outside the
derivatives regime.

Per the project's architectural rule (see parsers/whois_parser.py's own
docstring for the canonical statement): Helix does not actively go out
and fetch evidence itself, even a lightweight lookup. It only parses
whatever the user or an upstream tool hands over -- the same boundary
whois_parser.py applies to `whois example.com` output and
ingest_supplied_evidence.py applies to ASM-supplied observations. This
module never retrieves a filing itself; it parses whatever certificate
text is already in hand, the same way edgar_ma_extractor.py parses
8-K/10-K text that fetch_ma_filings() already retrieved.

(Note: ingest_supplied_evidence.py's own docstring cites "CORPORATION_
HELIX_CONTEXT.md sec 34.3" for this rule -- that section is actually the
12-company saturation probe order, not the architectural boundary, as of
this file's writing. Pre-existing stale cross-reference, not touched
here; flagging rather than silently propagating it into a second file.)

Document shape
---------------
Delaware Certificates of Merger filed under DGCL Sec. 251/252/253 are
short, heavily boilerplate, numbered-paragraph documents -- not free
narrative prose like a 10-K. Confirmed against two real filed examples
(Axion Acquisition Corp./Axion International, 2008; Allis-Chalmers
Energy Inc./Wellco Sub Company, 2011), both pulled from their SEC 8-K
exhibits:

    FIRST:  names the constituent corporations and their jurisdictions
            ("... is a corporation of the State of Delaware").
    SECOND: "[Merging Corp] will merge with and into [Surviving Corp]"
            (or "shall be merged with and into").
    THIRD:  "The name of the surviving corporation is [Surviving Corp]."
    [...]   DGCL authority clause: "Section 251 of the General
            Corporation Law of the State of Delaware."
    [...]   Effective-time clause: "shall become effective at the time
            this Certificate of Merger is filed with the Secretary of
            State" OR an explicit later date/time.
    Signature block with an execution date.

A different state's certificate will phrase this differently (this
extractor is Delaware-shaped first because Delaware is both the most
common jurisdiction by far and the only one with worked real-filing
examples validated here) -- extending to another state's format is a
new pattern set, not a change to this one, same as the EDGAR foreign-
entity "under the laws of" pattern was additive rather than a rewrite.

This is a structured-field extractor, not an ensemble: unlike 10-K/8-K
prose, a Certificate of Merger's numbered-paragraph structure is fixed
by statute, so a single well-anchored pattern set is appropriate here in
a way it was never appropriate for edgar_ma_extractor.py's free text.
"""
from __future__ import annotations

import re
from typing import Any

DGCL_SECTION_RE = re.compile(
    r"Section\s+(\d{3}[A-Za-z]?)\s+of\s+the\s+"
    r"(?:General\s+Corporation\s+Law\s+of\s+the\s+State\s+of\s+Delaware|"
    r"Delaware\s+General\s+Corporation\s+Law)",
    re.I,
)

# "[X] will merge with and into [Y]" / "[X] shall be merged with and into [Y]"
# Mirrors edgar_ma_extractor.py's MERGED_WITH_INTO grammar deliberately --
# same real-world relationship, same predicate, different source document.
#
# Both name captures are bounded by a lookahead for end-of-line, not by a
# consumed punctuation terminal. A consumed terminal like `[.,;]` is
# ambiguous here because "." is also a legitimate character WITHIN the
# capture itself (corporate suffixes: "Inc.", "Corp.") -- the regex engine
# always resolves that ambiguity by leaving the trailing period for the
# terminal rather than the name, silently truncating "Northgate Holdings,
# Inc." down to "Northgate Holdings, Inc". Bounding by line-end instead
# sidesteps the ambiguity entirely since newline is never a valid name
# character to begin with.
_NAME_CHARS = r"[A-Za-z0-9&.,'’ -]"
# Lazy: bounded by a required literal that follows (" will"/" shall"), so
# no punctuation-ambiguity risk -- \s+ immediately after the capture forces
# inclusion of a trailing abbreviation period when one is actually present
# ("...Inc." followed by " will" can only match if the period is captured,
# since \s+ cannot match a literal period itself).
_NAME_LAZY = r"[A-Z]" + _NAME_CHARS + r"{1,120}?"
# A name capture with no hard literal terminal (the object of "...merge
# with and into X", or the name in "the surviving corporation is X") has
# to be bounded by a lookahead instead. Real filings end that clause one
# of two ways: a line break, or an inline jurisdiction clause tacked
# straight onto the same sentence ("X, a Delaware corporation" --
# confirmed against a real filing where the naming and jurisdiction
# clauses are merged into one sentence rather than split into separate
# numbered paragraphs the way the two original reference filings do it).
# A single greedy-plus-line-end lookahead missed this: it has no reason
# to stop before "a Delaware corporation" since every character in that
# clause is itself a valid name character, so it swallowed the whole
# trailing clause into the captured name. Using a LAZY capture with both
# terminals offered in one lookahead fixes this the same way the EDGAR
# extractor's lazy matching naturally prefers the shortest valid parse --
# it stops at whichever terminal comes first, rather than always eating
# to the last one.
_NAME_LAZY_BOUNDED = r"[A-Z]" + _NAME_CHARS + r"{1,120}?"
_CLAUSE_END = r"(?=,\s+an?\s|\s*(?:\n|$))"

MERGE_CLAUSE_RE = re.compile(
    rf"\b({_NAME_LAZY})\s+(?:will|shall)\s+(?:be\s+)?merge(?:d)?\s+with\s+and\s+into\s+({_NAME_LAZY_BOUNDED}){_CLAUSE_END}",
    re.I,
)

SURVIVOR_NAMED_RE = re.compile(
    rf"name\s+of\s+the\s+surviving\s+corporation\s+is\s+({_NAME_LAZY_BOUNDED}){_CLAUSE_END}",
    re.I,
)

# Jurisdiction clause for a constituent: "[X], a corporation of the State
# of [Y]" or "[X], a Delaware corporation" -- both real-filing forms.
# Anchored to start right after "is " (first-named constituent) or "and "
# (each subsequent one in the FIRST-paragraph list) -- without this anchor,
# the lazy name capture's lowercase-and-space-tolerant character class is
# happy to swallow the whole preceding clause ("The name of each
# constituent corporation is Meridian...") since every character in it is
# individually a valid name character. Grounding the start where these
# documents actually introduce each constituent avoids relying on
# excluding specific connector words one at a time.
JURISDICTION_RE = re.compile(
    r"(?:\bis\s+|\band\s+)([A-Z][A-Za-z0-9&.,'’ -]{1,120}?),\s+a\s+"
    r"(?:corporation\s+of\s+the\s+State\s+of\s+([A-Z][a-z]+)|"
    r"([A-Z][a-z]+)\s+corporation)",
)

# Effective time: either immediate-on-filing, or an explicit later date/time
# DGCL Sec. 103(d) permits. Captures the explicit date when present so an
# effective_date distinct from the execution/filing date is never silently
# dropped.
EFFECTIVE_IMMEDIATE_RE = re.compile(
    r"shall\s+become\s+effective\s+(?:at\s+the\s+time|upon|forthwith\s+upon)\s+"
    r"(?:this\s+Certificate\s+of\s+Merger\s+is\s+filed|the\s+filing)",
    re.I,
)
EFFECTIVE_EXPLICIT_RE = re.compile(
    r"shall\s+become\s+effective\s+(?:on|at)\s+"
    r"([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})(?:\s+at\s+([\d:]+\s*[ap]\.?m\.?))?",
    re.I,
)

EXECUTED_RE = re.compile(
    r"executed\s+(?:on\s+)?(?:this\s+)?"
    r"(?:(\d{1,2})(?:st|nd|rd|th)?\s+day\s+of\s+([A-Z][a-z]+),?\s+(\d{4})"
    r"|([A-Z][a-z]+\s+\d{1,2},?\s+\d{4}))",
    re.I,
)

_FILING_STAMP_RE = re.compile(
    r"State\s+of\s+Delaware[^\n]{0,80}?Secretary\s+of\s+State[^\n]{0,200}?"
    r"(\d{1,2}/\d{1,2}/\d{4}|\d{1,2}:\d{2}\s*[AP]M)",
    re.I,
)


def _clean(s: str | None) -> str | None:
    if s is None:
        return None
    return re.sub(r"\s+", " ", s).strip(" ,;")


def _dewrap(text: str) -> str:
    """
    Join ordinary line-wrapping within a paragraph into spaces, while
    preserving blank-line paragraph breaks -- same distinction
    edgar_ma_extractor.py's _JOIN makes for the same reason (confirmed
    there against a real Ford 10-K where an unjoined line break let a
    section header bleed into an entity name). Applied once as a
    preprocessing pass here, rather than built into every pattern below,
    since this extractor matches structured fields rather than one shared
    entity grammar.
    """
    return re.sub(r"\n(?!\s*\n)", " ", text)


def extract_certificate_of_merger(text: str, *, jurisdiction: str = "Delaware") -> dict[str, Any] | None:
    """
    Parse one Certificate of Merger's text into structured fields.

    Returns None if the text doesn't look like a Certificate of Merger at
    all (no DGCL section cite AND no merge clause found) -- callers should
    treat that as "not this document type", not as a failed extraction of
    one that is. Partial extraction (e.g. merge clause found but no
    explicit effective date) is still returned; missing fields are None,
    same convention as edgar_resolver.py's _rv() default handling.
    """
    text = _dewrap(text)
    dgcl_match = DGCL_SECTION_RE.search(text)
    merge_match = MERGE_CLAUSE_RE.search(text)
    if not dgcl_match and not merge_match:
        return None

    surviving = None
    merging = None
    if merge_match:
        merging = _clean(merge_match.group(1))
        surviving = _clean(merge_match.group(2))

    survivor_named = SURVIVOR_NAMED_RE.search(text)
    if survivor_named:
        # The THIRD-paragraph naming clause is the more authoritative
        # source for the surviving corporation's exact legal name -- the
        # merge-clause capture can pick up trailing boilerplate the named
        # clause doesn't. Prefer it when both are present and disagree.
        named = _clean(survivor_named.group(1))
        if named:
            surviving = named

    jurisdictions: dict[str, str] = {}
    for jm in JURISDICTION_RE.finditer(text):
        name = _clean(jm.group(1))
        juris = jm.group(2) or jm.group(3)
        if name and juris:
            jurisdictions[name] = juris

    effective_date = None
    effective_time = None
    effective_basis = None
    explicit = EFFECTIVE_EXPLICIT_RE.search(text)
    if explicit:
        effective_date = _clean(explicit.group(1))
        effective_time = _clean(explicit.group(2))
        effective_basis = "EXPLICIT_DATE"
    elif EFFECTIVE_IMMEDIATE_RE.search(text):
        effective_basis = "EFFECTIVE_ON_FILING"

    executed_date = None
    ex = EXECUTED_RE.search(text)
    if ex:
        if ex.group(4):
            executed_date = _clean(ex.group(4))
        elif ex.group(1) and ex.group(2) and ex.group(3):
            executed_date = _clean(f"{ex.group(2)} {ex.group(1)}, {ex.group(3)}")

    filing_stamp = None
    fs = _FILING_STAMP_RE.search(text)
    if fs:
        filing_stamp = _clean(fs.group(0))

    return {
        "document_type": "CERTIFICATE_OF_MERGER",
        "jurisdiction": jurisdiction,
        "dgcl_section": dgcl_match.group(1) if dgcl_match else None,
        "surviving_entity": surviving,
        "merging_entity": merging,
        "constituent_jurisdictions": jurisdictions or None,
        # EFFECTIVE_ON_FILING means the merger's legal effective date is
        # whatever date the certificate was actually recorded by the
        # Secretary of State -- NOT necessarily the execution/signature
        # date above. Real filings routinely execute a certificate days
        # before submitting it for filing. When no filing stamp is present
        # in the supplied text (common -- EDGAR 8-K exhibit copies often
        # omit the state's own stamp), effective_date is left None rather
        # than guessing it equals executed_date; a caller that wants a
        # best-effort date should fall back to executed_date explicitly
        # and record that it did, not get a silently substituted value.
        "effective_date": effective_date,
        "effective_time": effective_time,
        "effective_basis": effective_basis,
        "executed_date": executed_date,
        "filing_stamp_raw": filing_stamp,
    }
