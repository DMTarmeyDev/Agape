from __future__ import annotations

import importlib.util
import os
import platform
import time
from typing import Any

from .coding_tools import tool_status, action as coding_action


def _pywinauto_ready() -> bool:
    return importlib.util.find_spec("pywinauto") is not None


def status() -> dict[str, Any]:
    tools = tool_status()
    managers = {x["id"]: x for x in tools.get("managers", [])}
    return {
        "ok": True,
        "platform": platform.system(),
        "windows": os.name == "nt",
        "pywinauto": _pywinauto_ready(),
        "vscode_ready": bool(managers.get("vscode", {}).get("ready")),
        "theia_ready": bool(managers.get("theia-full", {}).get("ready")),
        "summary": "Windows UI Automation bridge is ready." if os.name == "nt" and _pywinauto_ready() else "Install the Windows UI Automation support package to validate launched desktop coding tools." if os.name == "nt" else "Desktop UI probing runs only on Windows; browser QA remains available on this platform.",
    }


def probe(manager: str, workspace: str = "") -> dict[str, Any]:
    if os.name != "nt":
        raise RuntimeError("DESKTOP_QA_WINDOWS_ONLY")
    if not _pywinauto_ready():
        raise RuntimeError("PYWINAUTO_NOT_INSTALLED")
    manager = str(manager or "").strip().lower()
    if manager not in {"vscode", "theia-full"}:
        raise ValueError("DESKTOP_QA_MANAGER_MUST_BE_VSCODE_OR_THEIA_FULL")

    from pywinauto import Desktop

    launched = coding_action(manager, "open", workspace)
    pid = int(launched.get("pid") or 0)
    if not pid:
        raise RuntimeError("DESKTOP_PROCESS_ID_NOT_RETURNED")
    deadline = time.time() + 20
    windows = []
    while time.time() < deadline:
        windows = Desktop(backend="uia").windows(process=pid, visible_only=True)
        if windows:
            break
        time.sleep(0.5)
    if not windows:
        raise RuntimeError("DESKTOP_WINDOW_NOT_FOUND_AFTER_LAUNCH")
    titles = [w.window_text() for w in windows if w.window_text()]
    return {"ok": True, "manager": manager, "pid": pid, "window_count": len(windows), "titles": titles[:10], "workspace": workspace}
