from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .database import StudioDatabase


class TerminalError(ValueError):
    pass


class TerminalService:
    def __init__(self, db: StudioDatabase):
        self.db = db

    def run(self, project_path: str, argv: list[str], timeout: int = 30) -> dict[str, Any]:
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
            raise TerminalError('ARGV_REQUIRED')
        root = Path(project_path).resolve()
        if not root.is_dir():
            raise TerminalError('PROJECT_NOT_FOUND')
        result = subprocess.run(
            argv,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=max(1, min(int(timeout), 120)),
            shell=False,
        )
        payload = {
            'ok': result.returncode == 0,
            'exit_code': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'argv': argv,
        }
        self.db.add_terminal_history(str(root), argv, result.returncode, result.stdout, result.stderr)
        return payload
