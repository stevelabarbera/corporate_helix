#!/usr/bin/env python3
import re

CORP = r"(?:Inc\.?|Incorporated|Corporation|Corp\.?|LLC|L\.L\.C\.|Ltd\.?|Limited|PLC|plc)"
ENTITY = re.compile(rf"\b([A-Z][A-Za-z0-9&.'’\- ]{{1,80}}?(?:,\s*)?{CORP})\b")

BAD_ENTITY_PREFIXES = (
    "section ", "article ", "item ", "form ", "rule ", "schedule "
)

def clean(s):
    return re.sub(r"\s+", " ", s or "").strip(" ,.;") or None

def is_plausible_entity(name):
    n = clean(name)
    if not n:
        return False
    low = n.casefold()
    if low.startswith(BAD_ENTITY_PREFIXES):
        return False
    if "general corporation" in low and low.startswith("section "):
        return False
    return True

def alias_map(text):
    out = {}

    # Full legal entity -> quoted alias(es)
    for m in ENTITY.finditer(text):
        ent = clean(m.group(1))
        if not is_plausible_entity(ent):
            continue
        out[ent.casefold()] = ent
        tail = text[m.end():m.end()+260]
        pm = re.match(r"\s*(?:,\s*(?:a|an)\s+[^()]{0,120})?\s*\(([^)]{1,190})\)", tail, re.S)
        if pm:
            for a in re.findall(r'[“"]\s*(?:the\s+)?([^”"]+?)\s*[”"]', pm.group(1), re.I):
                a = clean(a)
                if a and len(a) < 80:
                    out[a.casefold()] = ent

    # Survivor aliases: "with Holdco continuing as ... (the “Holdco Surviving Company”)"
    survivor_pat = re.compile(
        r"\bwith\s+(?P<base>(?:the\s+)?[A-Za-z0-9 ]{1,60})\s+continuing\s+as\s+the\s+surviving[^()]{0,120}"
        r"\((?:the\s+)?[“\"](?P<alias>[^”\"]+)[”\"]\)",
        re.I | re.S
    )
    for m in survivor_pat.finditer(text):
        base = resolve(m.group("base"), out)
        alias = clean(m.group("alias"))
        if base and alias:
            out[alias.casefold()] = base

    return out

def resolve(s, aliases):
    s = clean(s)
    if not s:
        return None
    s = re.sub(r"^(?:following\s+(?:the\s+)?[^,]{1,70},\s*|with\s+|and\s+)", "", s, flags=re.I)
    # "the Company" should resolve via alias "company"
    key = re.sub(r"^the\s+", "", s, flags=re.I).casefold()
    return aliases.get(key, aliases.get(s.casefold(), s))

def span(text, start, end, pad=100):
    return clean(text[max(0, start-pad):min(len(text), end+pad)])

def last_entity_before(text, pos):
    ms = [m for m in ENTITY.finditer(text[:pos]) if is_plausible_entity(m.group(1))]
    return clean(ms[-1].group(1)) if ms else None

def agreement(text):
    aliases = alias_map(text)
    marker = re.search(
        r"\bentered into an? Agreement and Plan of Merger\b|\bentered into an? Merger Agreement\b",
        text, re.I
    )
    if not marker:
        return None

    acquirer = resolve(last_entity_before(text, marker.start()), aliases)
    after = text[marker.end():marker.end()+1400]

    # Broadcom style: "... Merger Agreement ... with VMware, Inc."
    wm = re.search(r"\bwith\s+(" + ENTITY.pattern[2:-2] + r")", after, re.I)
    if wm and is_plausible_entity(wm.group(1)):
        target = resolve(wm.group(1), aliases)
        return {
            "acquirer": acquirer,
            "target": target,
            "aliases": aliases,
            "evidence": span(text, marker.start(), marker.end())
        }

    # Cisco style: "... by and among the Company, Splunk Inc., ... and Spirit Merger Corp., ...
    # pursuant to which ..."
    bam = re.search(r"\bby and among\b(?P<body>.{1,1200}?)(?:\bpursuant to which\b|\.\s)", after, re.I | re.S)
    if bam:
        ents = []
        for m in ENTITY.finditer(bam.group("body")):
            ent = clean(m.group(1))
            if is_plausible_entity(ent):
                resolved = resolve(ent, aliases)
                if resolved not in ents:
                    ents.append(resolved)
        for ent in ents:
            if ent and ent != acquirer and "merger sub" not in ent.casefold():
                return {
                    "acquirer": acquirer,
                    "target": ent,
                    "aliases": aliases,
                    "evidence": span(text, marker.start(), marker.end())
                }

    return None

