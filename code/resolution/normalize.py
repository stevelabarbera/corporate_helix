from __future__ import annotations

import re
import unicodedata

# MVP fallback only. The roadmap still calls for the complete GLEIF ISO 20275 ELF
# list. These common forms make the first resolver usable without pretending this
# is the final legal-form normalizer.
LEGAL_FORMS = {
    "inc", "incorporated", "corp", "corporation", "llc", "ltd", "limited",
    "plc", "gmbh", "bv", "b v", "srl", "s r l", "sa", "s a", "s l", "sas",
    "aps", "kk", "k k", "pte", "pty", "sp z oo", "sp z o o", "private limited",
}


def _ascii(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def normalize_name(name: str | None, strip_legal_form: bool = True) -> str:
    if not name:
        return ""
    text = _ascii(name).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"\([^)]*(?:dormant|non[- ]operational)[^)]*\)", " ", text)
    text = re.sub(r"\(fka\s+[^)]*\)", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not strip_legal_form:
        return text

    changed = True
    while changed and text:
        changed = False
        for suffix in sorted(LEGAL_FORMS, key=len, reverse=True):
            if text == suffix:
                return ""
            if text.endswith(" " + suffix):
                text = text[: -(len(suffix) + 1)].strip()
                changed = True
                break
    return text


def normalize_address(text: str | None) -> str:
    if not text:
        return ""
    text = _ascii(text).lower()
    replacements = {
        "street": "st", "road": "rd", "avenue": "ave", "boulevard": "blvd",
        "suite": "ste", "floor": "fl",
    }
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = [replacements.get(t, t) for t in text.split()]
    return " ".join(tokens)
