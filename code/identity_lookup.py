"""Conservative, punctuation-insensitive lookup key for legal-name candidate retrieval.

Do not strip corporate-form words here: they may be meaningful identity tokens.
This key is NOT evidence that two legal entities are the same.
"""
import re


def legal_name_lookup_key(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(re.sub(r"[^\w]+", " ", value.casefold().strip(), flags=re.UNICODE).split())
