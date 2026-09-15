from __future__ import annotations

import hashlib
import json
from typing import Any


def attest_baseline(runtime: dict[str,Any], database: dict[str,Any], expected_build: str, manifest_build: str = '', source_manifest_ok: bool = True, history_preserved: bool = True) -> dict[str,Any]:
    rt=dict(runtime or {}); dbs=dict(database or {})
    live=str(rt.get('build') or '')
    expected=str(expected_build or '').strip()
    manifest=str(manifest_build or expected).strip()
    checks={
        'runtime_ok':bool(rt.get('ok',True)) and bool(live),
        'build_identity':bool(expected) and live==expected,
        'manifest_identity':bool(manifest) and manifest==expected,
        'source_manifest':bool(source_manifest_ok),
        'database_integrity':str(dbs.get('quick_check') or '').lower()=='ok',
        'history_preserved':bool(history_preserved),
    }
    canonical={'build':live,'expected_build':expected,'manifest_build':manifest,'database':str(dbs.get('database') or ''),'checks':checks}
    digest=hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')).hexdigest().upper()
    failed=[k for k,v in checks.items() if not v]
    return {'ok':not failed,'ready':not failed,'build':live,'expected_build':expected,'checks':checks,'failed':failed,'attestation_sha256':digest}
