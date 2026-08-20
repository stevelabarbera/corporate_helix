import re
from .similarity import levenshtein_ratio,jaccard_tokens

def _ids(n):
    return {x for x in n.get("provider_entity_ids") or [] if x}

def _aliases(n):
    return {a.get("name_normalized") for a in n.get("aliases") or [] if a.get("name_normalized")}

def _norm_addr(s):
    if not s: return None
    s=s.casefold()
    s=re.sub(r"[^a-z0-9]+"," ",s)
    return " ".join(s.split()) or None

def _addresses(n):
    out=set()
    for ent in n.get("source_entities") or []:
        vals=ent.get("addresses") or []
        if isinstance(vals,str): vals=[vals]
        for addr in vals:
            # tolerate future structured address objects
            if isinstance(addr,dict):
                addr=" ".join(str(v) for v in addr.values() if v)
            a=_norm_addr(str(addr)) if addr else None
            if a: out.add(a)
    return out

def extract_signals(graph,left,right):
    ln,rn=left.get("canonical_name_normalized"),right.get("canonical_name_normalized")
    lb,rb=left.get("legal_name_base"),right.get("legal_name_base")
    lj,rj=left.get("jurisdiction"),right.get("jurisdiction")
    li,ri=_ids(left),_ids(right); la,ra=_aliases(left),_aliases(right)
    shared=sorted(_addresses(left)&_addresses(right))
    edges=[e for e in graph.get("relationships") or []
           if {e.get("subject_node_id"),e.get("object_node_id")}==
              {left.get("node_id"),right.get("node_id")}]
    return {
      "exact_normalized_name":bool(ln and rn and ln==rn),
      "exact_legal_name_base":bool(lb and rb and lb==rb),
      "levenshtein_ratio":levenshtein_ratio(ln,rn),
      "token_jaccard":jaccard_tokens(ln,rn),
      "jurisdiction_match":bool(lj and rj and lj==rj),
      "jurisdiction_conflict":bool(lj and rj and lj!=rj),
      "exact_provider_identifier":bool(li&ri),
      "provider_identifier_conflict":bool(li and ri and not(li&ri)),
      "explicit_former_name_match":bool((rn in la if rn else False) or (ln in ra if ln else False)),
      "shared_address":bool(shared),
      "shared_addresses":shared,
      "explicit_subsidiary_edge":any(e.get("predicate")=="SUBSIDIARY_OF" for e in edges)
    }
