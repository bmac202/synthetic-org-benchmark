import json,glob,sys
from collections import defaultdict
from diffenv.measures import differentiation
def tabs(d):
    ag=d['agents']; W=d['config']['window']; nW=d['config']['rounds']//W
    opp={}
    for k,v in d['opportunity'].items():
        a,r=k.split('|'); opp[(a,int(r))]=v
    sent=defaultdict(int); rec=defaultdict(int); work=defaultdict(int); pas=defaultdict(int)
    for m in d['log']:
        w=m['window']
        if m['mtype']=='tell': sent[(m['sender'],w)]+=1; rec[(m['recipient'],w)]+=1
        elif m['mtype']=='work': work[(m['sender'],w)]+=1
        else: pas[(m['sender'],w)]+=1
    T=defaultdict(list)
    for w in range(nW):
        for a in ag:
            o=sum(1 for r in range(w*W,(w+1)*W) if opp.get((a,r),0)>0)
            load=sum(opp.get((a,r),0) for r in range(w*W,(w+1)*W))
            T['sent'].append(('r',w,a,sent[(a,w)])); T['received'].append(('r',w,a,rec[(a,w)]))
            T['interaction'].append(('r',w,a,sent[(a,w)]+rec[(a,w)]))
            T['opp_rounds'].append(('r',w,a,o)); T['item_load'].append(('r',w,a,load))
            if o>0:
                T['sent|opp'].append(('r',w,a,sent[(a,w)]/o)); T['work|opp'].append(('r',w,a,work[(a,w)]/o))
                T['tellshare'].append(('r',w,a,sent[(a,w)]/max(1,sent[(a,w)]+work[(a,w)])))
    return T
for pat in sys.argv[1:]:
    print("==",pat)
    res=defaultdict(list)
    for p in sorted(glob.glob(f'diffenv_results/final/specimens/{pat}-seed*.json')):
        d=json.load(open(p)); T=tabs(d)
        for k,t in T.items():
            x=differentiation(t,seed=0,n_draws=200)['R']; res[k].append((x['observed'],x['null_p95']))
    for k,v in res.items():
        print(f"  {k:12}", "  ".join(f"{o:.2f}{'*' if o>n else ' '}" for o,n in v), "  (null p95 ~%.2f)"%(sum(n for _,n in v)/len(v)))
