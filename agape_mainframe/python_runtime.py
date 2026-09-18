from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _same_executable(candidate: str) -> bool:
    try:
        return Path(candidate).resolve() == Path(sys.executable).resolve()
    except Exception:
        return candidate == sys.executable


def _candidate_commands() -> list[list[str]]:
    explicit = str(os.environ.get("AGAPE_EXTERNAL_PYTHON") or "").strip()
    out: list[list[str]] = []
    if explicit:
        out.append([explicit])
    if os.name == "nt":
        py = shutil.which("py") or shutil.which("py.exe")
        if py:
            out.append([py, "-3"])
        for name in ("python", "python.exe", "python3"):
            found = shutil.which(name)
            if found:
                out.append([found])
    else:
        for name in ("python3", "python"):
            found = shutil.which(name)
            if found:
                out.append([found])
    unique: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for cmd in out:
        key = tuple(cmd)
        if key not in seen:
            seen.add(key)
            unique.append(cmd)
    return unique


@lru_cache(maxsize=1)
def external_python_command() -> tuple[str, ...] | None:
    """Return a usable external Python command for optional developer tooling.

    In a PyInstaller build ``sys.executable`` is Agape itself, so it must never be
    used as ``python -m pip``. This routine locates and validates a separate Python.
    """
    if not is_frozen():
        return (sys.executable,)
    for cmd in _candidate_commands():
        if len(cmd) == 1 and _same_executable(cmd[0]):
            continue
        try:
            probe = subprocess.run(
                [*cmd, "-c", "import sys;print(sys.executable);print(sys.version.split()[0])"],
                capture_output=True,
                text=True,
                timeout=8,
            )
            if probe.returncode == 0 and probe.stdout.strip():
                return tuple(cmd)
        except Exception:
            continue
    return None


def pip_install_command(package: str, *, user: bool = False) -> list[str]:
    command = external_python_command()
    if not command:
        raise RuntimeError(
            "EXTERNAL_PYTHON_REQUIRED: this packaged Agape build cannot use itself as a Python interpreter. "
            "Install Python 3 or set AGAPE_EXTERNAL_PYTHON, then retry this optional developer-tool install."
        )
    args = [*command, "-m", "pip", "install", "--disable-pip-version-check"]
    if user:
        args.append("--user")
    args.append(str(package))
    return args


def runtime_detail() -> dict[str, object]:
    if not is_frozen():
        return {
            "ready": True,
            "path": sys.executable,
            "version": platform.python_version(),
            "packaged": False,
            "external": False,
        }
    command = external_python_command()
    if not command:
        return {
            "ready": False,
            "path": "",
            "version": "",
            "packaged": True,
            "external": True,
            "note": "Agape is packaged; no separate Python installation was detected.",
        }
    try:
        probe = subprocess.run(
            [*command, "-c", "import sys;print(sys.executable);print(sys.version.split()[0])"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        lines = [x.strip() for x in probe.stdout.splitlines() if x.strip()]
    except Exception:
        lines = []
    return {
        "ready": True,
        "path": lines[0] if lines else command[0],
        "version": lines[1] if len(lines) > 1 else "",
        "packaged": True,
        "external": True,
    }
