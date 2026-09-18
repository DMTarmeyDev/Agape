import unittest
from pathlib import Path

class R4AutoChooseUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html=Path(__file__).with_name('index.html').read_text(encoding='utf-8')
        cls.app=Path(__file__).with_name('app.py').read_text(encoding='utf-8')
    def test_auto_choose_is_button_not_dropdown_option(self):
        self.assertIn('id="auto-choose-model"',self.html)
        self.assertNotIn("auto.value='__auto__'",self.html)
        self.assertIn('Load a project to enable Auto Choose.',self.html)
    def test_button_uses_project_id(self):
        self.assertIn("/api/models/recommend?project_id='+currentProject",self.html)
    def test_backend_uses_project_context(self):
        self.assertIn('db.list_messages(project_id, 80)',self.app)
        self.assertIn('db.project_loop_runs(project_id)',self.app)
        self.assertIn('db.list_issues(project_id)',self.app)
        self.assertIn('codebase_index.build_index(workspace, 1500)',self.app)

if __name__=='__main__': unittest.main()
