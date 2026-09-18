from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import change_budget
import completion_evidence
import context_freshness
import db
import dependency_executor
import regression_planner
import release_confidence
import repair_verifier
import requirements_spec
import retry_policy
import self_heal_controller
import workspace_snapshot

class V20FeatureTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(prefix='agape-v20-test-'))
        self.data=self.root/'data'; self.work=self.root/'work'; (self.work/'src').mkdir(parents=True)
        (self.work/'src'/'api.py').write_text('VALUE=1\n',encoding='utf-8')
        (self.work/'SELFTEST.py').write_text("print('PASS')\n",encoding='utf-8')
        (self.work/'test_api.py').write_text("print('PASS')\n",encoding='utf-8')
        self.old_data,self.old_db=db.DATA_ROOT,db.DB_PATH
        db.DATA_ROOT=self.data; db.DB_PATH=self.data/'dmt_core.sqlite3'; db.init_db(); self.project=db.create_project('V20 Test Project')
    def tearDown(self):
        db.DATA_ROOT=self.old_data; db.DB_PATH=self.old_db; shutil.rmtree(self.root,ignore_errors=True)
    def test_51_requirements(self):
        r=requirements_spec.build_requirements('fix api',['must pass'],['api works'],['safe']); self.assertTrue(r['ok']); self.assertEqual(r['requirements'][0]['id'],'R1'); self.assertEqual(r['acceptance_criteria'][0]['id'],'AC1'); self.assertEqual(len(r['requirements_sha256']),64)
    def test_52_change_budget(self):
        r=change_budget.evaluate_change_budget([{'path':'a.py','before_content':'x=1\n','after_content':'x=2\n'}],{'max_files':1,'max_changed_lines':4}); self.assertTrue(r['allowed'])
        r=change_budget.evaluate_change_budget([{'path':'a.py','content':'x'},{'path':'b.py','content':'y'}],{'max_files':1}); self.assertFalse(r['allowed'])
    def test_53_context_freshness(self):
        snap=workspace_snapshot.create_snapshot(str(self.work),100); self.assertTrue(context_freshness.check_context_freshness(str(self.work),snap)['fresh'])
        (self.work/'src'/'api.py').write_text('VALUE=2\n',encoding='utf-8'); r=context_freshness.check_context_freshness(str(self.work),snap); self.assertTrue(r['stale']); self.assertFalse(r['safe'])
        self.assertTrue(context_freshness.check_context_freshness(str(self.work),snap,['src/api.py'])['safe'])
    def test_54_retry_policy(self):
        self.assertEqual(retry_policy.decide_retry(1,'network',3,1)['action'],'retry'); self.assertEqual(retry_policy.decide_retry(2,'syntax',3,2)['action'],'escalate'); self.assertEqual(retry_policy.decide_retry(3,'network',3,3)['action'],'rollback')
    def test_55_repair_verifier(self):
        r=repair_verifier.verify_repair({'category':'assertion'},{'ok':True},[{'ok':True}],{'allowed':True},{'safe':True}); self.assertTrue(r['fixed'])
        self.assertFalse(repair_verifier.verify_repair({'category':'assertion'},{'ok':True},[{'ok':False}])['ok'])
    def test_56_dependency_executor(self):
        tasks=[{'id':1,'depends_on':[]},{'id':2,'depends_on':[1]},{'id':3,'depends_on':[2]}]; r=dependency_executor.plan_next_tasks(tasks,{'1':'completed'},1); self.assertEqual(r['action'],'execute'); self.assertEqual(r['selected'][0]['id'],2)
    def test_57_completion_evidence(self):
        spec=requirements_spec.build_requirements('x',[],['one','two']); r=completion_evidence.evaluate_completion(spec,{'criteria':{'AC1':'PASS','AC2':True}},{'ok':True}); self.assertTrue(r['complete']); self.assertEqual(len(r['evidence_sha256']),64)
        self.assertFalse(completion_evidence.evaluate_completion(spec,{'criteria':{'AC1':'PASS'}},{'ok':True})['ok'])
    def test_58_regression_planner(self):
        r=regression_planner.plan_regressions(str(self.work),['src/api.py'],['test_api.py']); self.assertTrue(r['ok']); self.assertTrue(any(x['command']=='python SELFTEST.py' for x in r['phases'])); self.assertIn('test_api.py',r['selected_tests'])
    def test_59_release_confidence(self):
        signals={x:True for x in ('system','database','history','requirements','regressions','ledger','templates')}; r=release_confidence.score_release_confidence(signals); self.assertTrue(r['release_ready']); self.assertEqual(r['confidence'],100.0)
        signals['ledger']=False; self.assertFalse(release_confidence.score_release_confidence(signals)['ok'])
    def test_60_self_heal_prepare_and_decide(self):
        r=self_heal_controller.prepare_self_heal(self.project['id'],str(self.work),'verify project',[],['project tests pass'],['stay inside workspace'],2,['qwen2.5-coder:7b']); self.assertTrue(r['ready']); self.assertEqual(r['execution_engine'],'bounded_autodev_cycle')
        d=self_heal_controller.decide_after_attempt(1,'assertion',{'category':'assertion'},{'ok':True},[{'ok':True}],{'allowed':True},{'safe':True},3); self.assertEqual(d['action'],'complete')

if __name__=='__main__': unittest.main(verbosity=2)
