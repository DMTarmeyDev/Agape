import json, os, pathlib, sqlite3, sys, tempfile, unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.setdefault("AGAPE_MAINFRAME_DATA",str(pathlib.Path(tempfile.gettempdir())/"agape-mainframe-v27-testdata"))
from agape_mainframe import bridge

class SavedProjectSourceTests(unittest.TestCase):
    def test_saved_project_can_become_ai_fill_source(self):
        payload={
            "ok":True,
            "project":{"id":5,"name":"GreenStep Commercial Interiors Business Plan 2027","goal":"Create a bank-ready business plan"},
            "template":{"name":"Business Plan"},
            "messages":{"messages":[{"role":"user","content":"Budget is £150,000"}]},
            "loop_settings":{"mode":"guided"},
        }
        # This test covers the HTTP/service compatibility path. Force the
        # local-DB fallback off so a developer's or installer's real database
        # can never change the fixture result.
        with patch.object(bridge,"_core_db_read_project_bundle",return_value=None), \
             patch.object(bridge,"request_json",return_value=(200,payload)) as req:
            text=bridge._saved_project_source(5)
        self.assertIn("GreenStep Commercial Interiors Business Plan 2027",text)
        self.assertIn("bank-ready business plan",text)
        self.assertIn("£150,000",text)
        self.assertIn("Saved Agape project",text)
        req.assert_called_once()


    def test_saved_project_source_excludes_assistant_boilerplate_and_json_metadata(self):
        payload={
            "project":{"id":5,"name":"GreenStep Commercial Interiors Business Plan 2027","goal":"Bank-ready plan"},
            "messages":{"messages":[
                {"role":"user","content":"Budget is £150,000"},
                {"role":"assistant","content":"Would you like me to proceed with inspection and plan creation?"},
            ]},
            "loop_settings":{"goal":"Bank-ready plan"},
        }
        text=bridge._saved_project_source(5,payload)
        self.assertIn("Budget is £150,000",text)
        self.assertNotIn("Would you like me to proceed",text)
        self.assertNotIn('"source_type"',text)
        self.assertNotIn('"source_project_id"',text)


    def test_saved_project_keeps_substantive_assistant_summary_but_not_boilerplate(self):
        payload={
            "project":{"id":5,"name":"GreenStep Commercial Interiors Business Plan 2027"},
            "messages":{"messages":[
                {"role":"user","content":"Please complete the plan."},
                {"role":"assistant","content":"GreenStep Commercial Interiors is preparing its 2027 business plan. The project context records a budget of £150,000, a commercial interiors market focus, and a requirement to compare competitors before the final investment decision."},
                {"role":"assistant","content":"Would you like me to proceed with inspection and plan creation?"},
            ]},
            "loop_settings":{},
        }
        text=bridge._saved_project_source(5,payload)
        self.assertIn("Secondary assistant project summaries",text)
        self.assertIn("£150,000",text)
        self.assertNotIn("Would you like me to proceed",text)

    def _make_core_db(self, path: pathlib.Path):
        con=sqlite3.connect(path)
        try:
            con.executescript("""
            CREATE TABLE projects(id INTEGER PRIMARY KEY,name TEXT,created_at TEXT,updated_at TEXT,kind TEXT,archived INTEGER,hidden_reason TEXT);
            CREATE TABLE messages(id INTEGER PRIMARY KEY,project_id INTEGER,role TEXT,provider TEXT,model TEXT,content TEXT,created_at TEXT);
            CREATE TABLE project_loop_settings(project_id INTEGER PRIMARY KEY,workspace TEXT,goal TEXT,test_command TEXT,max_steps INTEGER,auto_model INTEGER,model TEXT,updated_at TEXT);
            """)
            con.execute("INSERT INTO projects VALUES(5,'GreenStep Commercial Interiors Business Plan 2027','2026-09-16','2026-09-16','user',0,'')")
            con.execute("INSERT INTO messages VALUES(1,5,'user','','','Budget is £150,000','2026-09-16')")
            con.execute("INSERT INTO project_loop_settings VALUES(5,'C:/work','Create a bank-ready business plan','',4,1,'','2026-09-16')")
            con.commit()
        finally:con.close()

    def test_saved_project_uses_read_only_database_when_core_is_offline(self):
        with tempfile.TemporaryDirectory() as td:
            db=pathlib.Path(td)/'dmt_core.sqlite3';self._make_core_db(db)
            old=os.environ.get('AGAPE_CORE_DB');os.environ['AGAPE_CORE_DB']=str(db)
            try:
                with patch.object(bridge,'request_json') as req:
                    text=bridge._saved_project_source(5)
                self.assertIn('GreenStep Commercial Interiors Business Plan 2027',text)
                self.assertIn('Budget is £150,000',text)
                self.assertIn('storage metadata, raw JSON and generic assistant boilerplate were excluded',text)
                req.assert_not_called()
            finally:
                if old is None:os.environ.pop('AGAPE_CORE_DB',None)
                else:os.environ['AGAPE_CORE_DB']=old

    def test_project_list_uses_database_without_core_http(self):
        with tempfile.TemporaryDirectory() as td:
            db=pathlib.Path(td)/'dmt_core.sqlite3';self._make_core_db(db)
            old=os.environ.get('AGAPE_CORE_DB');os.environ['AGAPE_CORE_DB']=str(db)
            try:
                with patch.object(bridge,'request_json') as req:
                    rows=bridge.projects()
                self.assertEqual(rows[0]['id'],5)
                req.assert_not_called()
            finally:
                if old is None:os.environ.pop('AGAPE_CORE_DB',None)
                else:os.environ['AGAPE_CORE_DB']=old

    def test_project_intake_becomes_self_contained_before_document_service(self):
        bundle={
            'ok':True,
            'project':{'id':5,'name':'GreenStep Commercial Interiors Business Plan 2027'},
            'messages':{'messages':[{'role':'user','content':'Budget is £150,000'}]},
            'template':{},'loop_settings':{'goal':'Bank-ready plan'},'source_access':'read-only-sqlite-fallback'
        }
        calls=[]
        def fake_request(method,url,body=None,timeout=0):
            calls.append((method,url,body,timeout))
            if url.endswith('/api/document/intake'):
                return 200,{'ok':True,'intake':{'id':'AGI-1','project_id':body.get('project_id'),'source_project_id':body.get('source_project_id'),'project_name':body.get('project_name')}}
            return 200,{'ok':True}
        with patch.object(bridge,'_saved_project_bundle',return_value=bundle), \
             patch.object(bridge,'ensure_existing_services',return_value={}) as ensure_services, \
             patch.object(bridge,'ensure_r24',return_value={'ok':True}), \
             patch.object(bridge,'request_json',side_effect=fake_request):
            result=bridge.prepare_intake({'source_mode':'project','project_id':5,'instruction':'Fill the brief'})
        ensure_services.assert_called_once_with({'route':'document'},0)
        post=[x for x in calls if x[1].endswith('/api/document/intake')][0][2]
        self.assertEqual(post['project_id'],0)
        self.assertEqual(post['source_project_id'],5)
        self.assertEqual(post['project_name'],'GreenStep Commercial Interiors Business Plan 2027')
        self.assertIn('Budget is £150,000',post['project_info'])
        self.assertEqual(result['intake']['project_id'],0)


    def test_legacy_literal_line_breaks_are_recovered_before_fact_extraction(self):
        payload={
            "project":{"id":5,"name":"GreenStep Commercial Interiors Business Plan 2027"},
            "messages":{"messages":[{
                "role":"user",
                "content":r"Organisation: GreenStep Commercial Interiors\nIndustry: Commercial interiors\nGeography: United Kingdom\nBudget / pricing: £150,000"
            }]},
            "loop_settings":{},
        }
        text=bridge._saved_project_source(5,payload)
        self.assertIn("Organisation: GreenStep Commercial Interiors\nIndustry: Commercial interiors",text)
        self.assertNotIn(r"Commercial Interiors\nIndustry",text)

    def test_new_auto_saved_project_uses_real_line_breaks(self):
        with tempfile.TemporaryDirectory() as td:
            db=pathlib.Path(td)/'dmt_core.sqlite3';self._make_core_db(db)
            intake={
                'ai_fill':{'fields':{
                    'organisation':{'value':'GreenStep Commercial Interiors'},
                    'document_purpose':{'value':'Business Plan'},
                    'timeline':{'value':'2027'},
                }},
                'upload':{'preview':'Organisation: GreenStep Commercial Interiors\nIndustry: Commercial interiors'}
            }
            with patch.object(bridge,'_ensure_project_database',return_value=db):
                saved=bridge._save_new_source_as_project(intake,{'instruction':'Create a bank-ready expansion business plan'},'', 'greenstep-source.docx')
            con=sqlite3.connect(db)
            try:
                content=con.execute('SELECT content FROM messages WHERE project_id=? ORDER BY id DESC LIMIT 1',(saved['id'],)).fetchone()[0]
            finally: con.close()
            self.assertIn('Requested result:\nCreate a bank-ready expansion business plan',content)
            self.assertIn('Source information:\nOrganisation: GreenStep Commercial Interiors',content)
            self.assertNotIn(r'Requested result:\nCreate',content)
            self.assertTrue(saved['name'].startswith('GreenStep Commercial Interiors Business Plan 2027'))

    def test_internal_mock_project_names_are_hidden(self):
        from agape_mainframe import bridge
        self.assertTrue(bridge._project_name_is_internal_test('Rollback Mock Project'))
        self.assertTrue(bridge._project_name_is_internal_test('Loop Mock Project'))
        self.assertFalse(bridge._project_name_is_internal_test('GreenStep Commercial Interiors Business Plan 2027'))

if __name__=="__main__":unittest.main(verbosity=2)
