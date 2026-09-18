from __future__ import annotations
import hashlib,json
from typing import Any

def build(goal: str, stages: dict[str,Any], tests: dict[str,Any], database: dict[str,Any], history_preserved: bool, provider: dict[str,Any], safety: dict[str,Any]) -> dict[str,Any]:
    signals={'goal':bool(str(goal or '').strip()),'stages':all(bool(v) for v in dict(stages or {}).values()) if stages else False,'tests':bool((tests or {}).get('ok')),'database':bool((database or {}).get('ok')) and str((database or {}).get('quick_check') or '').lower()=='ok','history':bool(history_preserved),'provider':bool((provider or {}).get('ok')),'safety':bool((safety or {}).get('ok'))}
    ready=all(signals.values()); payload={'goal':str(goal or '').strip(),'signals':signals,'stages':stages,'tests':tests,'database_quick_check':str((database or {}).get('quick_check') or ''),'provider':provider,'safety':safety}; raw=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False); digest=hashlib.sha256(raw.encode()).hexdigest().upper()
    return {'ok':ready,'ready':ready,'signals':signals,'proof_sha256':digest,'payload':payload}
