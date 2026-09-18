import tempfile
import unittest
from pathlib import Path

from agape_studio.database import StudioDatabase
from agape_studio.projects import ProjectError, ProjectService


class ProjectTests(unittest.TestCase):
    def test_project_create_read_write_and_escape_guard(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = StudioDatabase(root / 'db.sqlite3')
            svc = ProjectService(db, root / 'projects')
            project = svc.create('Demo')
            self.assertEqual(project['name'], 'Demo')
            svc.write_file(project['path'], 'src/main.py', 'print("ok")\n')
            self.assertEqual(svc.read_file(project['path'], 'src/main.py'), 'print("ok")\n')
            self.assertEqual((Path(project['path']) / 'src/main.py').read_bytes(), b'print("ok")\n')
            self.assertIn('src/main.py', svc.list_files(project['path']))
            with self.assertRaises(ProjectError):
                svc.write_file(project['path'], '../escape.txt', 'no')


if __name__ == '__main__': unittest.main()
