from __future__ import annotations
from typing import Any

def score_provider(observations: list[dict[str,Any]]) -> dict[str,Any]:
    rows=list(observations or [])
    if not rows: return {'ok':True,'score':0.5,'classification':'unknown','runs':0,'success_rate':0.0,'avg_latency_ms':0.0}
    success=sum(1 for x in rows if str(x.get('status') or '').lower() in {'pass','ok','healthy','success'} or bool(x.get('success'))); latency=[max(0.0,float(x.get('latency_ms') or x.get('duration_ms') or 0)) for x in rows]; rate=success/len(rows); avg=sum(latency)/len(latency) if latency else 0.0; penalty=min(avg/30000.0,0.25); score=max(0.0,min(1.0,rate-penalty)); cls='healthy' if score>=0.8 else 'degraded' if score>=0.5 else 'unhealthy'
    return {'ok':True,'score':round(score,4),'classification':cls,'runs':len(rows),'success_rate':round(rate,4),'avg_latency_ms':round(avg,2)}
