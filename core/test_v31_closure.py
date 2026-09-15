from __future__ import annotations
import json, unittest
from pathlib import Path
import model_router
ROOT=Path(__file__).resolve().parent
class V31ClosureTests(unittest.TestCase):
    def test_identity(self):
        import config
        self.assertEqual(config.BUILD,'DMT-CORE-V3.1-EARLY-ALPHA-R8')
        self.assertEqual(config.BROWSER_NAMESPACE,'dmt-core-v3.1')
    def test_database_manager_ui(self):
        t=(ROOT/'index.html').read_text(encoding='utf-8')
        for x in ('Database Manager','db-load-tables','db-table-select','db-read-table','db-backup','db-backup-output','/api/db/tables','/api/db/table','/api/db/backup','/api/db/backup/verify'): self.assertIn(x,t)
    def test_saved_connection_outcomes_ui(self):
        t=(ROOT/'index.html').read_text(encoding='utf-8')
        for x in ('Connection Outcomes','connection-refresh','connection-output','last_test_status','last_test_detail','/api/connections'): self.assertIn(x,t)
    def test_menu_branding(self):
        t=(ROOT/'index.html').read_text(encoding='utf-8')
        self.assertIn('Agape Core',t); self.assertIn('Early Alpha',t); self.assertNotIn('DMT Studio',t)
        
        self.assertIn('>Project Workspace<',t)
        self.assertIn('>Settings<',t)
        for label in ('Project','Models & Providers','Automation','Memory & Database','Tools & Terminal','Templates','Advanced'): self.assertIn('>'+label+'<',t)
    def test_chat_auto_choose_ui_and_wiring(self):
        t=(ROOT/'index.html').read_text(encoding='utf-8')
        for x in ('Auto Choose Model','id="auto-choose-model"','Auto Choose Model','/api/models/recommend?project_id=', 'autoChooseModel()', 'model:choice.model'):
            self.assertIn(x,t)
        self.assertNotIn("auto.value='__auto__'",t)
    def test_model_routing(self):
        models=[{'name':'qwen2.5-coder:1.5b-instruct'},{'name':'qwen2.5-coder:7b'}]
        self.assertEqual(model_router.choose_model(models,'fix python project tests')['model'],'qwen2.5-coder:7b')
        self.assertEqual(model_router.choose_model(models,'hello')['model'],'qwen2.5-coder:1.5b-instruct')
if __name__=='__main__': unittest.main(verbosity=2)
