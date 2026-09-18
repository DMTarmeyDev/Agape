from __future__ import annotations
from typing import Any
import db

def append(category: str, action: str, status: str, payload: dict[str,Any] | None=None, project_id: int | None=None) -> dict[str,Any]:
    return {'ok':True,'event':db.append_audit_event(category,action,status,payload or {},project_id)}
def verify() -> dict[str,Any]: return db.verify_audit_events()
def list_events(limit: int=100) -> dict[str,Any]: return {'ok':True,'events':db.list_audit_events(limit)}
