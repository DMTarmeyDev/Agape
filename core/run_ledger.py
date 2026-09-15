from __future__ import annotations

from typing import Any
import db


def append_entry(session_id: str, stage: str, status: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    item=db.append_run_ledger(str(session_id or ''),str(stage or ''),str(status or ''),dict(payload or {}))
    return {'ok':True,'entry':item}


def ledger_status(session_id: str) -> dict[str, Any]:
    entries=db.list_run_ledger(str(session_id or ''))
    verified=db.verify_run_ledger(str(session_id or ''))
    return {'ok':verified.get('ok',False),'session_id':str(session_id or ''),'entries':entries,'verification':verified}
