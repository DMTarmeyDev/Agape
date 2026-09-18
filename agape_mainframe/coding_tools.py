from __future__ import annotations
import os, shutil, subprocess, webbrowser
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
    {"id":"openhands","name":"OpenHands","summary":"Agentic coding environment; on Windows its CLI is designed to run through WSL."},
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
        p=shutil.which(n)
        if p:return p
    return ""

def _exists(candidates: list[str]) -> str:
    for raw in candidates:
        if not raw:continue
        p=Path(os.path.expandvars(raw))
        if p.exists():return str(p)
    return ""

def tool_status() -> dict[str, Any]:
    local=os.environ.get("LOCALAPPDATA",""); pf=os.environ.get("ProgramFiles",""); pf86=os.environ.get("ProgramFiles(x86)","")
    vscode=_which("code") or _exists([
        f"{local}\\Programs\\Microsoft VS Code\\Code.exe",
        f"{pf}\\Microsoft VS Code\\Code.exe",
        f"{pf86}\\Microsoft VS Code\\Code.exe",
    ])
    theia=_exists([
        f"{local}\\Programs\\Theia IDE\\Theia IDE.exe",
        f"{local}\\Programs\\TheiaIDE\\Theia IDE.exe",
        f"{pf}\\Theia IDE\\Theia IDE.exe",
        f"{pf86}\\Theia IDE\\Theia IDE.exe",
    ])
    return {
        "ok":True,
        "agents":[
            {**AGENTS[0],"ready":True},
            {**AGENTS[1],"ready":True},
            {**AGENTS[2],"ready":bool(_which("aider")),"path":_which("aider")},
            {**AGENTS[3],"ready":bool(_which("openhands")),"path":_which("openhands"),"windows_note":"OpenHands CLI requires WSL on Windows."},
            {**AGENTS[4],"ready":bool(_which("open-interpreter","interpreter")),"path":_which("open-interpreter","interpreter"),"experimental":True},
            {**AGENTS[5],"ready":True},
        ],
        "managers":[
            {**MANAGERS[0],"ready":True},
            {**MANAGERS[1],"ready":False,"planned":True},
            {**MANAGERS[2],"ready":bool(theia),"path":theia,"download_url":THEIA_DOWNLOAD_URL},
            {**MANAGERS[3],"ready":bool(vscode),"path":vscode},
        ],
        "model_modes":MODEL_MODES,
    }

def _launch(path: str, workspace: str="") -> dict[str, Any]:
    if not path: raise RuntimeError("TOOL_NOT_INSTALLED")
    args=[path]
    if workspace:
        p=Path(workspace).expanduser()
        if p.exists():args.append(str(p))
    proc=subprocess.Popen(args, close_fds=True)
    return {"ok":True,"action":"open","path":path,"workspace":workspace,"pid":proc.pid}

def action(tool: str, verb: str, workspace: str="") -> dict[str, Any]:
    tool=str(tool or "").strip().lower(); verb=str(verb or "").strip().lower()
    status=tool_status(); managers={x["id"]:x for x in status["managers"]}; agents={x["id"]:x for x in status["agents"]}
    if tool=="vscode":
        if verb=="open":return _launch(str(managers["vscode"].get("path") or ""),workspace)
        if verb=="download":
            webbrowser.open("https://code.visualstudio.com/download")
            return {"ok":True,"action":"download","tool":"vscode","message":"Opened the official VS Code download page."}
    if tool=="theia-full":
        if verb=="open":return _launch(str(managers["theia-full"].get("path") or ""),workspace)
        if verb=="download":
            webbrowser.open(THEIA_DOWNLOAD_URL)
            return {"ok":True,"action":"download","tool":"theia-full","message":"Opened the official Eclipse Theia Windows download."}
    if tool=="openhands" and verb in {"download","help"}:
        webbrowser.open(OPENHANDS_DOCS_URL)
        return {"ok":True,"action":"help","tool":"openhands","message":"Opened official OpenHands setup instructions."}
    if tool=="open-interpreter" and verb in {"download","help"}:
        webbrowser.open(OPEN_INTERPRETER_URL)
        return {"ok":True,"action":"help","tool":"open-interpreter","message":"Opened the Open Interpreter project page."}
    if tool=="aider" and verb=="open":return _launch(str(agents["aider"].get("path") or ""),workspace)
    raise ValueError("CODING_TOOL_ACTION_NOT_SUPPORTED")
