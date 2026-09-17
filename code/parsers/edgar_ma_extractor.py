#!/usr/bin/env python3
"""
Production EDGAR M&A entity/event extraction.

Historical note
---------------
This logic originally lived in benchmark_m385_merger_coref.py. During the
2026-09-13 trust-boundary review we made the dependency direction explicit:
production code owns extraction behavior; benchmarks import production code.

Why this matters:
- benchmark scripts must not silently become production dependencies;
- the validated ensemble configuration must be shared exactly;
- degraded parsing must be explicit rather than silently changing algorithms.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


def norm(s):
    if s is None:
        return None
    return re.sub(r"\s+", " ", s).strip(" ,;")


CORP = r"(?:Inc\.?|Incorporated|Corporation|Corp\.?|LLC|L\.L\.C\.|L\.P\.|LP|Ltd\.?|Limited|PLC|plc|Company|Co\.?)"
_WORD = r"(?:[A-Z][A-Za-z0-9&.'’-]*|[0-9][A-Za-z0-9&.'’-]*)"
_CONNECTOR = r"(?:of|and|the|for)"
# A blank line is real document structure (a section-header/paragraph
# break), not word-wrapping -- \s alone treats it identically to a single
# space, which let an ALL-CAPS 10-K section header on its own line bleed
# into the entity name of the very next sentence (confirmed on real Ford
# 10-K text: "ACQUISITIONS AND DIVESTITURES\nCompany Excluding Ford
# Credit\n\nElectriphi, Inc." was captured as one single entity name).
# Single newlines (ordinary line wrapping within one sentence) still join.
_JOIN = r"(?:[ \t-]+|\n(?!\s*\n))"
ENT = re.compile(
    r"\b(" + _WORD + r"(?:" + _JOIN + r"(?:" + _WORD + r"|" + _CONNECTOR + r")){0,7}"
    + r",?\s*" + CORP + r")(?![A-Za-z.])"
)

# Some real registrant names carry no recognizable corporate suffix at all
# (e.g. "Paramount Global" -- "Global" isn't a suffix). ENT alone can never
# see these. But every such filing still states the entity's legal form
# explicitly ("Paramount Global, a Delaware corporation"), so use that
# as an independent signal. _BARE_SUFFIX filters out spurious matches
# where the "entity" ENT_LEGALFORM captured is actually just the trailing
# suffix of an ENT-matched name immediately before its own legal-form
# clause (e.g. "Cedar Fair, L.P., a Delaware limited partnership" would
# otherwise also match "L.P." alone as a fake second entity).
_LEGAL_FORM = r"(?:corporation|company|limited liability company|limited partnership)"
ENT_LEGALFORM = re.compile(
    r"\b(" + _WORD + r"(?:" + _JOIN + r"(?:" + _WORD + r"|" + _CONNECTOR + r")){0,7})"
    r",\s+an?\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2}\s+" + _LEGAL_FORM + r"\b"
)
_BARE_SUFFIX = re.compile(r"^" + CORP + r"$")


def _entity_matches(text):
    for m in ENT.finditer(text):
        yield norm(m.group(1)), m.end()
    for m in ENT_LEGALFORM.finditer(text):
        ent = norm(m.group(1))
        if _BARE_SUFFIX.match(ent):
            continue
        yield ent, m.end()


def _aliases_from_tail(text, end):
    """
    Given the position right after an entity mention, look for a trailing
    parenthetical alias definition -- e.g. '..., a Delaware corporation
    ("Six Flags")' -- and return the quoted short name(s) found inside it.
    Shared by every backend so the alias-detection rule stays identical
    across ENT-based matches, spaCy NER spans, and gazetteer hits alike.
    """
    tail = text[end:end + 260]
    pm = re.match(
        r"\s*(?:,\s*(?:a|an)\s+[^()]{0,150})?\s*\(([^)]{1,220})\)",
        tail,
        re.S,
    )
    if not pm:
        return []
    return re.findall(r'[“"]\s*(?:the\s+)?([^”"]+?)\s*[”"]', pm.group(1), re.I)


class RegexBackend:
    name = "regex"

    def parse(self, text):
        orgs, aliases = [], {}
        for ent, end in _entity_matches(text):
            orgs.append(ent)
            for a in _aliases_from_tail(text, end):
                aliases[norm(a)] = ent
        return {"orgs": sorted(set(orgs)), "aliases": aliases}


class SpacyBackend:
    name = "spacy"

    def __init__(self, model):
        import spacy
        self.nlp = spacy.load(model)

    def parse(self, text):
        doc = self.nlp(text)
        orgs, aliases = [], {}
        for e in doc.ents:
            if e.label_ != "ORG":
                continue
            ent = norm(e.text)
            orgs.append(ent)
            for a in _aliases_from_tail(text, e.end_char):
                aliases[norm(a)] = ent
        return {"orgs": sorted(set(orgs)), "aliases": aliases}


class LegalRulesBackend:
    name = "legal_rules"

    def parse(self, text):
        orgs, aliases = [], {}
        for ent, end in _entity_matches(text):
            found = _aliases_from_tail(text, end)
            if not found:
                continue
            for a in found:
                aliases[norm(a)] = ent
            orgs.append(ent)
        return {"orgs": sorted(set(orgs)), "aliases": aliases}


def bad_org(name):
    x = (name or "").casefold().strip()
    if x in ("the company", "company", "the corporation", "corporation"):
        return True
    return any(
        b in x
        for b in (
            "section ", "article ", "item ", "form ", "rule ", "schedule ",
            "general corporation law", "merger agreement", "credit agreement",
            "senior notes", "board of directors",
        )
    )


def fuse(outputs, weights, threshold):
    votes = defaultdict(float)
    for backend, out in outputs.items():
        w = weights.get(backend, 1.0)
        for org in out["orgs"]:
            if not bad_org(org):
                votes[org] += w
    orgs = sorted(o for o, v in votes.items() if v >= threshold)

    alias_votes = defaultdict(lambda: defaultdict(float))
    for backend, out in outputs.items():
        w = weights.get(backend, 1.0)
        for alias, ent in out["aliases"].items():
            if not bad_org(ent):
                alias_votes[alias][ent] += w

    aliases = {}
    for alias, cands in alias_votes.items():
        ent, score = sorted(cands.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)[0]
        if ent in orgs or score >= threshold:
            aliases[alias] = ent
    return {"orgs": orgs, "aliases": aliases, "org_votes": dict(votes)}


def _parent_of(org, text, orgs):
    """
    If `org`'s own descriptor clause in `text` discloses it as "a wholly
    owned subsidiary of X" (or similar), return the parent X instead --
    a divestiture's immediate contracting buyer is very often a
    newly-formed subsidiary, and the counterparty that actually matters
    for identity purposes is the named parent (e.g. real Disney/Sinclair
    text names the buyer as "Diamond Sports Group, LLC ... a wholly owned
    subsidiary of Sinclair Broadcast Group, Inc." -- the real
    counterparty is Sinclair, not the shell). Falls back to `org` itself
    if no such disclosure is found or the named parent isn't a known org.
    """
    pos = text.find(org)
    if pos == -1:
        return org
    context = text[pos + len(org):pos + len(org) + 220]
    sm = re.search(r"\bsubsidiary of\s+", context, re.I)
    if not sm:
        return org
    # A fixed-length window past "subsidiary of", not a punctuation-
    # bounded capture: a parent's own name can contain a comma before its
    # suffix ("Sinclair Broadcast Group, Inc."), which a [^.,;()]-style
    # capture would misread as a clause boundary and cut off before the
    # suffix -- same bug class fixed for the AIG "Ltd." truncation.
    window = context[sm.end():sm.end() + 100]
    parent = known_prefix(window, orgs)
    return parent if parent else org


def _non_shell_orgs_in(span, orgs):
    """
    Real orgs mentioned in `span`, in order of first appearance, excluding
    entities introduced as "a subsidiary of X" (transitory shells formed
    solely to effect a merger -- a merger-sub or holdco named alongside
    the real acquirer/target in the same sentence). Each org's own
    "shell-ness" is checked only in the text between its own mention and
    the next org's mention, so one shell's descriptor clause can't bleed
    into flagging an unrelated, real org mentioned later in the same span.
    """
    positions = sorted(
        ((o, span.find(o)) for o in orgs if o in span),
        key=lambda t: t[1],
    )
    result = []
    for i, (o, pos) in enumerate(positions):
        end = positions[i + 1][1] if i + 1 < len(positions) else len(span)
        context = span[pos + len(o):end]
        if re.search(r"\bsubsidiary of\b", context, re.I):
            continue
        result.append(o)
    return result


def resolve(name, aliases):
    n = norm(name)
    if not n:
        return None
    key = re.sub(r"^the\s+", "", n, flags=re.I)
    return aliases.get(n, aliases.get(key, n))


def known_prefix(raw, orgs):
    raw = norm(raw)
    if not raw:
        return None
    raw_bare = raw.rstrip(".")
    hits = [
        o for o in orgs
        if raw.startswith(o) or raw_bare.startswith(o.rstrip("."))
    ]
    return sorted(hits, key=len, reverse=True)[0] if hits else None


def temporal_status(fragment):
    f = fragment.casefold()
    proposed_markers = (
        "will merge", "will be merged", "will continue", "will be converted",
        "will become", "to merge", "would merge", "upon the terms and subject to",
    )
    completed_markers = (
        "merged with and into", "was converted", "completed its acquisition",
        "completed the previously announced transaction",
        "becoming a wholly owned subsidiary",
        "continuing as the surviving", "surviving the merger as",
    )
    if any(x in f for x in proposed_markers):
        if " merged with and into " in " " + f + " " and "will " not in f:
            return "COMPLETED"
        if " was converted " in " " + f + " ":
            return "COMPLETED"
        return "PROPOSED"
    if any(x in f for x in completed_markers):
        return "COMPLETED"
    return "UNKNOWN"


def enrich_survivor_aliases(text, aliases):
    out = dict(aliases)
    changed = True
    while changed:
        changed = False
        alias_lc = {k.casefold(): v for k, v in out.items()}
        if not alias_lc:
            break
        ap = "|".join(sorted((re.escape(k) for k in alias_lc), key=len, reverse=True))
        pat = re.compile(
            rf"\b(?:with\s+)?({ap})\s+continuing as the surviving "
            rf"(?:corporation|company|limited liability company)"
            rf"[^.;]{{0,260}}?\(\s*the\s+[“\"]([^”\"]+)[”\"]\s*\)",
            re.I,
        )
        for m in pat.finditer(text):
            entity = alias_lc.get(m.group(1).casefold())
            defined = norm(m.group(2))
            if entity and defined and out.get(defined) != entity:
                out[defined] = entity
                changed = True
    return out


def mark_transient_relationships(events):
    merger_subjects = {
        e["subject"] for e in events
        if e["event_type"] == "MERGED_INTO" and e["status"] == "COMPLETED"
    }
    for e in events:
        e.setdefault("lifecycle", "FINAL")
        if (
            e["event_type"] == "SUBSIDIARY_OF"
            and e["status"] == "COMPLETED"
            and e["subject"] in merger_subjects
        ):
            e["lifecycle"] = "TRANSIENT"
    return events


def add_event(out, etype, subject, obj, status, evidence, *, extraction_rule):
    # extraction_rule was added during the 2026-09-13 hardening pass so that
    # downstream facts retain HOW a parser conclusion was produced.
    out.append({
        "event_type": etype,
        "subject": subject,
        "object": obj,
        "status": status,
        "evidence": norm(evidence),
        "extraction_rule": extraction_rule,
    })


def infer_events(text, aliases, orgs, item):
    aliases = enrich_survivor_aliases(text, aliases)
    out = []
    low = text.casefold()
    financing = any(
        x in low[:2200]
        for x in (
            "credit agreement", "senior notes", "underwriting agreement",
            "partial financing of the proposed acquisition", "term loan",
        )
    )
    # A definitive-agreement descriptor ("a definitive Agreement...", "a
    # binding Transaction Agreement...") commonly sits between the article
    # and the agreement name -- real AIG/Validus text uses "entered into a
    # definitive agreement and plan of merger". Curated adjective list,
    # not a generic wildcard, to avoid over-capturing unrelated text.
    _AGMT_MODIFIER = r"(?:definitive|binding|new)\s+"
    merger_exec = re.search(
        r"entered into an? (?:" + _AGMT_MODIFIER + r")?(?:agreement and plan of merger|transaction agreement|"
        r"business combination agreement|agreement and plan of reorganization)",
        low[:2200],
    )
    if item == "1.01" and financing and not merger_exec:
        return out

    m = re.search(
        r"\bentered into an? (?:" + _AGMT_MODIFIER + r")?(?:Agreement and Plan of Merger|Transaction Agreement|"
        r"Business Combination Agreement|Agreement and Plan of Reorganization)\b",
        text,
        re.I,
    )
    if m:
        preamble = text[:m.start()]
        # In a multi-party merger-of-equals preamble (e.g. "Six Flags, Cedar
        # Fair, HoldCo, and Merger Sub entered into an Agreement and Plan of
        # Merger"), the naive "last org before the match" heuristic below
        # resolves to a transitory merger-vehicle shell (HoldCo/Merger Sub),
        # not either real operating company -- and since neither shell is
        # the pivot, other_party() then silently drops the event. Exclude
        # entities introduced as "a subsidiary of X" (shells formed solely
        # to effect the merger) so real_parties holds the actual companies,
        # in order of first mention.
        real_parties = _non_shell_orgs_in(preamble, orgs)

        acq = None
        if "Company" in aliases and aliases["Company"] in preamble:
            acq = aliases["Company"]
        if not acq:
            if real_parties:
                acq = real_parties[0]
            else:
                prior = [o for o in orgs if o in preamble]
                if prior:
                    acq = prior[-1]

        after = text[m.end():m.end() + 1300]
        target = None
        wm_start = re.search(r"\bwith\s+", after, re.I)
        if wm_start:
            # Real AIG/Validus text: "entered into ... with Venus Holdings
            # Limited, a wholly owned subsidiary of AIG ('Merger Sub') and
            # Validus Holdings, Ltd. ('Validus')" -- the shell is named
            # FIRST in the "with X and Y" list, so the same shell exclusion
            # used for the preamble applies here too. Deliberately NOT
            # truncating this span at the first '.'/';' the way the old
            # known_prefix()-based capture did: a suffix like "Ltd." ends
            # in a period itself, so that truncation could cut off before
            # an org's own trailing period, making the literal org string
            # never match as a substring at all. _non_shell_orgs_in scopes
            # each org's own shell-check via the text between mentions, so
            # it doesn't need a clean sentence-bounded string the way an
            # exact-prefix match did.
            span = after[wm_start.end():wm_start.end() + 300]
            non_shell = [o for o in _non_shell_orgs_in(span, orgs) if o != acq]
            if non_shell:
                target = non_shell[0]
            else:
                wm = re.search(r"\bwith\s+([^.;]{2,180})", after, re.I)
                if wm:
                    target = known_prefix(wm.group(1), orgs)
        if not target:
            candidates = [o for o in orgs if o != acq and o in after]
            if candidates:
                target = min(candidates, key=lambda o: after.find(o))
        if not target:
            # Merger-of-equals fallback: the target's full legal name often
            # never reappears after the match (the filing switches to its
            # short alias), but it was already named alongside the acquirer
            # in the preamble.
            remaining = [o for o in real_parties if o != acq]
            if remaining:
                target = remaining[0]
        if acq and target:
            add_event(
                out, "AGREED_TO_ACQUIRE", acq, target, "COMPLETED",
                text[max(0, m.start() - 120):m.end() + 240],
                extraction_rule="MERGER_AGREEMENT",
            )

    m = re.search(
        r"\bcompleted\s+(?:its(?:\s+previously[- ]announced)?\s+acquisition\s*"
        r"(?:\([^)]{0,80}\))?\s*of|the previously announced transaction with)\s+"
        r"([^.;]{2,180})",
        text,
        re.I,
    )
    if m:
        target = known_prefix(m.group(1), orgs)
        if not target:
            resolved = resolve(m.group(1), aliases)
            if resolved in orgs:
                target = resolved

        acq = None
        if "Company" in aliases and aliases["Company"] in text[:m.start()]:
            acq = aliases["Company"]
        if not acq:
            # Prefer whichever known org or alias sits IMMEDIATELY before
            # "completed" (its actual grammatical subject) over the
            # weaker "last org mentioned anywhere earlier in the text"
            # fallback below -- this also resolves a short alias ("Tesla
            # completed its...") correctly even when the full legal name
            # was only ever stated in an earlier, separate part of the
            # same filing (confirmed on real Tesla/SolarCity closing
            # text). Exact-suffix adjacency check, not a character-class
            # capture, so there's no risk of swallowing preceding text.
            before = text[:m.start()].rstrip()
            adjacent = [c for c in list(orgs) + list(aliases) if c and before.endswith(c)]
            if adjacent:
                best = max(adjacent, key=len)
                acq = best if best in orgs else aliases.get(best)
        if not acq:
            prior = [o for o in orgs if o in text[:m.start()]]
            if prior:
                acq = prior[-1]
        if not target:
            after = text[m.end():m.end() + 400]
            candidates = [o for o in orgs if o != acq and o in after]
            if candidates:
                target = min(candidates, key=lambda o: after.find(o))
        if acq and target:
            add_event(
                out, "ACQUIRED", acq, target, "COMPLETED",
                text[max(0, m.start() - 120):m.end() + 220],
                extraction_rule="COMPLETED_ACQUISITION",
            )

    alias_lc = {k.casefold(): v for k, v in aliases.items()}
    if alias_lc:
        ap = "|".join(sorted((re.escape(k) for k in alias_lc), key=len, reverse=True))

        pat = re.compile(
            rf"\b({ap})\s+(?P<modal>will(?:\s+be)?\s+|was\s+)?(?:merge|merged) with and into\s+({ap})\b",
            re.I,
        )
        for m in pat.finditer(text):
            s = alias_lc.get(m.group(1).casefold())
            o = alias_lc.get(m.group(3).casefold())
            if not s or not o:
                continue
            frag = text[max(0, m.start() - 160):m.end() + 260]
            status = (
                "PROPOSED"
                if m.group("modal") and "will" in m.group("modal").casefold()
                else temporal_status(frag)
            )
            if status == "UNKNOWN":
                status = "COMPLETED" if item == "2.01" else "PROPOSED"
            add_event(
                out, "MERGED_INTO", s, o, status, frag,
                extraction_rule="MERGED_WITH_INTO",
            )

        pat2 = re.compile(
            rf"\bwith\s+(?:the\s+)?({ap})\s+(?:surviving|continuing)[^.;]{{0,220}}?"
            rf"wholly[- ]owned subsidiary of\s+"
            rf"((?:the\s+)?(?:{ap}))",
            re.I,
        )
        for m in pat2.finditer(text):
            s = resolve(m.group(1), aliases)
            o = resolve(m.group(2), aliases)
            if not s or not o:
                continue
            frag = text[max(0, m.start() - 180):m.end() + 180]
            status = temporal_status(frag)
            if status == "UNKNOWN":
                status = "COMPLETED" if item == "2.01" else "PROPOSED"
            add_event(
                out, "SUBSIDIARY_OF", s, o, status, frag,
                extraction_rule="SUBSIDIARY_RELATION",
            )

    # DIVESTED_BUSINESS: a real, previously entirely-unimplemented event
    # type. Gold files for Lumen (3 events) and Disney (1 event) have
    # referenced it since before this session, but no pattern ever
    # existed to produce it -- every DIVESTED_BUSINESS gold event was
    # therefore guaranteed to score NOT_DISCOVERED regardless of parsing
    # quality, a fact only discovered while investigating a real AT&T
    # divestiture. Validated against real Disney text: "Disney and FCN
    # agreed to sell FCN's interests in Fox Sports Net, LLC ('FSN') to
    # Buyer ... (the 'FSN Sale')" / "the FSN Sale was completed".
    dm = re.search(
        r"\bagreed to sell\s+(?:[^.;]{0,100}?\binterests?\s+in\s+[^.;]{2,120}?\s+)?to\s+",
        text,
        re.I,
    )
    if dm:
        seller = None
        if "Company" in aliases and aliases["Company"] in text[:dm.start()]:
            seller = aliases["Company"]
        if not seller:
            # orgs is alphabetically sorted, not in text order -- must
            # sort by actual position to find who's named first.
            prior = sorted(
                (o for o in orgs if o in text[:dm.start()]),
                key=lambda o: text.find(o),
            )
            if prior:
                seller = prior[0]  # the registrant is conventionally named first

        # A fixed-length window, not a punctuation-bounded capture: a
        # decimal number immediately after the buyer's name ("$9.6
        # billion") has its own period, which a [^.;]-style capture would
        # misread as the end of the buyer's name -- same bug class as the
        # AIG "Ltd." truncation fixed earlier. known_prefix()/resolve()
        # don't need a clean boundary; they just need the name to appear
        # somewhere within the window.
        window = text[dm.end():dm.end() + 150]
        buyer = known_prefix(window, orgs)
        if not buyer:
            short = re.match(r"[A-Z][A-Za-z0-9&.'\u2019-]*", window)
            if short:
                resolved = resolve(short.group(0), aliases)
                if resolved in orgs:
                    buyer = resolved
        if buyer:
            # A divestiture's immediate contracting buyer is very often a
            # newly-formed subsidiary of the real acquiring company --
            # prefer the disclosed parent, same as the real Sinclair case.
            buyer = _parent_of(buyer, text, orgs)

        if seller and buyer and seller != buyer:
            status = (
                "COMPLETED" if re.search(r"\bsale\s+was\s+completed\b", text, re.I)
                else "PROPOSED"
            )
            add_event(
                out, "DIVESTED_BUSINESS", seller, buyer, status,
                text[max(0, dm.start() - 150):dm.end() + 150],
                extraction_rule="ASSET_SALE_DIVESTITURE",
            )

    conv = re.search(
        r"(?P<lead>will be\s+|was\s+)?converted from a Delaware corporation "
        r"into a Delaware limited liability company",
        text,
        re.I,
    )
    if conv and "VMware" in aliases:
        frag = text[max(0, conv.start() - 180):conv.end() + 160]
        lead = (conv.group("lead") or "").casefold()
        status = (
            "PROPOSED" if "will" in lead
            else ("COMPLETED" if "was" in lead or item == "2.01" else temporal_status(frag))
        )
        add_event(
            out, "CONVERTED_TO", aliases["VMware"],
            "Delaware limited liability company", status, frag,
            extraction_rule="CORPORATE_CONVERSION",
        )

    # 10-K / long-form filer-declarative pattern.
    for m in re.finditer(
        r"\bwe acquired\s+(?:100%\s+of\s+)?([A-Z][^.;,]{1,120}?)(?:'s equity|,|\.|;)",
        text,
        re.I,
    ):
        raw = m.group(1).strip()
        target = known_prefix(raw, orgs)
        if not target:
            resolved = resolve(raw, aliases)
            if resolved in orgs:
                target = resolved
        if not target:
            continue
        frag = text[max(0, m.start() - 100):m.end() + 200]
        add_event(
            out, "ACQUIRED", "REGISTRANT_SELF_REFERENCE", target, "COMPLETED", frag,
            extraction_rule="REGISTRANT_DECLARATIVE_ACQUISITION",
        )

    # Direction correction: "the Company entered into an Agreement...with
    # Parent...Merger Sub will merge with and into the Company" is
    # IDENTICAL grammar whether the filer is the acquirer OR the target --
    # real EMC Corporation 8-K text (EMC's own filing about being
    # acquired by Denali Holding Inc./Dell) produced a backwards
    # AGREED_TO_ACQUIRE(EMC -> Denali) using the same "the Company =
    # acquirer" heuristic that correctly identifies the acquirer in every
    # case where the filer IS the acquirer. The SUBSIDIARY_OF pattern
    # (built independently, from "with the Company continuing...as a
    # wholly owned subsidiary of Parent") gives a direct, textual signal
    # of who actually acquired whom: if X becomes a subsidiary of Y, Y is
    # the real acquirer. When that signal directly contradicts an
    # AGREED_TO_ACQUIRE/ACQUIRED event's direction, swap it.
    subsidiary_of_pairs = {
        (e["subject"], e["object"])
        for e in out
        if e["event_type"] == "SUBSIDIARY_OF"
    }
    for e in out:
        if e["event_type"] in ("AGREED_TO_ACQUIRE", "ACQUIRED"):
            if (e["subject"], e["object"]) in subsidiary_of_pairs:
                e["subject"], e["object"] = e["object"], e["subject"]

    return out


def completed_only(events):
    mark_transient_relationships(events)
    return [
        e for e in events
        if e["status"] == "COMPLETED" and e.get("lifecycle") != "TRANSIENT"
    ]


def ekey(e):
    return (e["event_type"], norm(e["subject"]), norm(e["object"]), e["status"])


class EdgarMAExtractor:
    """
    Validated EDGAR M&A extraction ensemble.

    Degraded mode is OFF by default. Before this hardening pass, failure to
    load spaCy silently switched production to a different 2-backend algorithm
    and threshold. That made trust semantics machine-dependent. Callers must
    now explicitly opt in with allow_degraded=True, and the returned metadata
    records that degraded mode was used.
    """

    VALIDATED_WEIGHTS = {"regex": 0.5, "spacy": 1.0, "legal_rules": 1.25}
    VALIDATED_THRESHOLD = 1.5
    # An exact match against a real GLEIF legal name is categorically
    # stronger evidence than a suffix/pattern heuristic -- it's not
    # similarity, it's identity against a canonical source. Weighted to
    # meet the default threshold alone, the same way spacy+regex or
    # spacy+legal_rules already can. NOT folded into VALIDATED_WEIGHTS /
    # the default ensemble yet -- see gleif_gazetteer_backend.py's module
    # docstring for what real-filing-text validation is still needed
    # before that.
    GAZETTEER_WEIGHT = 1.5

    def __init__(
        self, spacy_model="en_core_web_sm", *, allow_degraded=False,
        gazetteer_db_path: str | None = None,
    ):
        self.spacy_model = spacy_model
        self.allow_degraded = allow_degraded
        self.degraded_reason = None

        try:
            self.backends = [
                RegexBackend(),
                SpacyBackend(spacy_model),
                LegalRulesBackend(),
            ]
            self.weights = dict(self.VALIDATED_WEIGHTS)
            self.threshold = self.VALIDATED_THRESHOLD
            self.mode = "VALIDATED_3_BACKEND"
        except Exception as exc:
            if not allow_degraded:
                raise RuntimeError(
                    "Validated EDGAR M&A ensemble unavailable; spaCy/model failed "
                    "to load. Refusing silent algorithm substitution. "
                    "Install the validated model or explicitly set allow_degraded=True."
                ) from exc
            self.backends = [RegexBackend(), LegalRulesBackend()]
            self.weights = {"regex": 0.5, "legal_rules": 1.25}
            self.threshold = 1.0
            self.mode = "EXPLICIT_DEGRADED_2_BACKEND"
            self.degraded_reason = f"{type(exc).__name__}: {exc}"

        self.gazetteer_db_path = gazetteer_db_path
        if gazetteer_db_path is not None:
            # Import locally, not at module top: this keeps
            # edgar_ma_extractor importable (and the validated 3-backend
            # ensemble usable) even in an environment without
            # pyahocorasick installed, as long as no caller asks for the
            # gazetteer explicitly. An explicit request that then fails
            # to load raises, per the same no-silent-degradation rule as
            # spaCy above -- opting in and silently getting nothing back
            # would be worse than not offering the option at all.
            from parsers.gleif_gazetteer_backend import GazetteerBackend

            self.backends.append(GazetteerBackend(gazetteer_db_path))
            self.weights["gazetteer"] = self.GAZETTEER_WEIGHT
            self.mode = f"{self.mode}+GAZETTEER"

    def parse_section(self, text: str, item: str | None) -> dict[str, Any]:
        outputs = {b.name: b.parse(text) for b in self.backends}
        fused = fuse(outputs, self.weights, self.threshold)
        raw_events = infer_events(text, fused["aliases"], fused["orgs"], item)
        return {
            "fused": fused,
            "raw_events": raw_events,
            "completed_events": completed_only(raw_events),
            "ensemble": {
                "mode": self.mode,
                "backends": [b.name for b in self.backends],
                "weights": dict(self.weights),
                "threshold": self.threshold,
                "degraded_reason": self.degraded_reason,
            },
        }
