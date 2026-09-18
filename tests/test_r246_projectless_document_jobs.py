import pathlib, sys, unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agape_mainframe import bridge

class ProjectlessDocumentJobTests(unittest.TestCase):
    def test_prepared_document_does_not_require_core_project_runtime(self):
        calls=[]
        def fake_request(method,url,body=None,timeout=0):
            calls.append((method,url,body,timeout))
            if url.endswith('/api/jobs'):
                return 202,{'job_id':'AGU-TEST'}
            return 200,{'ok':True}
        with patch.object(bridge,'ensure_existing_services',return_value={}) as services, \
             patch.object(bridge,'ensure_r24',return_value={'ok':True}), \
             patch.object(bridge,'request_json',side_effect=fake_request), \
             patch.object(bridge,'record_event'), patch.object(bridge,'remember_work'):
            out=bridge.run_work({'task':'Create document','project_id':321,'intake_id':'AGI-SELF-CONTAINED','quality':'gold'}, {'route':'document','title':'Document'})
        self.assertEqual(out['job_id'],'AGU-TEST')
        services.assert_called_once_with({'route':'document','title':'Document'},0)
        posted=[c for c in calls if c[1].endswith('/api/jobs')][0][2]
        self.assertEqual(posted['project_id'],0)
        self.assertEqual(posted['intake_id'],'AGI-SELF-CONTAINED')

    def test_non_document_project_work_keeps_real_project_id(self):
        calls=[]
        def fake_request(method,url,body=None,timeout=0):
            calls.append((method,url,body,timeout))
            if url.endswith('/api/jobs'):
                return 202,{'job_id':'AGU-DEV'}
            return 200,{'ok':True}
        with patch.object(bridge,'ensure_existing_services',return_value={}) as services, \
             patch.object(bridge,'ensure_r24',return_value={'ok':True}), \
             patch.object(bridge,'request_json',side_effect=fake_request), \
             patch.object(bridge,'record_event'), patch.object(bridge,'remember_work'):
            bridge.run_work({'task':'Fix code','project_id':321,'intake_id':'','quality':'gold'}, {'route':'development','title':'Dev'})
        services.assert_called_once_with({'route':'development','title':'Dev'},321)
        posted=[c for c in calls if c[1].endswith('/api/jobs')][0][2]
        self.assertEqual(posted['project_id'],321)

if __name__=='__main__': unittest.main(verbosity=2)
