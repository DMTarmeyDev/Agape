from __future__ import annotations
import uuid
from typing import Any
import db

_REQUIRED=('system','database','history','templates','models','project_loop','stages31_40','stages41_50','stages51_60','stages61_70','stages71_80','stages81_100','rollback','mission_proof')
def evaluate(signals: dict[str,Any], required: list[str] | None=None) -> dict[str,Any]:
    req=list(required or _REQUIRED); s=dict(signals or {}); missing=[x for x in req if not bool(s.get(x))]; return {'ok':not missing,'release_ready':not missing,'overall':'PASS' if not missing else 'FAIL','passed':len(req)-len(missing),'total':len(req),'missing':missing,'required':req}
def record(build: str, evaluation: dict[str,Any], proof_sha256: str='', detail: dict[str,Any] | None=None) -> dict[str,Any]:
    status='PASS' if bool((evaluation or {}).get('release_ready')) else 'FAIL'; run_id='ALPHA-'+uuid.uuid4().hex.upper()[:16]; item=db.record_alpha_release_run(run_id,str(build or ''),status,str(proof_sha256 or ''),dict(detail or {})); return {'ok':True,'run':item}
