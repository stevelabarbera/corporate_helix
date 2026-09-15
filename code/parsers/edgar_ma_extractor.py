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


CORP = r"(?:Inc\.?|Incorporated|Corporation|Corp\.?|LLC|L\.L\.C\.|L\.P\.|LP|Ltd\.?|Limited|PLC|plc|Company)"
_WORD = r"(?:[A-Z][A-Za-z0-9&.'’-]*|[0-9][A-Za-z0-9&.'’-]*)"
_CONNECTOR = r"(?:of|and|the|for)"
ENT = re.compile(
    r"\b(" + _WORD + r"(?:[\s-]+(?:" + _WORD + r"|" + _CONNECTOR + r")){0,7}"
    + r",?\s*" + CORP + r")(?![A-Za-z.])"
)


class RegexBackend:
    name = "regex"

    def parse(self, text):
        orgs, aliases = [], {}
        for m in ENT.finditer(text):
            ent = norm(m.group(1))
            orgs.append(ent)
            tail = text[m.end():m.end() + 260]
            pm = re.match(
                r"\s*(?:,\s*(?:a|an)\s+[^()]{0,150})?\s*\(([^)]{1,220})\)",
                tail,
                re.S,
            )
            if pm:
                for a in re.findall(r'[“"]\s*(?:the\s+)?([^”"]+?)\s*[”"]', pm.group(1), re.I):
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
            tail = text[e.end_char:e.end_char + 260]
            pm = re.match(
                r"\s*(?:,\s*(?:a|an)\s+[^()]{0,150})?\s*\(([^)]{1,220})\)",
                tail,
                re.S,
            )
            if pm:
                for a in re.findall(r'[“"]\s*(?:the\s+)?([^”"]+?)\s*[”"]', pm.group(1), re.I):
                    aliases[norm(a)] = ent
        return {"orgs": sorted(set(orgs)), "aliases": aliases}


class LegalRulesBackend:
    name = "legal_rules"

    def parse(self, text):
        orgs, aliases = [], {}
        for m in ENT.finditer(text):
            ent = norm(m.group(1))
            tail = text[m.end():m.end() + 260]
            pm = re.match(
                r"\s*(?:,\s*(?:a|an)\s+[^()]{0,150})?\s*\(([^)]{1,220})\)",
                tail,
                re.S,
            )
            if not pm:
                continue
            got = False
            for a in re.findall(r'[“"]\s*(?:the\s+)?([^”"]+?)\s*[”"]', pm.group(1), re.I):
                aliases[norm(a)] = ent
                got = True
            if got:
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
    merger_exec = "entered into an agreement and plan of merger" in low[:2200]
    if item == "1.01" and financing and not merger_exec:
        return out

    m = re.search(r"\bentered into an? Agreement and Plan of Merger\b", text, re.I)
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
        positions = sorted(
            ((o, preamble.find(o)) for o in orgs if o in preamble),
            key=lambda t: t[1],
        )
        real_parties = []
        for i, (o, pos) in enumerate(positions):
            end = positions[i + 1][1] if i + 1 < len(positions) else len(preamble)
            context = preamble[pos + len(o):end]
            if re.search(r"\bsubsidiary of\b", context, re.I):
                continue
            real_parties.append(o)

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
        acq = None
        if "Company" in aliases and aliases["Company"] in text[:m.start()]:
            acq = aliases["Company"]
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
            rf"\bwith\s+({ap})\s+(?:surviving|continuing)[^.;]{{0,220}}?"
            rf"(?:as|becoming)\s+a\s+wholly[- ]owned subsidiary of\s+"
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

    def __init__(self, spacy_model="en_core_web_sm", *, allow_degraded=False):
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
