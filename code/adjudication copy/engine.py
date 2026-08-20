from copy import deepcopy
from .signals import extract_signals
from .policies import get_policy
def evaluate_candidate(graph,left,right,policy_name):
    p=deepcopy(get_policy(policy_name)); s=extract_signals(graph,left,right)
    hc=[x for x in p.get("hard_confirms",[]) if s.get(x) is True]
    hx=[x for x in p.get("hard_conflicts",[]) if s.get(x) is True]
    score=0.0; contrib=[]
    for sig,w in p.get("weights",{}).items():
        if s.get(sig) is True: score+=w; contrib.append((sig,w))
    for sig,w in p.get("numeric_weights",{}).items():
        v=s.get(sig)
        if v is not None: score+=v*w; contrib.append((sig,round(v*w,4)))
    guards=[]
    if hx:
        decision,reason,res="REJECT","hard_conflict","HARD_IDENTIFIER_CONFLICT"
    elif hc:
        decision,reason,res="ACCEPT","hard_confirm","EXPLICIT_CONTINUITY_OR_IDENTIFIER"
    else:
        hit=None
        for g in p.get("guards",[]):
            if s.get(g.get("when")) is True and g.get("effect")=="reject":
                hit=g; break
        if hit:
            guards.append(hit); decision,reason,res="REJECT","guard",hit["resolution_reason"]
        elif score>=p["thresholds"]["auto_accept"]:
            decision,reason,res="ACCEPT","score_threshold","SUFFICIENT_SIGNAL_AGREEMENT"
        elif score>=p["thresholds"]["review"]:
            decision,reason,res="REVIEW","score_threshold","AMBIGUOUS_SIGNAL_AGREEMENT"
        else:
            decision,reason,res="REJECT","score_threshold","INSUFFICIENT_IDENTITY_EVIDENCE"
    return {"decision":decision,"resolution_reason":res,"decision_reason":reason,"score":round(score,4),"signals":s,"guard_events":guards,"hard_confirms":hc,"hard_conflicts":hx,"contributions":contrib}
