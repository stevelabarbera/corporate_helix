import hashlib
def _stable(parts):
    payload="|".join((p or "").strip() for p in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
def make_entity_key(normalized_name, normalized_jurisdiction):
    return "ent:" + _stable([normalized_name, normalized_jurisdiction])
def make_relationship_key(subject_key, predicate, object_key):
    return "rel:" + _stable([subject_key, predicate, object_key])
