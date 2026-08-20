POLICIES={
"SAME_ENTITY":{
 "name":"SAME_ENTITY",
 "hard_confirms":["exact_provider_identifier","explicit_former_name_match"],
 "hard_conflicts":["provider_identifier_conflict"],
 "weights":{"exact_normalized_name":35,"exact_legal_name_base":15,"jurisdiction_match":20,"shared_address":8},
 "numeric_weights":{"levenshtein_ratio":12,"token_jaccard":10},
 "penalties":{},
 "thresholds":{"auto_accept":75,"review":45},
 "guards":[{"name":"distinct_by_jurisdiction","when":"jurisdiction_conflict","effect":"reject","resolution_reason":"DISTINCT_BY_JURISDICTION"}]
},
"SUBSIDIARY_OF":{
 "name":"SUBSIDIARY_OF",
 "hard_confirms":["explicit_subsidiary_edge"],
 "hard_conflicts":[],
 "weights":{"exact_legal_name_base":4,"jurisdiction_match":2,"shared_address":3},
 "numeric_weights":{"levenshtein_ratio":2,"token_jaccard":2},
 "penalties":{},
 "thresholds":{"auto_accept":70,"review":35},
 "guards":[]
}}
def get_policy(name):
    k=name.upper()
    if k not in POLICIES: raise KeyError(name)
    return POLICIES[k]
