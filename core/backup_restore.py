from __future__ import annotations
import hashlib, sqlite3
from pathlib import Path
from typing import Any

def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest().upper()

def verify_sqlite_backup(path: str) -> dict[str,Any]:
    p=Path(str(path or '')).expanduser().resolve()
    if not p.is_file(): return {'ok':False,'reason':'backup_missing','path':str(p)}
    conn=None
    try:
        conn=sqlite3.connect('file:'+str(p).replace('\\','/')+'?mode=ro',uri=True,timeout=5); quick=str(conn.execute('PRAGMA quick_check').fetchone()[0]); tables=[str(x[0]) for x in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {'ok':quick.lower()=='ok','quick_check':quick,'path':str(p),'size_bytes':p.stat().st_size,'sha256':sha256_file(p),'tables':tables}
    except Exception as exc: return {'ok':False,'reason':'backup_invalid:'+type(exc).__name__,'path':str(p)}
    finally:
        if conn is not None: conn.close()

def plan_restore(backup: dict[str,Any], target: str) -> dict[str,Any]:
    valid=bool((backup or {}).get('ok')); return {'ok':valid,'ready':valid,'action':'restore_with_final_backup_and_approval' if valid else 'stop','approval_required':True,'automatic_restore':False,'target':str(target or ''),'backup_sha256':str((backup or {}).get('sha256') or '')}
