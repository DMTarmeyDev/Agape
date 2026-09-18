from __future__ import annotations
import os, shutil, sqlite3, tempfile, unittest
from pathlib import Path
import provider_catalog,connection_spec,provider_failover,request_budget,backup_restore,project_portability,diagnostic_bundle,instance_guard,schema_guard,startup_recovery,provider_resilience,alpha_user_readiness,safety_matrix,retention_policy,resource_envelope,mission_proof
import db,offline_queue,audit_trail,alpha_release

class V30FeatureTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(prefix='agape-v30-test-')); self.data=self.root/'data'; self.old_data,self.old_db=db.DATA_ROOT,db.DB_PATH; db.DATA_ROOT=self.data; db.DB_PATH=self.data/'dmt_core.sqlite3'; db.init_db(); self.project=db.create_project('V30 Test Project')
    def tearDown(self): db.DATA_ROOT=self.old_data; db.DB_PATH=self.old_db; shutil.rmtree(self.root,ignore_errors=True)
    def test_81_provider_catalog(self): self.assertEqual(len(provider_catalog.provider_catalog()['providers']),2); self.assertTrue(provider_catalog.provider_capabilities('ollama')['ok'])
    def test_82_connection_spec(self):
        r=connection_spec.normalize_connection('openai-compatible','m',{'base_url':'https://example.com','api_key_env':'OPENAI_API_KEY'}); self.assertFalse(r['plaintext_secret_stored'])
        with self.assertRaises(ValueError): connection_spec.normalize_connection('openai-compatible','m',{'base_url':'https://example.com','api_key':'secret'})
    def test_83_external_layer_declared(self): self.assertTrue(provider_catalog.provider_capabilities('openai-compatible')['chat'])
    def test_84_provider_failover(self): self.assertEqual(provider_failover.choose_provider([{'provider':'online','online':True,'health':'healthy'},{'provider':'ollama','online':False,'health':'healthy'}])['provider'],'ollama')
    def test_85_request_budget(self): self.assertTrue(request_budget.evaluate_request_budget({'requests':1},{'requests':2})['allowed']); self.assertFalse(request_budget.evaluate_request_budget({'requests':3},{'requests':2})['allowed'])
    def test_86_offline_queue(self):
        x=offline_queue.enqueue(self.project['id'],'retry me'); self.assertEqual(x['item']['status'],'pending'); y=offline_queue.update(x['item']['id'],'ready'); self.assertEqual(y['item']['status'],'ready')
    def test_87_backup_restore(self):
        p=db.backup_database(str(self.root/'backups')); v=backup_restore.verify_sqlite_backup(p); self.assertTrue(v['ok']); self.assertTrue(backup_restore.plan_restore(v,str(db.DB_PATH))['approval_required'])
    def test_88_project_portability(self):
        db.add_message(self.project['id'],'user','hello'); e=project_portability.export_project(self.project,db.list_messages(self.project['id']),[]); self.assertTrue(e['ok']); self.assertTrue(project_portability.validate_import(e['payload'],e['sha256'])['ok'])
    def test_89_diagnostic_bundle(self):
        d=diagnostic_bundle.build_bundle({'token':'abc'},{'ok':True},['api_key=secret'],[]); self.assertTrue(d['sanitized']); self.assertNotIn('secret',str(d['payload']).lower())
    def test_90_instance_guard(self): self.assertTrue(instance_guard.verify_instance({'ok':True,'build':'B'},'B')['ok']); self.assertFalse(instance_guard.verify_instance({'ok':True,'build':'X'},'B')['ok'])
    def test_91_schema_guard(self): self.assertTrue(schema_guard.evaluate_schema(db.status(),db.database_tables(),9)['ok'])
    def test_92_startup_recovery(self): self.assertTrue(startup_recovery.plan_startup_recovery({'database_ok':True,'ledger_ok':True,'incomplete_loops':1})['safe_to_start'])
    def test_93_audit_trail(self): audit_trail.append('test','run','PASS',{'x':1},self.project['id']); audit_trail.append('test','verify','PASS',{},self.project['id']); self.assertTrue(audit_trail.verify()['ok'])
    def test_94_provider_resilience(self): self.assertEqual(provider_resilience.score_provider([{'status':'PASS','latency_ms':100},{'status':'PASS','latency_ms':200}])['classification'],'healthy')
    def test_95_alpha_user_readiness(self): self.assertTrue(alpha_user_readiness.evaluate({k:True for k in ('system_test','database','history','project_filter','ollama','templates','autodev','rollback','startup','security','provider_layer','diagnostics')})['alpha_ready'])
    def test_96_safety_matrix(self): self.assertTrue(safety_matrix.evaluate({'operation':'edit'})['allowed']); self.assertFalse(safety_matrix.evaluate({'operation':'format'})['allowed'])
    def test_97_retention_policy(self): r=retention_policy.plan_retention([{'id':1,'status':'pass'},{'id':2,'status':'failed'}],1,True); self.assertEqual(r['delete'],[]); self.assertIn(2,r['keep'])
    def test_98_resource_envelope(self): r=resource_envelope.recommend({'ram_gb':13.7,'logical_cores':12,'disk_free_gb':100},['qwen2.5-coder:1.5b-instruct','qwen2.5-coder:7b']); self.assertTrue(r['ok']); self.assertIn(r['preferred_model'],['qwen2.5-coder:1.5b-instruct','qwen2.5-coder:7b'])
    def test_99_mission_proof(self): r=mission_proof.build('ship alpha',{'all':True},{'ok':True},{'ok':True,'quick_check':'ok'},True,{'ok':True},{'ok':True}); self.assertTrue(r['ready']); self.assertEqual(len(r['proof_sha256']),64)
    def test_100_alpha_release(self):
        keys=('system','database','history','templates','models','project_loop','stages31_40','stages41_50','stages51_60','stages61_70','stages71_80','stages81_100','rollback','mission_proof'); ev=alpha_release.evaluate({k:True for k in keys}); self.assertTrue(ev['release_ready']); rec=alpha_release.record('DMT-CORE-V3.1-EARLY-ALPHA-R1',ev,'A'*64,{}); self.assertEqual(rec['run']['status'],'PASS')
if __name__=='__main__': unittest.main(verbosity=2)
