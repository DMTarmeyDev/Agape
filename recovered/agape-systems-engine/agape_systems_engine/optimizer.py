from __future__ import annotations
import itertools, json, math, time, uuid

class SweetSpotOptimizer:
    def __init__(self,db):self.db=db
    def run(self,space,evaluate,quality_floor=0.95,max_trials=50):
        keys=sorted(space);combos=list(itertools.product(*[space[k] for k in keys]))[:max_trials];run_id=uuid.uuid4().hex[:12];best=None
        for i,vals in enumerate(combos,1):
            params=dict(zip(keys,vals));t=time.perf_counter();state='PASS';data={}
            try:
                res=evaluate(params) or {};quality=float(res.get('quality',0));elapsed=float(res.get('elapsed_ms',(time.perf_counter()-t)*1000));cost=float(res.get('cost',0));score=(quality*1000)-(elapsed/100)-cost
                if quality<quality_floor:state='PRUNED_QUALITY';score=-1e9+quality
                data=res
            except Exception as e:
                quality=0;elapsed=(time.perf_counter()-t)*1000;score=-1e12;state='FAIL';data={'error':str(e)}
            with self.db.connect() as c:c.execute('INSERT INTO optimizer_runs(run_id,trial,params_json,score,quality,elapsed_ms,state,data_json) VALUES(?,?,?,?,?,?,?,?)',(run_id,i,json.dumps(params),score,quality,elapsed,state,json.dumps(data)))
            row={'trial':i,'params':params,'score':score,'quality':quality,'elapsed_ms':elapsed,'state':state,'data':data}
            if state=='PASS' and (best is None or score>best['score']):best=row
        return {'run_id':run_id,'trials':len(combos),'best':best}
