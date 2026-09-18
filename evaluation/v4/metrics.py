"""Chunk-level IR metrics. Gold labels must be complete for the specified query."""
import math

def ir_metrics(ids,relevant,k=5):
    top=list(dict.fromkeys(ids))[:k]; relevant=set(relevant)
    if not relevant:return {'answerable':False,'recall_at_k':None,'hit_at_k':None,'mrr_at_k':None,'ndcg_at_k':None}
    hit=set(top)&relevant
    dcg=sum(1/math.log2(i+2) for i,x in enumerate(top) if x in relevant)
    ideal=sum(1/math.log2(i+2) for i in range(min(k,len(relevant))))
    return {'answerable':True,'recall_at_k':len(hit)/len(relevant),'hit_at_k':float(bool(hit)),
        'mrr_at_k':next((1/(i+1) for i,x in enumerate(top) if x in relevant),0),
        'precision_at_k':len(hit)/k,'ndcg_at_k':dcg/ideal}
