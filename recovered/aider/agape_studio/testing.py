from __future__ import annotations

from .terminal import TerminalService


class TestService:
    def __init__(self, terminal: TerminalService):
        self.terminal = terminal

    def run(self, project_path: str, argv: list[str], timeout: int = 60):
        result = self.terminal.run(project_path, argv, timeout)
        return {
            **result,
            'status': 'PASS' if result['exit_code'] == 0 else 'FAIL',
        }
