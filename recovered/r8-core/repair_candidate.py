from __future__ import annotations

from typing import Any


def score_candidates(candidates: list[dict[str,Any]]) -> dict[str,Any]:
    rows=[]
    for i,raw in enumerate(candidates or []):
        c=dict(raw or {}); ident=str(c.get('id') or f'C{i+1}')
        files=max(0,int(c.get('files_changed') or len(c.get('files') or [])))
        lines=max(0,int(c.get('changed_lines') or 0))
        confidence=max(0.0,min(float(c.get('confidence') or 0.0),1.0))
        tests=bool(c.get('tests_passed')); regressions=bool(c.get('regressions_passed')); scope=bool(c.get('scope_safe',True)); budget=bool(c.get('budget_safe',True)); approval=str(c.get('approval') or 'allow').lower()
        score=confidence*40+(25 if tests else 0)+(20 if regressions else 0)+(10 if scope else -50)+(5 if budget else -30)-min(files*2,12)-min(lines/50.0,10)
        if approval=='block': score-=100
        elif approval=='approval_required': score-=15
        eligible=scope and budget and approval!='block'
        rows.append({'id':ident,'score':round(score,3),'eligible':eligible,'tests_passed':tests,'regressions_passed':regressions,'scope_safe':scope,'budget_safe':budget,'approval':approval,'files_changed':files,'changed_lines':lines})
    rows.sort(key=lambda x:(not x['eligible'],-x['score'],x['id']))
    selected=next((x for x in rows if x['eligible']),None)
    return {'ok':bool(selected),'selected':selected,'candidates':rows,'reason':'highest_safe_evidence_score' if selected else 'no_eligible_candidate'}
