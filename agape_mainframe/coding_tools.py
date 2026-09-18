from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import webbrowser
from pathlib import Path
from typing import Any

THEIA_DOWNLOAD_URL = "https://www.eclipse.org/downloads/download.php?file=%2Ftheia%2Fide%2Flatest%2Fwindows%2FTheiaIDESetup.exe&r=1"
THEIA_HOME_URL = "https://theia-ide.org/"
OPENHANDS_DOCS_URL = "https://docs.openhands.dev/openhands/usage/cli/quick-start"
OPEN_INTERPRETER_URL = "https://osp.fyi/open-interpreter"

AGENTS = [
    {"id":"auto","name":"Auto choose","summary":"Agape chooses an available coding agent for the task."},
    {"id":"agape-native","name":"Agape Native","summary":"Use Agape's own development workflow, tests and rollback."},
    {"id":"aider","name":"Aider","summary":"Repository-aware coding assistant with Agape-owned validation."},
    {"id":"openhands","name":"OpenHands","summary":"Agentic coding environment; on Windows Agape installs and runs it inside WSL."},
    {"id":"open-interpreter","name":"Open Interpreter","summary":"Experimental harness-oriented coding engine / Codex-compatible execution option."},
    {"id":"compare","name":"Compare engines","summary":"Keep the task/model fixed and compare available coding agents in isolated runs."},
]
MANAGERS = [
    {"id":"agape","name":"Agape workspace","summary":"Use Agape without requiring a full external IDE."},
    {"id":"theia-lite","name":"Theia Lite","summary":"Reserved for the trimmed embedded Theia workspace; full Theia remains optional."},
    {"id":"theia-full","name":"Theia Full","summary":"Open-source desktop IDE with VS Code extension compatibility through Open VSX."},
    {"id":"vscode","name":"VS Code","summary":"Use the installed Visual Studio Code desktop application."},
]
MODEL_MODES = [
    {"id":"auto-coding","name":"Auto - coding specialist","summary":"Prefer a coding-specialist model and escalate only when needed."},
    {"id":"local-first","name":"Local/open model first","summary":"Prefer an installed open coding model before cloud fallback."},
    {"id":"cloud-first","name":"Cloud coding model first","summary":"Prefer a connected cloud coding model."},
    {"id":"manual","name":"Manual model choice","summary":"Use a model selected in Advanced AI settings."},
]


def _which(*names: str) -> str:
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return ""


def _exists(candidates: list[str]) -> str:
    for raw in candidates:
        if not raw:
            continue
        p = Path(os.path.expandvars(raw))
        if p.exists():
            return str(p)
    return ""


def _run(args: list[str], timeout: int = 60) -> tuple[bool, str]:
    try:
        cp = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=timeout)
        text = ((cp.stdout or "") + "\n" + (cp.stderr or "")).strip()
        return cp.returncode == 0, text[-6000:]
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _wsl() -> str:
    return _which("wsl", "wsl.exe")


def _wsl_distros() -> list[str]:
    wsl = _wsl()
    if not wsl:
        return []
    ok, text = _run([wsl, "-l", "-q"], timeout=15)
    if not ok:
        return []
    return [x.strip().replace("\x00", "") for x in text.splitlines() if x.strip().replace("\x00", "")]


def _preferred_wsl_distro() -> str:
    rows = _wsl_distros()
    for name in rows:
        if name.lower() == "ubuntu":
            return name
    for name in rows:
        if "ubuntu" in name.lower():
            return name
    return rows[0] if rows else ""


def _wsl_bash(command: str, timeout: int = 120, distro: str = "") -> tuple[bool, str]:
    wsl = _wsl()
    if not wsl:
        return False, "WSL_NOT_INSTALLED"
    distro = distro or _preferred_wsl_distro()
    if not distro:
        return False, "WSL_DISTRO_NOT_INSTALLED"
    return _run([wsl, "-d", distro, "--", "bash", "-lc", command], timeout=timeout)


