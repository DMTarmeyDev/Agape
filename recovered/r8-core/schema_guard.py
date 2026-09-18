from __future__ import annotations
from typing import Any

def evaluate_schema(database: dict[str,Any], tables: list[str], schema_version: int, required_tables: list[str] | None=None, minimum_version: int=9) -> dict[str,Any]:
    req=list(required_tables or ['projects','messages','connections','project_loop_runs','autodev_sessions','run_ledger','supervisor_runs','deferred_work','audit_events','alpha_release_runs']); have={str(x) for x in tables or []}; missing=[x for x in req if x not in have]; dbok=bool((database or {}).get('ok')) and str((database or {}).get('quick_check') or '').lower()=='ok'; version_ok=int(schema_version or 0)>=int(minimum_version)
    return {'ok':dbok and version_ok and not missing,'database_ok':dbok,'version_ok':version_ok,'schema_version':int(schema_version or 0),'minimum_version':int(minimum_version),'missing_tables':missing}
