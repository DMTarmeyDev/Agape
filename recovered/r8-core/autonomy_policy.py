from __future__ import annotations

from typing import Any
import approval_gate


def decide_autonomy(change: dict[str,Any], mode: str = 'safe') -> dict[str,Any]:
    policy=str(mode or 'safe').lower().strip()
    if policy not in {'safe','balanced','manual'}: raise ValueError('AUTONOMY_MODE_INVALID')
    base=approval_gate.evaluate_change(dict(change or {}))
    decision=str(base.get('decision') or 'block')
    risk=str(base.get('risk') or 'critical')
    if decision=='block': action='block'
    elif policy=='manual': action='approval_required'
    elif decision=='approval_required': action='approval_required'
    else: action='auto_continue'
    return {'ok':action!='block','action':action,'mode':policy,'risk':risk,'reasons':list(base.get('reasons') or []),'base':base,'human_required':action=='approval_required'}
