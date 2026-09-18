from __future__ import annotations
from typing import Any
_REQUIRED=('system_test','database','history','project_filter','ollama','templates','autodev','rollback','startup','security','provider_layer','diagnostics')
def evaluate(signals: dict[str,Any], required: list[str] | None=None) -> dict[str,Any]:
    req=list(required or _REQUIRED); s=dict(signals or {}); missing=[k for k in req if not bool(s.get(k))]; return {'ok':not missing,'overall':'PASS' if not missing else 'FAIL','passed':len(req)-len(missing),'total':len(req),'missing':missing,'alpha_ready':not missing}
