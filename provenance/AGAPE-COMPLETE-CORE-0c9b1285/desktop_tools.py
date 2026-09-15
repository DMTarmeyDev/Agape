from __future__ import annotations
from pathlib import Path
import shutil
import subprocess

def validate_project_workspace(value: str) -> Path:
    raw = str(value or "").strip().strip('"')
    if not raw:
        raise ValueError("PROJECT_WORKSPACE_REQUIRED")
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("PROJECT_WORKSPACE_NOT_FOUND=" + str(root))
    if root.parent == root or root == Path.home().resolve():
        raise ValueError("PROJECT_WORKSPACE_ROOT_NOT_ALLOWED")
    if root.is_symlink():
        raise ValueError("PROJECT_WORKSPACE_SYMLINK_NOT_ALLOWED")
    return root

def vscode_command(workspace: str) -> list[str]:
    root = validate_project_workspace(workspace)
    exe = shutil.which("code") or shutil.which("code.cmd") or "code"
    return [exe, str(root)]

def open_vscode(workspace: str, dry_run: bool = True) -> dict:
    cmd = vscode_command(workspace)
    if dry_run:
        return {"ok": True, "dry_run": True, "command": cmd, "workspace": cmd[-1]}
    try:
        subprocess.Popen(cmd, cwd=cmd[-1])
    except OSError as exc:
        raise ValueError("VSCODE_START_FAILED=" + str(exc)) from None
    return {"ok": True, "dry_run": False, "command": cmd, "workspace": cmd[-1]}
