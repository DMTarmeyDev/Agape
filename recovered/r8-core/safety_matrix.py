from __future__ import annotations
from typing import Any

def evaluate(action: dict[str,Any]) -> dict[str,Any]:
    a=dict(action or {}); reasons=[]; approval=False
    if bool(a.get('admin')): reasons.append('admin_operation'); approval=True
    if bool(a.get('system_path')) or bool(a.get('protected_source')): reasons.append('protected_scope'); approval=True
    if str(a.get('operation') or '').lower() in {'delete','format','partition','firmware','bcd','credential_export'}: reasons.append('high_risk_operation'); approval=True
    network=bool(a.get('network')); external=bool(a.get('external_write'))
    if network and external: reasons.append('external_side_effect'); approval=True
    blocked=any(x in reasons for x in {'high_risk_operation'})
    return {'ok':not blocked,'allowed':not blocked,'approval_required':approval,'risk':'high' if blocked else 'medium' if approval else 'low','reasons':reasons or ['ordinary_project_operation']}
