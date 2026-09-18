from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import checkpoint_cadence
import completion_proof
import confidence_tracker
import db
import dependency_state
import development_supervisor
import interruption_recovery
import parallelism_advisor
import regression_memory
import stale_failure
import work_plan

class V22FeatureTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(prefix='agape-v22-test-')); self.work=self.root/'work'; self.data=self.root/'data'; self.work.mkdir()
        (self.work/'SELFTEST.py').write_text("print('PASS')\n",encoding='utf-8'); (self.work/'app_local.py').write_text('VALUE=1\n',encoding='utf-8')
        self.old_data,self.old_db=db.DATA_ROOT,db.DB_PATH; db.DATA_ROOT=self.data; db.DB_PATH=self.data/'dmt_core.sqlite3'; db.init_db(); self.project=db.create_project('V22 Test Project')
        self.runtime={'ok':True,'build':'DMT-CORE-V3.0-ALPHA-R1'}; self.database={'ok':True,'quick_check':'ok','database':str(db.DB_PATH)}
    def tearDown(self):
        db.DATA_ROOT=self.old_data; db.DB_PATH=self.old_db; shutil.rmtree(self.root,ignore_errors=True)
    def test_71_work_plan(self):
        r=work_plan.build_work_plan('Improve feature safely'); self.assertTrue(r['ok']); self.assertEqual(r['task_count'],4); self.assertEqual(len(r['plan_sha256']),64)
    def test_72_interruption_recovery(self):
        self.assertEqual(interruption_recovery.decide_interruption_recovery({'status':'paused','snapshot_sha256':'A'},{'ok':True},{'ok':True},'A')['action'],'resume')
        self.assertEqual(interruption_recovery.decide_interruption_recovery({'status':'paused'},{'ok':False},{'ok':True},'',{'path':'good'})['action'],'rollback')
    def test_73_dependency_state(self):
        r=dependency_state.evaluate_dependency_state([{'id':'a','status':'completed'},{'id':'b','depends_on':['a'],'status':'pending'},{'id':'c','depends_on':['b'],'status':'pending'}]); self.assertTrue(r['ok']); self.assertEqual([x['id'] for x in r['ready']],['b'])
    def test_74_confidence_tracker(self):
        r=confidence_tracker.track_confidence({'baseline':True,'database':True,'history':True,'tests':True,'ledger':True}); self.assertTrue(r['ready']); self.assertEqual(r['score'],1.0)
    def test_75_stale_failure(self):
        r=stale_failure.classify_failure_freshness({'snapshot_sha256':'OLD'},'NEW',[]); self.assertTrue(r['stale']); self.assertEqual(r['action'],'suppress')
        r2=stale_failure.classify_failure_freshness({'id':1,'test_name':'t'},'',[{'id':2,'test_name':'t','status':'PASS'}]); self.assertTrue(r2['stale'])
    def test_76_parallelism(self):
        r=parallelism_advisor.advise_parallelism([{'id':'read1','kind':'inspect','files':['a.py']},{'id':'test1','kind':'test','files':['b.py']},{'id':'edit1','kind':'edit','files':['c.py']}],2); self.assertTrue(r['ok']); self.assertIn('edit1',r['serialized']); self.assertTrue(any(len(g)==2 for g in r['parallel_groups']))
    def test_77_checkpoint_cadence(self):
        self.assertTrue(checkpoint_cadence.checkpoint_decision(2,1,1,True,False)['checkpoint_due']); self.assertFalse(checkpoint_cadence.checkpoint_decision(0,0,1,False,False)['checkpoint_due'])
    def test_78_regression_memory(self):
        rows=[{'id':1,'test_name':'api','status':'FAIL'},{'id':2,'test_name':'api','status':'FAIL'},{'id':3,'test_name':'ui','status':'PASS'}]; r=regression_memory.summarize_regression_memory(rows); self.assertIn('api',r['recommended_tests'])
    def test_79_completion_proof(self):
        conf=confidence_tracker.track_confidence({'baseline':True,'database':True,'history':True,'tests':True,'ledger':True}); r=completion_proof.build_completion_proof({'ok':True},conf,{'ok':True,'head_hash':'A'},{'quick_check':'ok'},True,True,0); self.assertTrue(r['ready']); self.assertEqual(len(r['proof_sha256']),64)
    def test_80_supervisor_prepare_persistence(self):
        r=development_supervisor.prepare_supervisor_run(self.project['id'],str(self.work),'verify passing project',self.runtime,self.database,'DMT-CORE-V3.0-ALPHA-R1','DMT-CORE-V3.0-ALPHA-R1',2,None,True); self.assertTrue(r['ready']); self.assertEqual(r['execution_engine'],'bounded_governed_autodev'); self.assertIsNotNone(db.supervisor_run(r['supervisor_id']))

if __name__=='__main__': unittest.main(verbosity=2)
