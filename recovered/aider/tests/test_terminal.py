import sys
import tempfile
import unittest
from pathlib import Path

from agape_studio.database import StudioDatabase
from agape_studio.terminal import TerminalService
from agape_studio.testing import TestService


class TerminalTests(unittest.TestCase):
    def test_terminal_and_test_service(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = StudioDatabase(root / 'db.sqlite3')
            terminal = TerminalService(db)
            result = terminal.run(str(root), [sys.executable, '-c', 'print("TERMINAL_OK")'])
            self.assertEqual(result['exit_code'], 0)
            self.assertIn('TERMINAL_OK', result['stdout'])
            tested = TestService(terminal).run(str(root), [sys.executable, '-c', 'raise SystemExit(0)'])
            self.assertEqual(tested['status'], 'PASS')
            self.assertEqual(db.table_counts()['terminal_history'], 2)


if __name__ == '__main__': unittest.main()
