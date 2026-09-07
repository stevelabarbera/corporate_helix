import re, unicodedata

ALIASES = {
    "us":"US","u s":"US","u s a":"US","usa":"US","united states":"US","united states of america":"US",
    "uk":"GB","u k":"GB","u k":"GB","united kingdom":"GB","great britain":"GB","england":"GB",
    "south korea":"KR","korea":"KR","republic of korea":"KR","czech republic":"CZ","czechia":"CZ",
    "netherlands":"NL","germany":"DE","france":"FR","spain":"ES","ireland":"IE","italy":"IT",
    "poland":"PL","japan":"JP","singapore":"SG","australia":"AU","denmark":"DK","israel":"IL",
    "china":"CN","malaysia":"MY","thailand":"TH","india":"IN","costa rica":"CR"
}
def _fold(v):
    v=unicodedata.normalize("NFKD",v)
    v="".join(ch for ch in v if not unicodedata.combining(ch)).casefold()
    v=re.sub(r"[^a-z0-9]+"," ",v)
    return re.sub(r"\s+"," ",v).strip()
def normalize_jurisdiction(value):
    if not value: return None
    return ALIASES.get(_fold(value), value.strip())
