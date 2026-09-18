from __future__ import annotations

def score_health(signals):
    s=dict(signals or {}); score=100; reasons=[]
    critical=['tests_pass','security_pass','database_ok','rollback_ready']; failed=[k for k in critical if not bool(s.get(k))]
    for k in failed: score-=25; reasons.append(k+'_failed')
    try: oi=max(0,int(s.get('open_issues') or 0))
    except Exception: oi=99
    try: rf=max(0,int(s.get('recent_failures') or 0))
    except Exception: rf=99
    if oi: reasons.append(f'open_issues={oi}'); score-=min(20,oi*3)
    if rf: reasons.append(f'recent_failures={rf}'); score-=min(20,rf*5)
    score=max(0,min(100,score)); overall='FAIL' if failed else ('PASS' if score>=90 else 'WARN')
    return {'ok':not failed,'score':score,'overall':overall,'reasons':reasons}
