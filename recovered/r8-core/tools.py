from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import MAX_COMMAND_CHARS, TERMINAL_TIMEOUT_SECONDS
from db import terminal_job_create, terminal_job_finish

ACTION_RE = re.compile(
    r"\b(create|make|write|edit|modify|update|run|execute|test|check|inspect|read|open|restart|fix|repair|install|delete|remove|start|build)\b",
    re.I,
)
DENY_RE = re.compile(
    r"\b(?:do\s+not|don'?t|dont|never)\s+(?:actually\s+)?(?:run|execute|perform|create|make|write|edit|modify|update|delete|remove|install|start|build|open|read|test|check|inspect|restart|fix|repair)\b"
    r"|\b(?:no|without)\s+(?:actual\s+)?(?:execution|executing|running|changes?)\b"
    r"|\b(?:explain|describe|show|print)\s+only\b",
    re.I,
)

# These commands are never auto-executed by the AI bridge.
PROTECTED_PATTERNS = [
    r"\b(format|diskpart|bcdedit|manage-bde|reagentc)\b",
    r"\b(shutdown|restart-computer|stop-computer)\b",
    r"\b(remove-partition|clear-disk|initialize-disk|set-partition)\b",
    r"\b(reg\s+delete|remove-itemproperty|set-itemproperty)\b",
    r"\b(net\s+user|net\s+localgroup|sc\.exe|schtasks)\b",
    r"\b(stop-process)\b",
    r"\b(-verb\s+runas|runas\.exe)\b",
]
SOURCE_CHANGE_RE = re.compile(r"(?i)(app\.py|config\.py|tools\.py|providers\.py|orchestrator\.py|security\.py|db\.py|system_test\.py|project_loop\.py|workflows\.py|selftest\.py|manifest\.json|index\.html|first-run\.html|start-dmt-second-brain\.ps1)")
INFO_ONLY_RE = re.compile(
    r"\b(?:how\s+(?:do|can|would)\s+i|show\s+me\s+how|tell\s+me\s+how|what\s+(?:command|code|script)\b|which\s+(?:command|code|script)\b|give\s+me\s+(?:the\s+)?(?:powershell\s+)?(?:command|code|script)\b|explain\s+how|describe\s+how|what\s+would\s+happen)\b",
    re.I,
)


@dataclass
class ParsedToolCall:
    name: str
    arguments: dict[str, Any]
    source_format: str


@dataclass
class Analysis:
    allowed: bool
    risk: str
    reason: str


def explicit_action(text: str) -> bool:
    text = str(text or "").strip()
    if not text:
        return False
    if DENY_RE.search(text):
        return False
    # Questions asking for instructions/code are informational, not permission to act.
    if INFO_ONLY_RE.search(text):
        return False
    return bool(ACTION_RE.search(text))


def parse_tool_call(text: str) -> ParsedToolCall | None:
    raw = str(text or "").strip()
    if not raw:
        return None

    source_format = "json"
    candidate = raw

    # Safe normalization: accept only ONE fenced JSON object occupying the entire response.
    fenced = re.fullmatch(r"```(?:json)?\s*(\{.*\})\s*```", raw, flags=re.I | re.S)
    if fenced:
        candidate = fenced.group(1).strip()
        source_format = "fenced_json"

    # Never scrape JSON out of arbitrary prose.
    try:
        obj = json.loads(candidate)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    if set(obj.keys()) != {"name", "arguments"}:
        return None
    if str(obj.get("name") or "").strip().lower() not in {"shell", "terminal_run"}:
        return None
    args = obj.get("arguments")
    if not isinstance(args, dict):
        return None
    if set(args.keys()) not in ({"cmd"}, {"command"}):
        return None
    command = str(args.get("cmd") if "cmd" in args else args.get("command") or "").strip()
    if not command:
        return None
    if len(command) > MAX_COMMAND_CHARS:
        return None
    return ParsedToolCall("shell", {"cmd": command}, source_format)


def analyze_command(command: str) -> Analysis:
    command = str(command or "").strip()
    if not command:
        return Analysis(False, "blocked", "EMPTY_COMMAND")
    if len(command) > MAX_COMMAND_CHARS:
        return Analysis(False, "blocked", "COMMAND_TOO_LONG")
    for pattern in PROTECTED_PATTERNS:
        if re.search(pattern, command, re.I):
            return Analysis(False, "protected", "PROTECTED_COMMAND")
    if SOURCE_CHANGE_RE.search(command):
        return Analysis(False, "source_change", "CORE_SOURCE_CHANGE_BLOCKED")
    return Analysis(True, "normal", "SAFE_NON_ADMIN_COMMAND")


def run_powershell(command: str, project_id: int | None = None) -> dict[str, Any]:
    analysis = analyze_command(command)
    if not analysis.allowed:
        return {
            "ok": False,
            "executed": False,
            "risk": analysis.risk,
            "reason": analysis.reason,
            "command": command,
        }

    job_id = "TERM-" + uuid.uuid4().hex[:16].upper()
    terminal_job_create(job_id, project_id, command, analysis.risk)
    exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    try:
        cp = subprocess.run(
            [exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=TERMINAL_TIMEOUT_SECONDS,
            cwd=str(Path.home()),
        )
        stdout = cp.stdout[-20000:]
        stderr = cp.stderr[-20000:]
        terminal_job_finish(job_id, int(cp.returncode), stdout, stderr)
        return {
            "ok": cp.returncode == 0,
            "executed": True,
            "job_id": job_id,
            "exit_code": int(cp.returncode),
            "stdout": stdout,
            "stderr": stderr,
            "risk": analysis.risk,
            "reason": analysis.reason,
        }
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or "")[-20000:] if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "")[-20000:] if isinstance(exc.stderr, str) else ""
        terminal_job_finish(job_id, 124, stdout, stderr + "\nTIMEOUT")
        return {
            "ok": False,
            "executed": True,
            "job_id": job_id,
            "exit_code": 124,
            "stdout": stdout,
            "stderr": stderr + "\nTIMEOUT",
            "risk": analysis.risk,
            "reason": "TERMINAL_TIMEOUT",
        }
