from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import db
from config import BUILD, DATA_ROOT
from providers import ollama_models
from security import ensure_session_token
from workflows import list_templates
from project_loop import auto_select_model

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "manifest.json"
RECEIPT = DATA_ROOT / "install-receipt.json"
PREFERRED_MODEL = "qwen2.5-coder:1.5b-instruct"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def _manifest_check() -> dict[str, Any]:
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
        expected = manifest.get("files", {})
        if not isinstance(expected, dict) or not expected:
            return {"ok": False, "error": "MANIFEST_FILES_MISSING", "checked": 0}
        failures: list[dict[str, str]] = []
        checked = 0
        for rel, wanted in expected.items():
            path = ROOT / str(rel)
            if not path.is_file():
                failures.append({"file": str(rel), "reason": "MISSING"})
                continue
            checked += 1
            actual = _sha256(path)
            if actual != str(wanted).upper():
                failures.append({"file": str(rel), "reason": "HASH_MISMATCH"})
        return {"ok": not failures, "checked": checked, "failures": failures}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "checked": 0}


def _receipt() -> dict[str, Any]:
    if not RECEIPT.is_file():
        return {"ok": False, "present": False, "error": "INSTALL_RECEIPT_MISSING"}
    try:
        value = json.loads(RECEIPT.read_text(encoding="utf-8-sig"))
        if not isinstance(value, dict):
            raise ValueError("INSTALL_RECEIPT_NOT_OBJECT")
        return {
            "ok": bool(value.get("isolated_real_chat_to_terminal") and value.get("isolated_real_readback") and value.get("template_1_preflight") and value.get("template_2_preflight") and value.get("project_loop_preflight")),
            "present": True,
            "installed_at": value.get("installed_at", ""),
            "package_sha256": value.get("package_sha256", ""),
            "isolated_real_chat_to_terminal": bool(value.get("isolated_real_chat_to_terminal")),
            "isolated_real_readback": bool(value.get("isolated_real_readback")),
            "preflight_model": value.get("preflight_model", ""),
            "template_1_preflight": bool(value.get("template_1_preflight")),
            "template_2_preflight": bool(value.get("template_2_preflight")),
            "project_loop_preflight": bool(value.get("project_loop_preflight")),
            "source": value.get("source", ""),
        }
    except Exception as exc:
        return {"ok": False, "present": True, "error": str(exc)}


def run_system_test() -> dict[str, Any]:
    manifest = _manifest_check()
    database = db.status()
    counts = database.get("counts", {}) if isinstance(database, dict) else {}
    clean_lineage = True
    try:
        clean_lineage = str((db.row("SELECT value FROM meta WHERE key='legacy_imported'") or {}).get("value", "false")).lower() == "false"
    except Exception:
        clean_lineage = False
    templates = list_templates()
    templates_ok = len(templates) == 2 and {str(x.get("id")) for x in templates} == {"system-stress", "snake-game"}

    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    powershell = system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    powershell_ok = powershell.is_file() if os.name == "nt" else True

    token = ensure_session_token()
    security_ok = len(token) >= 32

    ollama_error = ""
    models: list[str] = []
    try:
        models = [str(m.get("name") or "") for m in ollama_models()]
    except Exception as exc:
        ollama_error = str(exc)
    ollama_ok = bool(models)
    preferred_ok = PREFERRED_MODEL in models

    receipt = _receipt()

    loop_tables = {str(x.get("name") or "") for x in db.rows("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('project_loop_settings','project_loop_runs','project_loop_steps')")}
    loop_storage_ok = loop_tables == {"project_loop_settings", "project_loop_runs", "project_loop_steps"}
    auto_model = ""
    auto_model_ok = False
    if models:
        try:
            auto_model = str(auto_select_model(models).get("model") or "")
            auto_model_ok = auto_model in models
        except Exception:
            auto_model_ok = False

    checks = {
        "source_manifest": bool(manifest.get("ok")),
        "database_integrity": bool(database.get("ok")),
        "clean_data_lineage": clean_lineage,
        "templates_installed": templates_ok,
        "session_security": security_ok,
        "windows_powershell": powershell_ok,
        "ollama_service": ollama_ok,
        "preferred_model": preferred_ok,
        "isolated_install_preflight": bool(receipt.get("ok")),
        "template_1_preflight": bool(receipt.get("template_1_preflight")),
        "template_2_preflight": bool(receipt.get("template_2_preflight")),
        "project_loop_storage": loop_storage_ok,
        "project_loop_auto_model": auto_model_ok,
        "project_loop_preflight": bool(receipt.get("project_loop_preflight")),
    }
    passed = sum(1 for value in checks.values() if value)
    failed = [name for name, value in checks.items() if not value]
    overall = "PASS" if not failed else "FAIL"

    return {
        "ok": not failed,
        "overall": overall,
        "build": BUILD,
        "checks": checks,
        "passed": passed,
        "total": len(checks),
        "failed": failed,
        "database": database,
        "manifest": manifest,
        "ollama": {
            "ok": ollama_ok,
            "preferred_model": PREFERRED_MODEL,
            "preferred_model_present": preferred_ok,
            "models": models,
            "error": ollama_error,
        },
        "security": {"ok": security_ok, "token_value_exposed": False},
        "powershell": {"ok": powershell_ok, "path": str(powershell)},
        "install_receipt": receipt,
        "project_loop": {"storage_ok": loop_storage_ok, "auto_model": auto_model, "auto_model_ok": auto_model_ok},
        "legacy_imported": False,
        "templates": templates,
    }
