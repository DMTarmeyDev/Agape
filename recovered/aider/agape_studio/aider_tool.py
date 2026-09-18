from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .database import StudioDatabase


_SECRET_PATTERNS = (
    (re.compile(r'(?i)(api[_-]?key\s*[=:]\s*)[^\s]+'), r'\1[REDACTED]'),
    (re.compile(r'(?i)(authorization\s*:\s*bearer\s+)[^\s]+'), r'\1[REDACTED]'),
    (re.compile(r'\bsk-[A-Za-z0-9_\-]{12,}\b'), '[REDACTED_API_KEY]'),
    (re.compile(r'\bsk-or-v1-[A-Za-z0-9_\-]{8,}\b'), '[REDACTED_OPENROUTER_KEY]'),
)


def redact(text: str) -> str:
    value = str(text or '')
    for pattern, replacement in _SECRET_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def aider_model_name(provider: str, model: str, tier: str = '') -> str:
    provider = str(provider or '').lower()
    model = str(model or '').strip()
    tier = str(tier or '').lower()
    if not model:
        raise ValueError('AIDER_MODEL_REQUIRED')
    if provider == 'ollama' or tier == 'local':
        return model if model.startswith('ollama_chat/') else 'ollama_chat/' + model
    if provider == 'openrouter-free' or tier == 'free-online':
        return model if model.startswith('openrouter/') else 'openrouter/' + model
    return model


@dataclass
class AiderStatus:
    installed: bool
    ready: bool
    command: list[str]
    version: str = ''
    detail: str = ''

    def public(self) -> dict[str, Any]:
        return {
            'installed': self.installed,
            'ready': self.ready,
            'command': list(self.command),
            'version': self.version,
            'detail': self.detail,
            'optional': True,
        }


