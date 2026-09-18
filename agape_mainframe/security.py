from __future__ import annotations
import json, os, threading, time
from pathlib import Path
from typing import Any
from .platform_paths import security_root

_LOCK = threading.RLock()
SECURITY_ROOT = security_root()
APPROVED_FILE = SECURITY_ROOT / "approved-installers.json"
AUDIT_FILE = SECURITY_ROOT / "installer-audit.jsonl"
APPROVAL_DIR = SECURITY_ROOT / "approvals"


def _ensure() -> None:
    SECURITY_ROOT.mkdir(parents=True, exist_ok=True)
    APPROVAL_DIR.mkdir(parents=True, exist_ok=True)


def _empty() -> dict[str, Any]:
    return {"schema": 1, "approved": []}


def _load() -> dict[str, Any]:
    _ensure()
    if not APPROVED_FILE.exists():
        return _empty()
    try:
        raw = json.loads(APPROVED_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return _empty()
        rows = raw.get("approved")
        if not isinstance(rows, list):
            rows = []
        return {"schema": 1, "approved": [x for x in rows if isinstance(x, dict)]}
    except Exception:
        return _empty()


def _save(data: dict[str, Any]) -> None:
    _ensure()
    tmp = APPROVED_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, APPROVED_FILE)


def _file_approvals() -> list[dict[str, Any]]:
    _ensure()
    out: list[dict[str, Any]] = []
    for path in APPROVAL_DIR.glob("*.approved"):
        try:
            row: dict[str, Any] = {}
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                row[k.strip()] = v.strip()
            if row.get("id"):
                row["_path"] = str(path)
                out.append(row)
        except Exception:
            continue
    return out


def approved_installers() -> list[dict[str, Any]]:
    with _LOCK:
        rows = list(_load()["approved"]) + _file_approvals()
        keep = {"id", "kind", "name", "sha256", "publisher", "certificate_thumbprint", "signature_status", "approved_at", "version"}
        dedup: dict[str, dict[str, Any]] = {}
        for row in rows:
            clean = {k: v for k, v in row.items() if k in keep}
            if clean.get("id"):
                dedup[str(clean["id"])] = clean
        return list(dedup.values())


def revoke_approval(approval_id: str) -> dict[str, Any]:
    key = str(approval_id or "").strip()
    if not key:
        raise ValueError("APPROVAL_ID_REQUIRED")
    with _LOCK:
        data = _load()
        before = len(data["approved"])
        data["approved"] = [x for x in data["approved"] if str(x.get("id") or "") != key]
        removed_file = False
        for row in _file_approvals():
            if str(row.get("id") or "") == key and row.get("_path"):
                try:
                    Path(str(row["_path"])).unlink()
                    removed_file = True
                except FileNotFoundError:
                    pass
        removed_json = len(data["approved"]) != before
        if removed_json:
            _save(data)
        if not removed_json and not removed_file:
            return {"ok": True, "removed": False, "approved": approved_installers()}
        _ensure()
        event = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "action": "approval_revoked",
            "approval_id": key,
            "source": "Agape Settings",
        }
        with AUDIT_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        return {"ok": True, "removed": True, "approved": approved_installers()}
