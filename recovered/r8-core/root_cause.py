from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def rank_root_causes(evidence: dict[str,Any], dependency_graph: dict[str,Any] | None = None, candidate_files: list[Any] | None = None, limit: int = 5) -> dict[str,Any]:
    ev=dict(evidence or {}); dep=dict(dependency_graph or {})
    text='\n'.join(str(ev.get(k) or '') for k in ('stderr','error','stdout'))
    files=[]
    for raw in candidate_files or ev.get('changed_files') or []:
        p=str(raw).replace('\\','/').lstrip('/')
        if p and p not in files: files.append(p)
    for match in re.finditer(r'([A-Za-z0-9_.\-/]+\.py)(?:["\',:\s]|$)',text):
        p=match.group(1).replace('\\','/').lstrip('/')
        if p and p not in files: files.append(p)
    scores={p:0.0 for p in files}
    reasons={p:[] for p in files}
    changed=set(str(x).replace('\\','/').lstrip('/') for x in ev.get('changed_files') or [])
    for p in files:
        if p in changed: scores[p]+=35; reasons[p].append('recently_changed')
        if p in text or Path(p).name in text: scores[p]+=45; reasons[p].append('mentioned_in_failure')
    reasons_map=dep.get('reasons') if isinstance(dep.get('reasons'),dict) else {}
    impacted=set(str(x).replace('\\','/').lstrip('/') for x in dep.get('impacted_files') or [])
    for p in files:
        if p in impacted: scores[p]+=15; reasons[p].append('dependency_impact')
        if p in reasons_map: scores[p]+=5; reasons[p].append('dependency_reason')
    category=str((ev.get('triage') or {}).get('category') or 'unknown')
    rows=[{'file':p,'score':round(min(100.0,scores[p]),2),'reasons':reasons[p]} for p in files]
    rows.sort(key=lambda x:(-x['score'],x['file']))
    top=rows[:max(1,min(int(limit or 5),20))]
    if not top:
        top=[{'file':'','score':0.0,'reasons':['insufficient_file_evidence']}]
    return {'ok':True,'category':category,'hypotheses':top,'primary':top[0],'evidence_sha256':str(ev.get('evidence_sha256') or '')}
