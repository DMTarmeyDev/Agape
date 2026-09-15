from __future__ import annotations
from typing import Any
import db

def enqueue(project_id: int, goal: str, reason: str='provider_unavailable', provider: str='') -> dict[str,Any]:
    return {'ok':True,'item':db.enqueue_deferred_work(project_id,goal,reason,provider)}
def list_items(project_id: int | None=None, status: str='') -> dict[str,Any]:
    return {'ok':True,'items':db.list_deferred_work(project_id,status)}
def update(item_id: int, status: str) -> dict[str,Any]:
    return {'ok':True,'item':db.update_deferred_work(item_id,status)}
