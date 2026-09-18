from __future__ import annotations
import hashlib,json
from typing import Any

def export_project(project: dict[str,Any], messages: list[dict[str,Any]], issues: list[dict[str,Any]] | None=None) -> dict[str,Any]:
    p={k:v for k,v in dict(project or {}).items() if k in {'id','name','kind','archived','hidden_reason','created_at','updated_at'}}
    if not p.get('name'): return {'ok':False,'reason':'project_name_required'}
    payload={'format':'agape-project-v1','project':p,'messages':[dict(x) for x in messages or []],'issues':[dict(x) for x in issues or []]}
    raw=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False); digest=hashlib.sha256(raw.encode()).hexdigest().upper()
    return {'ok':True,'payload':payload,'sha256':digest,'message_count':len(payload['messages']),'issue_count':len(payload['issues'])}

def validate_import(payload: dict[str,Any], expected_sha256: str='') -> dict[str,Any]:
    p=dict(payload or {}); valid=p.get('format')=='agape-project-v1' and isinstance(p.get('project'),dict) and bool((p.get('project') or {}).get('name')) and isinstance(p.get('messages'),list)
    raw=json.dumps(p,sort_keys=True,separators=(',',':'),ensure_ascii=False); digest=hashlib.sha256(raw.encode()).hexdigest().upper(); hash_ok=not expected_sha256 or digest==str(expected_sha256).upper()
    return {'ok':bool(valid and hash_ok),'format_ok':bool(valid),'hash_ok':hash_ok,'sha256':digest,'destructive':False}
