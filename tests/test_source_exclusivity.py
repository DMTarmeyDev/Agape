import base64, pathlib, sys, tempfile, unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agape_mainframe import bridge

class SourceExclusivityTests(unittest.TestCase):
    def _run(self,body):
        posted={}
        def fake_request(method,url,payload=None,timeout=0):
            if url.endswith('/api/document/intake'):
                posted.update(payload or {})
                return 200,{'intake':{'id':'I1','project_id':payload.get('project_id',0)}}
            return 200,{'ok':True}
        with patch.object(bridge,'ensure_existing_services',return_value={}), patch.object(bridge,'ensure_r24',return_value={'ok':True}), patch.object(bridge,'request_json',side_effect=fake_request), patch.object(bridge,'_saved_project_bundle',return_value={'project':{'id':5,'name':'Saved Five'},'messages':{},'template':{},'loop_settings':{},'source_access':'test'}):
            result=bridge.prepare_intake(body)
        return result,posted

    def test_paste_mode_ignores_file_and_project(self):
        _,posted=self._run({'source_mode':'paste','source_text':'PASTE FACTS','file_name':'wrong.pdf','file_data_base64':'AAAA','project_id':99})
        self.assertEqual(posted['project_id'],0)
        self.assertEqual(posted['name'],'pasted-source.txt')
        self.assertIn(b'PASTE FACTS',base64.b64decode(posted['data_base64']))

    def test_upload_mode_ignores_pasted_text_and_project(self):
        _,posted=self._run({'source_mode':'upload','source_text':'IGNORE ME','file_name':'facts.txt','file_data_base64':base64.b64encode(b'FILE FACTS').decode(),'project_id':99})
        self.assertEqual(posted['project_id'],0)
        self.assertEqual(posted['name'],'facts.txt')
        self.assertEqual(base64.b64decode(posted['data_base64']),b'FILE FACTS')

    def test_project_mode_uses_only_saved_project(self):
        _,posted=self._run({'source_mode':'project','source_text':'IGNORE ME','file_name':'wrong.txt','file_data_base64':'AAAA','project_id':5})
        self.assertEqual(posted['project_id'],0)
        self.assertEqual(posted['source_project_id'],5)
        self.assertEqual(posted['name'],'Saved Five.txt')
        decoded=base64.b64decode(posted['data_base64']).decode()
        self.assertIn('Saved Agape project selected as the source',decoded)
        self.assertIn('Saved Five',decoded)

if __name__=='__main__': unittest.main(verbosity=2)