def completion(text):
    aliases = alias_map(text)
    patterns = [
        r"\bcompleted\s+(?:its|the)\s+acquisition\s+of\s+(" + ENTITY.pattern[2:-2] + r")",
        r"\bcompleted\s+the\s+(?:previously announced\s+)?transaction\s+with\s+(" + ENTITY.pattern[2:-2] + r")",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m and is_plausible_entity(m.group(1)):
            return {
                "acquirer": resolve(last_entity_before(text, m.start()), aliases),
                "target": resolve(m.group(1), aliases),
                "evidence": span(text, m.start(), m.end())
            }
    return None

def merger_actions(text):
    aliases = alias_map(text)
    out = []
    ref = r"(?:[A-Z][A-Za-z0-9&.'’\- ]{1,80}?(?:,\s*)?" + CORP + r"|(?:the\s+)?[A-Z][A-Za-z0-9 ]{1,55})"
    pat = re.compile(
        r"(?P<s>" + ref + r")\s+(?:will be\s+|was\s+)?merged with and into\s+(?P<o>" + ref + r")",
        re.I
    )
    for m in pat.finditer(text):
        subject = resolve(m.group("s"), aliases)
        obj = resolve(m.group("o"), aliases)
        if not subject or not obj:
            continue
        window = text[m.end():m.end()+450]
        survivor = None
        sm = re.search(r"\bwith\s+(?P<x>" + ref + r")\s+(?:continuing|surviving)", window, re.I)
        if sm:
            survivor = resolve(sm.group("x"), aliases)
        out.append({
            "subject": subject,
            "object_entity": obj,
            "result_entity": survivor,
            "evidence": span(text, m.start(), m.end())
        })
    return out

def subsidiary_actions(text):
    aliases = alias_map(text)
    out = []

    # "with Splunk surviving ... as a wholly owned subsidiary of the Company"
    pat = re.compile(
        r"\bwith\s+(?P<s>(?:the\s+)?[A-Za-z0-9 ]{1,70})\s+"
        r"(?:surviving|continuing)[^.;]{0,220}?"
        r"(?:as|becoming)\s+a\s+wholly[- ]owned subsidiary of\s+"
        r"(?P<p>(?:the\s+)?[A-Za-z0-9 ]{1,70})",
        re.I
    )
    for m in pat.finditer(text):
        s = resolve(m.group("s"), aliases)
        p = resolve(m.group("p"), aliases)
        if s and p:
            out.append({
                "subject": s,
                "object_entity": p,
                "evidence": span(text, m.start(), m.end())
            })

    # de-duplicate
    seen = set()
    result = []
    for x in out:
        k = (x["subject"], x["object_entity"])
        if k not in seen:
            seen.add(k)
            result.append(x)
    return result

def conversion_actions(text, default_subject=None):
    aliases = alias_map(text)
    out = []
    pat = re.compile(
        r"(?P<s>(?:the\s+)?[A-Z][A-Za-z0-9 ]{1,70})\s+was converted from an?\s+"
        r"(?P<f>[^.;]{2,80}?)\s+into an?\s+(?P<t>[^.;]{2,80}?)(?=\s*(?:\(|;|\.))",
        re.I
    )
    for m in pat.finditer(text):
        s = resolve(m.group("s"), aliases)
        if s and "surviving company" in s.casefold() and default_subject:
            s = default_subject
        out.append({
            "subject": s,
            "from_legal_form": clean(m.group("f")),
            "to_legal_form": clean(m.group("t")),
            "result_entity": None,
            "evidence": span(text, m.start(), m.end())
        })
    return out
