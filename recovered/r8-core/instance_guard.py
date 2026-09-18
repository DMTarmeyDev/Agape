from __future__ import annotations
from pathlib import Path
from typing import Any

def verify_instance(runtime: dict[str,Any], expected_build: str, expected_project_path: str='', fixed_port: int=8797) -> dict[str,Any]:
    r=dict(runtime or {}); reasons=[]
    if not r.get('ok',True): reasons.append('runtime_not_ok')
    if str(r.get('build') or '')!=str(expected_build or ''): reasons.append('build_mismatch')
    url=str(r.get('url') or r.get('base_url') or '')
    if url and (':'+str(int(fixed_port))) not in url: reasons.append('port_mismatch')
    if expected_project_path and r.get('project_path'):
        try:
            if Path(str(r['project_path'])).resolve()!=Path(str(expected_project_path)).resolve(): reasons.append('project_path_mismatch')
        except Exception: reasons.append('project_path_invalid')
    return {'ok':not reasons,'single_instance_verified':not reasons,'reasons':reasons,'expected_build':str(expected_build),'fixed_port':int(fixed_port)}
