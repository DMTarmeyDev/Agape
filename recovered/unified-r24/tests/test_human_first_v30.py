import inspect, pathlib, sys, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import app

class HumanFirstV30Tests(unittest.TestCase):
    def test_document_execution_does_not_probe_unrelated_work_engine(self):
        src=inspect.getsource(app.execute_job)
        doc_branch=src.split('if route == "document":',1)[1].split('elif route == "project_loop":',1)[0]
        self.assertNotIn('WORK_URL',doc_branch)
        self.assertNotIn('submit_work_health_probe',doc_branch)
        self.assertIn("doc_get('/api/health'",doc_branch)
    def test_gold_default_is_three_reviewers(self):
        self.assertEqual(app.DEFAULT_SETTINGS['gold_reviewer_count'],3)
    def test_intake_keeps_writing_check_metadata(self):
        src=inspect.getsource(app._create_document_intake_once)
        self.assertIn("'writing_check'",src)
        self.assertIn("upload.get('writing_check')",src)

if __name__=='__main__': unittest.main(verbosity=2)
