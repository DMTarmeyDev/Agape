import pathlib, sys, unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import app

class ProjectlessIntakeFallbackTests(unittest.TestCase):
    def test_missing_core_project_falls_back_to_self_contained_intake(self):
        intake={'id':'AGI-X','project_id':0,'project_name':'Recovered document'}
        with patch.object(app,'get_intake',return_value=intake), \
             patch.object(app,'project_by_id',return_value=None), \
             patch.object(app,'load_jobs',return_value=[]), \
             patch.object(app,'save_jobs') as save_jobs, \
             patch.object(app,'threading') as threading_mock:
            threading_mock.Thread.return_value.start.return_value=None
            job=app.new_job({'project_id':999,'intake_id':'AGI-X','quality_mode':'standard'})
        self.assertEqual(job['project_id'],0)
        self.assertEqual(job['project_name'],'Recovered document')
        self.assertEqual(save_jobs.call_args.args[0][-1]['project_id'],0)

    def test_missing_project_without_intake_still_fails(self):
        with patch.object(app,'project_by_id',return_value=None):
            with self.assertRaisesRegex(ValueError,'PROJECT_NOT_FOUND'):
                app.new_job({'project_id':999,'intake_id':''})

if __name__=='__main__': unittest.main(verbosity=2)