def _openhands_status() -> dict[str, Any]:
    if os.name != "nt":
        path = _which("openhands")
        return {"ready": bool(path), "path": path, "mode": "native", "detail": path or "OpenHands CLI not installed"}
    wsl = _wsl()
    distro = _preferred_wsl_distro()
    if not wsl:
        return {"ready": False, "path": "", "mode": "wsl", "detail": "WSL is not installed", "needs": "wsl"}
    if not distro:
        return {"ready": False, "path": "", "mode": "wsl", "detail": "WSL is installed but no Linux distribution is available", "needs": "ubuntu"}
    ok, detail = _wsl_bash('export PATH="$HOME/.local/bin:$PATH"; command -v openhands && openhands --version', timeout=30, distro=distro)
    path = ""
    if ok:
        path = next((line.strip() for line in detail.splitlines() if "/openhands" in line or line.strip().endswith("openhands")), "openhands")
    return {"ready": ok, "path": path, "mode": "wsl", "distro": distro, "detail": detail or "OpenHands not installed in WSL"}


def tool_status() -> dict[str, Any]:
    local = os.environ.get("LOCALAPPDATA", "")
    pf = os.environ.get("ProgramFiles", "")
    pf86 = os.environ.get("ProgramFiles(x86)", "")
    vscode = _which("code") or _exists([
        f"{local}\\Programs\\Microsoft VS Code\\Code.exe",
        f"{pf}\\Microsoft VS Code\\Code.exe",
        f"{pf86}\\Microsoft VS Code\\Code.exe",
    ])
    theia = _exists([
        f"{local}\\Programs\\Theia IDE\\Theia IDE.exe",
        f"{local}\\Programs\\TheiaIDE\\Theia IDE.exe",
        f"{pf}\\Theia IDE\\Theia IDE.exe",
        f"{pf86}\\Theia IDE\\Theia IDE.exe",
    ])
    oh = _openhands_status()
    return {
        "ok": True,
        "agents": [
            {**AGENTS[0], "ready": True},
            {**AGENTS[1], "ready": True},
            {**AGENTS[2], "ready": bool(_which("aider")), "path": _which("aider")},
            {**AGENTS[3], **oh, "windows_note": "OpenHands CLI requires WSL on Windows; Agape can set it up from Settings."},
            {**AGENTS[4], "ready": bool(_which("open-interpreter", "interpreter")), "path": _which("open-interpreter", "interpreter"), "experimental": True},
            {**AGENTS[5], "ready": True},
        ],
        "managers": [
            {**MANAGERS[0], "ready": True},
            {**MANAGERS[1], "ready": False, "planned": True},
            {**MANAGERS[2], "ready": bool(theia), "path": theia, "download_url": THEIA_DOWNLOAD_URL},
            {**MANAGERS[3], "ready": bool(vscode), "path": vscode},
        ],
        "model_modes": MODEL_MODES,
    }


def _launch(path: str, workspace: str = "") -> dict[str, Any]:
    if not path:
        raise RuntimeError("TOOL_NOT_INSTALLED")
    args = [path]
    if workspace:
        p = Path(workspace).expanduser()
        if p.exists():
            args.append(str(p))
    proc = subprocess.Popen(args, close_fds=True)
    return {"ok": True, "action": "open", "path": path, "workspace": workspace, "pid": proc.pid}


def _install_openhands() -> dict[str, Any]:
    if os.name != "nt":
        uv = _which("uv")
        if not uv:
            return {"ok": False, "tool": "openhands", "error": "UV_NOT_FOUND", "message": "Install uv first, then retry OpenHands setup."}
        ok, detail = _run([uv, "tool", "install", "openhands", "--python", "3.12"], timeout=1200)
        if not ok and "already installed" in detail.lower():
            ok, detail = _run([uv, "tool", "upgrade", "openhands", "--python", "3.12"], timeout=1200)
        return {"ok": ok, "tool": "openhands", "action": "install", "output": detail, "status": _openhands_status()}

    wsl = _wsl()
    if not wsl:
        return {"ok": False, "tool": "openhands", "error": "WSL_NOT_FOUND", "message": "OpenHands requires WSL on Windows. Install WSL/Ubuntu, restart Windows if requested, then press Install again."}
    distro = _preferred_wsl_distro()
    if not distro:
        ok, detail = _run([wsl, "--install", "-d", "Ubuntu", "--no-launch"], timeout=1800)
        return {
            "ok": False,
            "tool": "openhands",
            "error": "WSL_UBUNTU_INSTALL_PENDING" if ok else "WSL_UBUNTU_INSTALL_FAILED",
            "message": "Ubuntu installation was requested. A restart or first-run Linux setup may be required before OpenHands can be installed.",
            "output": detail,
            "requires_restart_or_first_run": True,
        }
    command = (
        'set -e; export PATH="$HOME/.local/bin:$PATH"; '
        'if ! command -v curl >/dev/null 2>&1; then sudo apt-get update && sudo apt-get install -y curl ca-certificates; fi; '
        'if ! command -v uv >/dev/null 2>&1; then curl -LsSf https://astral.sh/uv/install.sh | sh; fi; '
        'export PATH="$HOME/.local/bin:$PATH"; '
        'if uv tool list 2>/dev/null | grep -q "^openhands "; then uv tool upgrade openhands --python 3.12; '
        'else uv tool install openhands --python 3.12; fi; '
        'openhands --version'
    )
    ok, detail = _wsl_bash(command, timeout=1800, distro=distro)
    return {"ok": ok, "tool": "openhands", "action": "install", "distro": distro, "output": detail, "status": _openhands_status()}


