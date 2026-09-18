from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import baseline_attestation
import failure_evidence
import root_cause
import reproduction_planner
import repair_candidate
import flake_detector
import checkpoint_selector
import execution_budget
import autonomy_policy
import autodev_governor
import db

class V21FeatureTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(prefix='agape-v21-test-')); self.work=self.root/'work'; self.data=self.root/'data'; self.work.mkdir()
        (self.work/'SELFTEST.py').write_text("print('PASS')\n",encoding='utf-8'); (self.work/'test_api.py').write_text("print('PASS')\n",encoding='utf-8'); (self.work/'api.py').write_text('VALUE=1\n',encoding='utf-8')
        self.old_data,self.old_db=db.DATA_ROOT,db.DB_PATH; db.DATA_ROOT=self.data; db.DB_PATH=self.data/'dmt_core.sqlite3'; db.init_db(); self.project=db.create_project('V21 Test Project')
        self.runtime={'ok':True,'build':'DMT-CORE-V2.1-ALPHA-R1'}; self.database={'ok':True,'quick_check':'ok','database':str(db.DB_PATH)}
    def tearDown(self):
        db.DATA_ROOT=self.old_data; db.DB_PATH=self.old_db; shutil.rmtree(self.root,ignore_errors=True)
    def test_61_baseline_attestation(self):
        r=baseline_attestation.attest_baseline(self.runtime,self.database,'DMT-CORE-V2.1-ALPHA-R1','DMT-CORE-V2.1-ALPHA-R1',True,True); self.assertTrue(r['ready']); self.assertEqual(len(r['attestation_sha256']),64)
        self.assertFalse(baseline_attestation.attest_baseline({'build':'wrong'},self.database,'right','right')['ok'])
    def test_62_failure_evidence(self):
        r=failure_evidence.build_failure_evidence('',"TOKEN=secret123\nTraceback api.py line 2",'AssertionError',1,['test_api.py'],['api.py']); self.assertTrue(r['ok']); self.assertNotIn('secret123',r['stderr']); self.assertEqual(len(r['evidence_sha256']),64)
    def test_63_root_cause(self):
        ev=failure_evidence.build_failure_evidence('','Traceback api.py line 2','AssertionError',1,['test_api.py'],['api.py']); r=root_cause.rank_root_causes(ev,None,['api.py']); self.assertEqual(r['primary']['file'],'api.py'); self.assertGreater(r['primary']['score'],0)
    def test_64_reproduction(self):
        r=reproduction_planner.plan_reproduction(str(self.work),{'failed_tests':['test_api.py'],'changed_files':['api.py']},['api.py']); self.assertTrue(r['ok']); self.assertTrue(r['minimal_command'].startswith('python ')); self.assertNotIn('&&',r['minimal_command'])
    def test_65_repair_candidate(self):
        r=repair_candidate.score_candidates([{'id':'safe','files_changed':1,'changed_lines':4,'confidence':0.8,'tests_passed':True,'regressions_passed':True,'scope_safe':True,'budget_safe':True,'approval':'allow'},{'id':'unsafe','files_changed':1,'changed_lines':1,'confidence':1,'tests_passed':True,'regressions_passed':True,'scope_safe':False,'budget_safe':True,'approval':'block'}]); self.assertTrue(r['ok']); self.assertEqual(r['selected']['id'],'safe')
    def test_66_flake_detector_and_persistence(self):
        flake_detector.record_and_classify(self.project['id'],'test_api','PASS')
        flake_detector.record_and_classify(self.project['id'],'test_api','FAIL',failure_text='boom')
        r=flake_detector.record_and_classify(self.project['id'],'test_api','PASS'); self.assertTrue(r['classification']['flaky']); self.assertEqual(len(db.list_test_observations(self.project['id'],'test_api')),3)
    def test_67_checkpoint_selector(self):
        r=checkpoint_selector.select_checkpoint([{'path':'old','build':'B','verified':True,'modified':1},{'path':'new','build':'B','verified':True,'modified':2},{'path':'bad','build':'B','verified':False,'modified':3}],'B',True); self.assertEqual(r['selected']['path'],'new')
    def test_68_execution_budget(self):
        self.assertTrue(execution_budget.evaluate_execution_budget({'max_steps':2},{'max_steps':4})['allowed']); self.assertFalse(execution_budget.evaluate_execution_budget({'max_steps':5},{'max_steps':4})['ok'])
    def test_69_autonomy_policy(self):
        self.assertEqual(autonomy_policy.decide_autonomy({'files':['app_local.py'],'command':''},'safe')['action'],'auto_continue'); self.assertEqual(autonomy_policy.decide_autonomy({'files':['security.py'],'command':''},'safe')['action'],'approval_required')
    def test_70_governor_prepare(self):
        r=autodev_governor.prepare_governed_run(self.project['id'],str(self.work),'verify project',self.runtime,self.database,'DMT-CORE-V2.1-ALPHA-R1','DMT-CORE-V2.1-ALPHA-R1',True,True,None,[],None,{'max_steps':0},{'max_steps':2},{'files':[],'command':''}); self.assertTrue(r['ready']); self.assertEqual(r['execution_engine'],'quality_controlled_self_heal')

if __name__=='__main__': unittest.main(verbosity=2)
