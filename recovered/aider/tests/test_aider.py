from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from agape_studio.ai import AIRouter, FakeProvider
from agape_studio.aider_tool import AiderService, aider_model_name, redact
from agape_studio.database import StudioDatabase
from agape_studio.planning import ToolPlanner

ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / 'tests' / 'fake_aider_cli.py'


@contextmanager
def fake_aider_enabled():
    with patch.dict(os.environ, {
        'AGAPE_AIDER_COMMAND_JSON': json.dumps([sys.executable, str(FAKE)]),
        'AGAPE_AIDER_DISABLE': '0',
    }, clear=False):
        yield


def init_repo(root: Path) -> None:
    subprocess.run(['git', 'init'], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(['git', 'config', 'user.email', 'agape-tests@example.invalid'], cwd=root, check=True)
    subprocess.run(['git', 'config', 'user.name', 'Agape Tests'], cwd=root, check=True)
    (root / 'aider_target.py').write_text('print("before")\n', encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=root, check=True)
    subprocess.run(['git', 'commit', '-m', 'baseline'], cwd=root, check=True, capture_output=True, text=True)


class AiderToolTests(unittest.TestCase):
    def test_model_mapping(self):
        self.assertEqual(aider_model_name('ollama', 'qwen2.5-coder:7b', 'local'), 'ollama_chat/qwen2.5-coder:7b')
        self.assertEqual(aider_model_name('openrouter-free', 'acme/coder-free', 'free-online'), 'openrouter/acme/coder-free')

    def test_redaction(self):
        value = redact('api_key=secret12345 Authorization: Bearer abcdefgh sk-abcdefgh12345678')
        self.assertNotIn('secret12345', value)
        self.assertNotIn('abcdefgh12345678', value)
        self.assertIn('[REDACTED]', value)

    def test_aider_status_with_fake_command(self):
        with tempfile.TemporaryDirectory() as td, fake_aider_enabled():
            service = AiderService(StudioDatabase(Path(td) / 'db.sqlite3'))
            status = service.status()
            self.assertTrue(status['ready'])
            self.assertIn('0.86.0-test', status['version'])

    def test_planner_uses_extension_for_formatting(self):
        with tempfile.TemporaryDirectory() as td:
            db = StudioDatabase(Path(td) / 'db.sqlite3')
            router = AIRouter(db, [FakeProvider(provider_id='ollama', model_name='qwen2.5-coder:7b', tier='local')])
            planner = ToolPlanner(router, AiderService(db))
            plan = planner.plan(None, 'format this Python file')
            self.assertEqual(plan['tool'], 'extension')

    def test_planner_uses_aider_for_clean_repo_wide_task(self):
        with tempfile.TemporaryDirectory() as td, fake_aider_enabled():
            root = Path(td) / 'repo'; root.mkdir(); init_repo(root)
            db = StudioDatabase(Path(td) / 'db.sqlite3'); db.upsert_project(root.name, str(root))
            router = AIRouter(db, [FakeProvider(provider_id='ollama', model_name='qwen2.5-coder:7b', tier='local')])
            planner = ToolPlanner(router, AiderService(db))
            plan = planner.plan(str(root), 'refactor this codebase across multiple files and fix tests')
            self.assertEqual(plan['tool'], 'aider')
            self.assertEqual(plan['aider_model'], 'ollama_chat/qwen2.5-coder:7b')
            self.assertTrue(plan['requires_explicit_run'])

    def test_dirty_repo_blocks_aider_route(self):
        with tempfile.TemporaryDirectory() as td, fake_aider_enabled():
            root = Path(td) / 'repo'; root.mkdir(); init_repo(root)
            (root / 'aider_target.py').write_text('dirty\n', encoding='utf-8')
            db = StudioDatabase(Path(td) / 'db.sqlite3'); db.upsert_project(root.name, str(root))
            router = AIRouter(db, [FakeProvider(provider_id='ollama', model_name='qwen2.5-coder:7b', tier='local')])
            plan = ToolPlanner(router, AiderService(db)).plan(str(root), 'refactor this codebase across multiple files')
            self.assertEqual(plan['tool'], 'agape-ai')
            self.assertFalse(plan['workspace']['clean'])

    def test_run_aider_changes_only_registered_clean_repo_and_records_evidence(self):
        with tempfile.TemporaryDirectory() as td, fake_aider_enabled():
            root = Path(td) / 'repo'; root.mkdir(); init_repo(root)
            db = StudioDatabase(Path(td) / 'db.sqlite3'); db.upsert_project(root.name, str(root))
            service = AiderService(db)
            result = service.run_task(str(root), 'implement feature across project', 'ollama', 'qwen2.5-coder:7b', 'local', 30)
            self.assertTrue(result['ok'])
            self.assertIn('aider_target.py', result['changed_files'])
            self.assertFalse(result['shell_used'])
            self.assertFalse(result['auto_commit'])
            self.assertIn('# AIDER_EDIT_PASS', (root / 'aider_target.py').read_text(encoding='utf-8'))
            history = db.tool_run_history()
            self.assertEqual(history[0]['tool'], 'aider')
            self.assertEqual(history[0]['status'], 'PASS')

    def test_unregistered_repo_is_blocked(self):
        with tempfile.TemporaryDirectory() as td, fake_aider_enabled():
            root = Path(td) / 'repo'; root.mkdir(); init_repo(root)
            db = StudioDatabase(Path(td) / 'db.sqlite3')
            service = AiderService(db)
            with self.assertRaisesRegex(RuntimeError, 'PROJECT_NOT_REGISTERED'):
                service.build_command(str(root), 'refactor codebase', 'ollama', 'qwen2.5-coder:7b', 'local')

    def test_aider_is_optional_and_falls_back(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {'AGAPE_AIDER_DISABLE': '1'}, clear=False):
            root = Path(td) / 'repo'; root.mkdir(); init_repo(root)
            db = StudioDatabase(Path(td) / 'db.sqlite3'); db.upsert_project(root.name, str(root))
            router = AIRouter(db, [FakeProvider(provider_id='ollama', model_name='qwen2.5-coder:7b', tier='local')])
            planner = ToolPlanner(router, AiderService(db))
            plan = planner.plan(str(root), 'refactor this codebase across multiple files')
            self.assertEqual(plan['tool'], 'agape-ai')
            self.assertFalse(plan['aider_ready'])

    def test_managed_aider_precedes_path_copy(self):
        with tempfile.TemporaryDirectory() as td:
            local = Path(td)
            managed = local / 'AgapeAIStudio' / 'tools' / 'aider-v0.86.0' / 'Scripts' / 'aider.exe'
            managed.parent.mkdir(parents=True)
            managed.write_bytes(b'placeholder')
            db = StudioDatabase(local / 'db.sqlite3')
            with patch.dict(os.environ, {'LOCALAPPDATA': str(local), 'AGAPE_AIDER_DISABLE': '0'}, clear=False), patch('agape_studio.aider_tool.shutil.which', return_value='C:/Users/test/.local/bin/aider.exe'):
                os.environ.pop('AGAPE_AIDER_COMMAND_JSON', None)
                os.environ.pop('AGAPE_AIDER_ALLOW_PATH', None)
                self.assertEqual(AiderService(db).command(), [str(managed)])

    def test_unmanaged_path_aider_is_ignored_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            local = Path(td)
            db = StudioDatabase(local / 'db.sqlite3')
            with patch.dict(os.environ, {'LOCALAPPDATA': str(local), 'AGAPE_AIDER_DISABLE': '0'}, clear=False), patch('agape_studio.aider_tool.shutil.which', return_value='C:/Users/test/.local/bin/aider.exe'):
                os.environ.pop('AGAPE_AIDER_COMMAND_JSON', None)
                os.environ.pop('AGAPE_AIDER_ALLOW_PATH', None)
                self.assertEqual(AiderService(db).command(), [])


if __name__ == '__main__':
    unittest.main()