class AiderService:
    """Optional, replaceable Aider CLI adapter.

    Agape keeps ownership of project scope, model choice, testing and release
    gates. Aider is only a specialist code-change engine inside a registered,
    clean git workspace. Secrets are inherited through environment variables,
    never placed on the command line.
    """

    def __init__(self, db: StudioDatabase):
        self.db = db

    def command(self) -> list[str]:
        if os.environ.get('AGAPE_AIDER_DISABLE') == '1':
            return []
        override = os.environ.get('AGAPE_AIDER_COMMAND_JSON')
        if override:
            try:
                value = json.loads(override)
                if isinstance(value, list) and value and all(isinstance(x, str) and x for x in value):
                    return value
            except json.JSONDecodeError:
                return []
        local_value = os.environ.get('LOCALAPPDATA')
        if local_value:
            managed = Path(local_value) / 'AgapeAIStudio' / 'tools' / 'aider-v0.86.0' / 'Scripts' / 'aider.exe'
            if managed.is_file():
                return [str(managed)]
        if os.environ.get('AGAPE_AIDER_ALLOW_PATH') == '1':
            exe = shutil.which('aider') or shutil.which('aider.exe') or shutil.which('aider.cmd')
            if exe:
                return [exe]
        return []

    def status(self) -> dict[str, Any]:
        command = self.command()
        if not command:
            return AiderStatus(False, False, [], '', 'AIDER_NOT_INSTALLED').public()
        try:
            proc = subprocess.run(command + ['--version'], capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError) as exc:
            return AiderStatus(True, False, command, '', redact(str(exc))).public()
        output = redact((proc.stdout + '\n' + proc.stderr).strip())[:1000]
        return AiderStatus(True, proc.returncode == 0, command, output.splitlines()[0] if output else '', output).public()

    @staticmethod
    def _git(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
        git = shutil.which('git')
        if not git:
            raise RuntimeError('GIT_NOT_INSTALLED')
        return subprocess.run([git, '-C', str(path), *args], capture_output=True, text=True, timeout=15)

    def workspace_status(self, project_path: str) -> dict[str, Any]:
        path = Path(project_path).expanduser().resolve()
        if not path.is_dir():
            return {'ok': False, 'git': False, 'clean': False, 'error': 'PROJECT_NOT_FOUND'}
        if not self.db.project_registered(str(path)):
            return {'ok': False, 'git': False, 'clean': False, 'error': 'PROJECT_NOT_REGISTERED'}
        try:
            inside = self._git(path, 'rev-parse', '--is-inside-work-tree')
            if inside.returncode != 0 or inside.stdout.strip().lower() != 'true':
                return {'ok': False, 'git': False, 'clean': False, 'error': 'AIDER_REQUIRES_GIT_REPOSITORY'}
            status = self._git(path, 'status', '--porcelain')
            if status.returncode != 0:
                return {'ok': False, 'git': True, 'clean': False, 'error': 'GIT_STATUS_FAILED'}
            dirty = [x for x in status.stdout.splitlines() if x.strip()]
            return {'ok': True, 'git': True, 'clean': not dirty, 'dirty_count': len(dirty), 'dirty': dirty[:50]}
        except Exception as exc:
            return {'ok': False, 'git': False, 'clean': False, 'error': redact(str(exc))}

    def build_command(self, project_path: str, task: str, provider: str, model: str, tier: str) -> dict[str, Any]:
        status = self.status()
        if not status['ready']:
            raise RuntimeError('AIDER_NOT_READY')
        ws = self.workspace_status(project_path)
        if not ws.get('ok'):
            raise RuntimeError(str(ws.get('error') or 'AIDER_WORKSPACE_NOT_READY'))
        if not ws.get('clean'):
            raise RuntimeError('AIDER_REQUIRES_CLEAN_GIT_WORKTREE')
        aider_model = aider_model_name(provider, model, tier)
        argv = list(status['command']) + [
            '--model', aider_model,
            '--message', str(task),
            '--no-auto-commits',
            '--no-gitignore',
            '--no-check-update',
            '--analytics-disable',
            '--disable-playwright',
            '--no-suggest-shell-commands',
            '--no-auto-lint',
            '--no-auto-test',
            '--no-browser',
            '--no-fancy-input',
            '--yes-always',
            '--encoding', 'utf-8',
        ]
        return {
            'ok': True,
            'workspace': str(Path(project_path).resolve()),
            'provider': provider,
            'model': model,
            'aider_model': aider_model,
            'argv': argv,
            'secrets_on_argv': False,
        }

    def run_task(self, project_path: str, task: str, provider: str, model: str, tier: str, timeout: int = 300) -> dict[str, Any]:
        plan = self.build_command(project_path, task, provider, model, tier)
        root = Path(project_path).resolve()
        before = self._git(root, 'status', '--porcelain').stdout.splitlines()
        started = time.perf_counter()
        try:
            proc = subprocess.run(
                plan['argv'],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=max(10, min(int(timeout), 1800)),
                env=os.environ.copy(),
            )
            exit_code = int(proc.returncode)
            stdout = redact(proc.stdout)[-12000:]
            stderr = redact(proc.stderr)[-12000:]
        except subprocess.TimeoutExpired as exc:
            exit_code = 124
            stdout = redact(exc.stdout or '')[-12000:]
            stderr = (redact(exc.stderr or '') + '\nAIDER_TIMEOUT').strip()[-12000:]
        duration_ms = int((time.perf_counter() - started) * 1000)
        after = self._git(root, 'status', '--porcelain').stdout.splitlines()
        changed = sorted({line[3:].strip() for line in after if len(line) >= 4})
        result = {
            'ok': exit_code == 0,
            'exit_code': exit_code,
            'provider': provider,
            'model': model,
            'aider_model': plan['aider_model'],
            'duration_ms': duration_ms,
            'stdout': stdout,
            'stderr': stderr,
            'changed_files': changed,
            'dirty_before': len([x for x in before if x.strip()]),
            'dirty_after': len([x for x in after if x.strip()]),
            'shell_used': False,
            'auto_commit': False,
        }
        self.db.record_tool_run('aider', str(root), str(task), 'PASS' if result['ok'] else 'FAIL', result)
        return result
