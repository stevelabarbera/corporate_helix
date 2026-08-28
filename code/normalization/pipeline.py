from copy import deepcopy
from .names import normalize_legal_name, normalize_alias
from .jurisdictions import normalize_jurisdiction
from .keys import make_entity_key, make_relationship_key

def _normalize_entity(entity):
    out=deepcopy(entity)
    raw_name=entity.get("legal_name")
    raw_j=entity.get("jurisdiction")
    former=list(entity.get("former_names") or [])
    nn=normalize_legal_name(raw_name)
    jb=normalize_jurisdiction(raw_j)
    out["identity"]={
        "legal_name_raw":raw_name,
        "legal_name_normalized":nn,
        "legal_name_base":normalize_legal_name(raw_name, True),
        "jurisdiction_raw":raw_j,
        "jurisdiction_normalized":jb,
        "former_names_raw":former,
        "former_names_normalized":[x for x in (normalize_alias(v) for v in former) if x],
    }
    out["entity_key"]=make_entity_key(nn,jb)
    return out

def normalize_provider_result(result):
    out=deepcopy(result)
    ents=[_normalize_entity(e) for e in result.get("entities",[])]
    groups={}
    for i,e in enumerate(ents): groups.setdefault(e["entity_key"],[]).append(i)
    dupes=[{"entity_key":k,"entity_indices":v,"count":len(v),"reason":"same normalized legal name + normalized jurisdiction"}
           for k,v in groups.items() if len(v)>1]
    lookup={}
    for e in ents:
        lookup.setdefault((e["identity"]["legal_name_normalized"],e["identity"]["jurisdiction_normalized"]),e["entity_key"])
    rels=[]
    for rel in result.get("relationships",[]):
        r=deepcopy(rel)
        sn=normalize_legal_name(rel.get("subject_name")); on=normalize_legal_name(rel.get("object_name"))
        jn=normalize_jurisdiction(rel.get("jurisdiction"))
        attrs=rel.get("attributes") or {}
        sjn=normalize_jurisdiction(attrs.get("child_jurisdiction") or attrs.get("subject_jurisdiction"))
        ojn=normalize_jurisdiction(attrs.get("parent_jurisdiction") or attrs.get("object_jurisdiction") or rel.get("jurisdiction"))
        sk=lookup.get((sn,sjn)) or make_entity_key(sn,sjn)
        ok=lookup.get((on,ojn)) or make_entity_key(on,ojn)
        r["identity"]={
            "subject_name_raw":rel.get("subject_name"),
            "subject_name_normalized":sn,
            "object_name_raw":rel.get("object_name"),
            "object_name_normalized":on,
            "jurisdiction_raw":rel.get("jurisdiction"),
            "jurisdiction_normalized":jn,
            "former_names_raw":list(rel.get("former_names") or []),
            "former_names_normalized":[x for x in (normalize_alias(v) for v in (rel.get("former_names") or [])) if x],
        }
        r["subject_entity_key"]=sk; r["object_entity_key"]=ok
        r["relationship_key"]=make_relationship_key(sk, rel.get("predicate") or "", ok)
        rels.append(r)
    out["entities"]=ents; out["relationships"]=rels
    out["normalization"]={
        "version":"m2-v1","duplicate_groups":dupes,
        "entity_count":len(ents),"relationship_count":len(rels),
        "notes":[
            "Normalization is additive; original provider fields are preserved.",
            "entity_key is deterministic from normalized legal name + normalized jurisdiction.",
            "Duplicates are flagged, not removed.",
            "No fuzzy/entity-resolution decision is made in M2."
        ]
    }
    return out
