from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import acceptance_gate
import adaptive_router
import autodev_cycle
import autodev_session
import db
import failure_triage
import model_scorecard
import resume_planner
import run_ledger
import scope_lock
import task_graph


class V19FeatureTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(prefix='agape-v19-test-'))
        self.data=self.root/'data'; self.work=self.root/'work'; (self.work/'src').mkdir(parents=True)
        (self.work/'src'/'api.py').write_text('VALUE=1\n',encoding='utf-8')
        (self.work/'README.md').write_text('project\n',encoding='utf-8')
        (self.work/'SELFTEST.py').write_text("print('PASS')\n",encoding='utf-8')
        self.old_data,self.old_db=db.DATA_ROOT,db.DB_PATH
        db.DATA_ROOT=self.data; db.DB_PATH=self.data/'dmt_core.sqlite3'; db.init_db()
        self.project=db.create_project('V19 Test Project')
    def tearDown(self):
        db.DATA_ROOT=self.old_data
        db.DB_PATH=self.old_db
        shutil.rmtree(self.root,ignore_errors=True)
    def test_41_persistent_session(self):
        r=autodev_session.create_session(self.project['id'],str(self.work),'fix api and test','',4,'')
        self.assertTrue(r['ok']); sid=r['session']['session_id']
        self.assertEqual(db.autodev_session(sid)['status'],'prepared')
        self.assertEqual(len(db.list_autodev_sessions(self.project['id'])),1)
    def test_42_task_graph(self):
        tasks=[{'id':1,'title':'a','depends_on':[]},{'id':2,'title':'b','depends_on':[1]},{'id':3,'title':'c','depends_on':[2]}]
        r=task_graph.build_task_graph(tasks,[1],[]); self.assertTrue(r['ok']); self.assertEqual([x['id'] for x in r['ready']],[2])
        with self.assertRaises(ValueError): task_graph.build_task_graph([{'id':1,'depends_on':[2]},{'id':2,'depends_on':[1]}])
    def test_43_scope_lock(self):
        lock=scope_lock.create_scope_lock(str(self.work),['src/api.py'])
        (self.work/'src'/'api.py').write_text('VALUE=2\n',encoding='utf-8')
        self.assertTrue(scope_lock.check_scope_lock(lock,str(self.work))['safe'])
        (self.work/'README.md').write_text('changed\n',encoding='utf-8')
        r=scope_lock.check_scope_lock(lock,str(self.work)); self.assertFalse(r['safe']); self.assertIn('README.md',r['unexpected_paths'])
    def test_44_failure_triage(self):
        r=failure_triage.triage_failure('',"ModuleNotFoundError: No module named 'x'",1); self.assertEqual(r['category'],'import'); self.assertFalse(r['retryable'])
        self.assertEqual(failure_triage.triage_failure('','operation timed out',124)['category'],'timeout')
    def test_45_model_scorecard(self):
        db.record_model_outcome('qwen2.5-coder:7b','coding',True,10)
        db.record_model_outcome('qwen2.5-coder:7b','coding',True,12)
        db.record_model_outcome('qwen2.5-coder:1.5b-instruct','coding',False,5,'assertion')
        r=model_scorecard.build_scorecard(['qwen2.5-coder:1.5b-instruct','qwen2.5-coder:7b'],'coding'); self.assertEqual(r['recommended'],'qwen2.5-coder:7b')
    def test_46_adaptive_router(self):
        r=adaptive_router.choose_adaptive_model(['qwen2.5-coder:1.5b-instruct','qwen2.5-coder:7b'],'repair failing api',2,'syntax')
        self.assertEqual(r['model'],'qwen2.5-coder:7b'); self.assertEqual(r['reason'],'FAILURE_ESCALATION')
    def test_47_resume_planner(self):
        s=autodev_session.create_session(self.project['id'],str(self.work),'fix api','',4,'')['session']
        self.assertEqual(resume_planner.decide_resume(s,{'safe':True},True)['action'],'resume')
        self.assertEqual(resume_planner.decide_resume(s,{'safe':False,'unexpected_paths':['x']},True)['action'],'replan')
    def test_48_acceptance_gate(self):
        r=acceptance_gate.evaluate_acceptance({'tests':'PASS','db':True},['tests','db']); self.assertTrue(r['ok'])
        r=acceptance_gate.evaluate_acceptance({'tests':False},['tests','db']); self.assertFalse(r['ok']); self.assertIn('db',r['missing'])
    def test_49_tamper_evident_ledger(self):
        sid=autodev_session.create_session(self.project['id'],str(self.work),'fix api','',4,'')['session']['session_id']
        run_ledger.append_entry(sid,'ONE','PASS',{'x':1}); run_ledger.append_entry(sid,'TWO','PASS',{'y':2})
        self.assertTrue(run_ledger.ledger_status(sid)['ok'])
        db.execute("UPDATE run_ledger SET payload_json='{}' WHERE session_id=? AND stage='ONE'",(sid,))
        self.assertFalse(run_ledger.ledger_status(sid)['ok'])
    def test_50_cycle_coordinator(self):
        r=autodev_cycle.prepare_cycle(self.project['id'],str(self.work),'fix api and run tests',['stay inside workspace'],4,['qwen2.5-coder:1.5b-instruct','qwen2.5-coder:7b'])
        self.assertTrue(r['ok']); self.assertTrue(r['ready']); self.assertEqual(r['execution_engine'],'project_loop')
        self.assertEqual(r['pipeline']['tests']['command'],'python SELFTEST.py')
        self.assertTrue(run_ledger.ledger_status(r['session']['session_id'])['ok'])

if __name__=='__main__': unittest.main(verbosity=2)
