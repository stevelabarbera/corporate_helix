def levenshtein_distance(a,b):
    if a==b:return 0
    if not a:return len(b)
    if not b:return len(a)
    prev=list(range(len(b)+1))
    for i,ca in enumerate(a,1):
        cur=[i]
        for j,cb in enumerate(b,1):
            cur.append(min(cur[j-1]+1,prev[j]+1,prev[j-1]+(0 if ca==cb else 1)))
        prev=cur
    return prev[-1]
def levenshtein_ratio(a,b):
    if not a or not b:return None
    d=max(len(a),len(b))
    return 1.0-(levenshtein_distance(a,b)/d)
def jaccard_tokens(a,b):
    if not a or not b:return None
    sa,sb=set(a.split()),set(b.split()); u=sa|sb
    return len(sa&sb)/len(u) if u else 1.0
