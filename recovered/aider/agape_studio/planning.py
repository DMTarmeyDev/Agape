from __future__ import annotations

from typing import Any

from .ai import AIRouter
from .aider_tool import AiderService, aider_model_name


_DETERMINISTIC_WORDS = ('spell', 'spelling', 'format', 'formatting', 'whitespace', 'lint only', 'prettier')
_AIDER_WORDS = (
    'multi-file', 'multiple files', 'across the project', 'across project', 'codebase',
    'refactor', 'implement feature', 'build feature', 'fix tests', 'repair tests',
    'rename across', 'dependency', 'architecture change', 'project-wide', 'repo-wide',
)


class ToolPlanner:
    def __init__(self, ai: AIRouter, aider: AiderService):
        self.ai = ai
        self.aider = aider

    def plan(self, project_path: str | None, task: str, mode: str = 'auto') -> dict[str, Any]:
        text = str(task or '').strip()
        lower = text.lower()
        if not text:
            raise ValueError('TASK_REQUIRED')
        if any(word in lower for word in _DETERMINISTIC_WORDS):
            return {
                'ok': True,
                'tool': 'extension',
                'reason': 'Deterministic formatter/linter/spelling work should not consume an AI coding loop.',
                'requires_explicit_run': False,
            }
        recommendation = self.ai.recommend(text, mode)
        aider_status = self.aider.status()
        workspace = self.aider.workspace_status(project_path) if project_path else {'ok': False, 'error': 'NO_PROJECT'}
        complex_code = any(word in lower for word in _AIDER_WORDS) or sum(lower.count(x) for x in ('fix ', 'create ', 'change ', 'test ')) >= 2
        if complex_code and aider_status.get('ready') and workspace.get('ok') and workspace.get('clean'):
            return {
                'ok': True,
                'tool': 'aider',
                'reason': 'Repo-aware coding task: use Aider for repository mapping/edit mechanics while Agape retains model, scope and test control.',
                'requires_explicit_run': True,
                'provider': recommendation['provider'],
                'model': recommendation['model'],
                'tier': recommendation['tier'],
                'aider_model': aider_model_name(recommendation['provider'], recommendation['model'], recommendation['tier']),
                'workspace': workspace,
            }
        return {
            'ok': True,
            'tool': 'agape-ai',
            'reason': 'Use Agape AI directly; Aider is optional, unavailable, unsuitable, or the repository is not in a clean safe state.',
            'requires_explicit_run': False,
            'provider': recommendation['provider'],
            'model': recommendation['model'],
            'tier': recommendation['tier'],
            'aider_ready': bool(aider_status.get('ready')),
            'workspace': workspace,
        }
