from __future__ import annotations

import hashlib, json, re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def build_evidence_bundle(output_root: str, label: str, evidence: dict[str, Any]) -> dict[str, Any]:
    root=Path(output_root).expanduser().resolve(); root.mkdir(parents=True,exist_ok=True)
    safe=re.sub(r'[^A-Za-z0-9._-]+','-',str(label or 'run')).strip('-')[:80] or 'run'
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    path=root/f'{stamp}-{safe}.json'
    payload={'ok':True,'label':str(label or 'run'),'created_at':datetime.now(timezone.utc).isoformat(),'evidence':evidence}
    raw=json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True).encode('utf-8')
    path.write_bytes(raw)
    return {'ok':True,'path':str(path),'sha256':hashlib.sha256(raw).hexdigest().upper(),'bytes':len(raw)}