def _windows_to_wsl_path(workspace: str, distro: str) -> str:
    if not workspace:
        return "~"
    ok, detail = _wsl_bash(f"wslpath -a {shlex.quote(str(Path(workspace).expanduser()))}", timeout=20, distro=distro)
    if ok and detail.strip():
        return detail.splitlines()[-1].strip()
    return "~"


def _open_openhands(workspace: str = "") -> dict[str, Any]:
    st = _openhands_status()
    if not st.get("ready"):
        raise RuntimeError("OPENHANDS_NOT_READY: Use Settings > Coding tools > Install OpenHands first.")
    if os.name != "nt":
        return _launch(str(st.get("path") or "openhands"), workspace)
    wsl = _wsl()
    distro = str(st.get("distro") or _preferred_wsl_distro())
    target = _windows_to_wsl_path(workspace, distro)
    command = f'cd {shlex.quote(target)} 2>/dev/null || cd ~; export PATH="$HOME/.local/bin:$PATH"; exec openhands'
    # Launch a visible WSL terminal so the interactive OpenHands CLI remains usable.
    proc = subprocess.Popen(["cmd.exe", "/c", "start", "", wsl, "-d", distro, "--", "bash", "-lc", command], close_fds=True)
    return {"ok": True, "action": "open", "tool": "openhands", "workspace": workspace, "distro": distro, "pid": proc.pid}


def action(tool: str, verb: str, workspace: str = "") -> dict[str, Any]:
    tool = str(tool or "").strip().lower()
    verb = str(verb or "").strip().lower()
    status = tool_status()
    managers = {x["id"]: x for x in status["managers"]}
    agents = {x["id"]: x for x in status["agents"]}
    if tool == "vscode":
        if verb == "open":
            return _launch(str(managers["vscode"].get("path") or ""), workspace)
        if verb == "download":
            webbrowser.open("https://code.visualstudio.com/download")
            return {"ok": True, "action": "download", "tool": "vscode", "message": "Opened the official VS Code download page."}
    if tool == "theia-full":
        if verb == "open":
            return _launch(str(managers["theia-full"].get("path") or ""), workspace)
        if verb == "download":
            webbrowser.open(THEIA_DOWNLOAD_URL)
            return {"ok": True, "action": "download", "tool": "theia-full", "message": "Opened the official Eclipse Theia Windows download."}
    if tool == "openhands":
        if verb == "install":
            return _install_openhands()
        if verb == "open":
            return _open_openhands(workspace)
        if verb in {"download", "help"}:
            webbrowser.open(OPENHANDS_DOCS_URL)
            return {"ok": True, "action": "help", "tool": "openhands", "message": "Opened official OpenHands setup instructions."}
    if tool == "open-interpreter" and verb in {"download", "help"}:
        webbrowser.open(OPEN_INTERPRETER_URL)
        return {"ok": True, "action": "help", "tool": "open-interpreter", "message": "Opened the Open Interpreter project page."}
    if tool == "aider" and verb == "open":
        return _launch(str(agents["aider"].get("path") or ""), workspace)
    raise ValueError("CODING_TOOL_ACTION_NOT_SUPPORTED")
