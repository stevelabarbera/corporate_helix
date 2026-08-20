import re, unicodedata

LEGAL_SUFFIX_PATTERNS = [
    r"incorporated", r"inc", r"corporation", r"corp", r"limited", r"ltd",
    r"llc", r"l\.l\.c", r"plc", r"gmbh", r"b\.?v\.?", r"s\.?a\.?",
    r"s\.?a\.?s\.?", r"s\.?r\.?l\.?", r"aps", r"pte", r"pty", r"kk", r"co"
]

def _fold(v):
    v = unicodedata.normalize("NFKD", v)
    v = "".join(ch for ch in v if not unicodedata.combining(ch))
    return v

def normalize_legal_name(value, strip_legal_suffix=False):
    if not value: return None
    text = _fold(value).casefold().replace("&", " and ")
    text = re.sub(r"[’'`]", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if strip_legal_suffix:
        changed = True
        while changed and text:
            changed = False
            for pat in LEGAL_SUFFIX_PATTERNS:
                new = re.sub(rf"(?:\s+|^){pat}\.?$", "", text, flags=re.I).strip()
                if new != text:
                    text = new; changed = True; break
    return text or None

def normalize_alias(value):
    return normalize_legal_name(value, False)
