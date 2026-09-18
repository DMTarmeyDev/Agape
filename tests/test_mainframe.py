import json, os, pathlib, sys, tempfile, threading, time, unittest, urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.setdefault('AGAPE_MAINFRAME_DATA',str(pathlib.Path(tempfile.gettempdir())/'agape-mainframe-v1-testdata'))
from agape_mainframe import capabilities, planner, server, state

class MainframeTests(unittest.TestCase):
    def setUp(self):
        try: state.SETTINGS_FILE.unlink()
        except FileNotFoundError: pass
    def test_health_endpoint_is_lightweight(self):
        original=server.service_status
        def deliberately_slow_status():
            time.sleep(2.0)
            return {"slow": {"ok": False}}
        server.service_status=deliberately_slow_status
        srv=server.ThreadingHTTPServer(("127.0.0.1",0),server.Handler)
        thread=threading.Thread(target=srv.serve_forever,daemon=True)
        thread.start()
        try:
            started=time.monotonic()
            with urllib.request.urlopen(f"http://127.0.0.1:{srv.server_port}/api/health",timeout=0.75) as r:
                payload=json.loads(r.read().decode("utf-8"))
            elapsed=time.monotonic()-started
            self.assertTrue(payload["ok"])
            self.assertLess(elapsed,0.75)
            self.assertEqual(payload.get("services_endpoint"),"/api/services")
        finally:
            srv.shutdown();srv.server_close();server.service_status=original
    def test_three_experience_levels_only(self):
        self.assertEqual(set(capabilities.PROFILE_DEFAULTS),{'basic','standard','advanced'})
    def test_basic_is_human_first(self):
        b=set(capabilities.PROFILE_DEFAULTS['basic'])
        self.assertTrue({'ai-routing','projects','documents','research'}<=b)
        self.assertFalse({'development','aider','browser-automation','advanced-rag'} & b)
    def test_standard_adds_useful_project_tools(self):
        s=set(capabilities.PROFILE_DEFAULTS['standard'])
        self.assertTrue({'work-engine','development','local-ai','artifacts'}<=s)
        self.assertNotIn('aider',s)
    def test_advanced_contains_optional_power_tools(self):
        a=set(capabilities.PROFILE_DEFAULTS['advanced'])
        self.assertTrue({'aider','communications','browser-automation','advanced-rag','mcp','public-access'}<=a)
    def test_medium_hardware_recommends_standard(self):
        r=capabilities.recommend_profile({'ram_gb':13.7,'has_discrete_gpu':False})
        self.assertEqual(r['recommended_experience'],'standard')
    def test_low_hardware_recommends_basic(self):
        self.assertEqual(capabilities.recommend_profile({'ram_gb':8,'has_discrete_gpu':False})['recommended_experience'],'basic')
    def test_advanced_heavy_tools_deferred_under_20gb(self):
        p=capabilities.profile_plan('advanced',{'ram_gb':13.7,'has_discrete_gpu':False,'tools':{}})
        by={x['id']:x for x in p['capabilities']}
        self.assertFalse(by['advanced-rag']['recommended_now']);self.assertFalse(by['browser-automation']['recommended_now'])
    def test_plans_are_always_three_steps(self):
        for task in ['write a proposal','research flooring market','fix python code','email the customer','help me decide']:
            p=planner.plan(task,project_id=1)
            self.assertEqual(p['decision_count'],3);self.assertEqual(len(p['steps']),3)
    def test_file_routes_to_documents(self):
        self.assertEqual(planner.plan('review this',has_file=True)['route'],'document')
    def test_development_requires_workspace(self):
        p=planner.plan('fix this python app',project_id=0)
        self.assertEqual(p['route'],'development');self.assertTrue(p['blockers'])
    def test_manifest_set_valid_unique(self):
        rows=capabilities.manifests();ids=[x['id'] for x in rows]
        self.assertGreaterEqual(len(rows),15);self.assertEqual(len(ids),len(set(ids)))
        for x in rows:
            self.assertEqual(x.get('schema'),1);self.assertIn('name',x);self.assertIn('install_policy',x);self.assertIsInstance(x.get('permissions'),list)
    def test_support_allowlist_rejects_unknown(self):
        with self.assertRaisesRegex(ValueError,'NOT_ALLOWLISTED'):
            capabilities.install_support('pip','definitely-not-allowed')
    def test_settings_validate_experience(self):
        with self.assertRaises(ValueError):state.save_settings({'experience':'expert'})
    def test_profile_apply_preserves_mandatory_core(self):
        s=capabilities.apply_profile('basic',['documents'])
        self.assertIn('ai-routing',s['enabled_capabilities']);self.assertIn('projects',s['enabled_capabilities'])
    def test_ui_contract_five_nav_and_setup_levels(self):
        t=(ROOT/'web'/'index.html').read_text(encoding='utf-8')
        for name in ['Create','Projects','Results','Workspace','Settings','Basic','Standard','Advanced']:
            self.assertIn(name,t)
        self.assertEqual(t.count('data-page='),5)
    def test_recovered_asset_index_exists(self):
        x=json.loads((ROOT/'RECOVERED-ASSET-INDEX.json').read_text(encoding='utf-8'))
        self.assertGreaterEqual(len(x['assets']),10)
        self.assertTrue(all(a['exists'] for a in x['assets']))
    def test_bundled_workflow_bridge_present(self):
        self.assertTrue((ROOT/'recovered'/'unified-r24'/'app.py').exists())
    def test_recovered_r8_modular_core_present(self):
        for f in ['app.py','model_router.py','project_loop.py','autodev_controller.py','approval_gate.py','release_manager.py']:
            self.assertTrue((ROOT/'recovered'/'r8-core'/f).exists(),f)
    def test_recovered_aider_present(self):
        self.assertTrue((ROOT/'recovered'/'aider'/'agape_studio'/'aider_tool.py').exists())
    def test_approved_installers_visible_in_settings(self):
        t=(ROOT/'web'/'index.html').read_text(encoding='utf-8')
        self.assertIn('Approved installers',t);self.assertIn('approvedInstallers',t)
    def test_security_routes_present(self):
        t=(ROOT/'agape_mainframe'/'server.py').read_text(encoding='utf-8')
        self.assertIn('/api/security/approved-installers',t);self.assertIn('revoke_approval',t)
    def test_create_page_is_three_step_and_source_exclusive(self):
        h=(ROOT/'web'/'index.html').read_text(encoding='utf-8')
        for marker in ['1 · Source','2 · Review','3 · Result','data-source-mode="paste"','data-source-mode="upload"','data-source-mode="project"','writingCheck']:
            self.assertIn(marker,h)
        self.assertNotIn('4 · Result',h)
        self.assertNotIn('id="qualityCard"',h)
        js=(ROOT/'web'/'app.js').read_text(encoding='utf-8')
        self.assertIn("SOURCE_MODE === 'paste'",js)
        self.assertIn("SOURCE_MODE === 'upload'",js)
        self.assertIn("SOURCE_MODE === 'project'",js)
        self.assertIn('source_mode: SOURCE_MODE',js)
        self.assertNotIn('parts.join',js)



    def test_progress_bar_is_monotonic_and_stage_based(self):
        js=(ROOT/'web'/'app.js').read_text(encoding='utf-8')
        html=(ROOT/'web'/'index.html').read_text(encoding='utf-8')
        self.assertIn('Math.max(PROGRESS.last',js)
        self.assertIn('function stageBand(job)',js)
        self.assertIn('function jobProgress(job)',js)
        self.assertIn("setProgress(100, 'Finished')",js)
        self.assertIn('progressPercent',html)
        self.assertNotIn("$('progressBar').style.width = `${Number.isFinite(reported)",js)
        self.assertIn('stageCeiling',js)
        self.assertIn("'Planning'",js)
        self.assertIn('Planning document structure'.lower(),js.lower())

    def test_job_polling_has_no_fixed_completion_window(self):
        js=(ROOT/'web'/'app.js').read_text(encoding='utf-8')
        self.assertNotIn('The job did not finish in the expected polling window.',js)
        self.assertIn('Agape is still working. Reconnecting to job status',js)
        self.assertIn('while (CURRENT_JOB === id)',js)
        self.assertIn('AbortController',js)
        self.assertNotIn('n>600',js)

    def test_results_can_resume_saved_job_after_restart(self):
        js=(ROOT/'web'/'app.js').read_text(encoding='utf-8')
        self.assertIn('Check / resume',js)
        self.assertIn('external_job_id',js)
        self.assertIn('resumeRecentJob',js)
        self.assertIn('Checking the saved Agape job after restart',js)

    def test_source_preparation_runs_as_background_job(self):
        original=server.prepare_intake
        def slow_prepare(payload, progress=None):
            if progress: progress(45, 'Filling brief with AI')
            time.sleep(0.08)
            if progress: progress(96, 'Finalising')
            return {'intake': {'id':'I-ASYNC','field_count':3}}
        server.prepare_intake=slow_prepare
        try:
            started_at=time.monotonic()
            row=server._start_intake_prepare({'prepare_request_id':'TEST-ASYNC-ONE','source_mode':'paste','source_text':'hello'})
            self.assertLess(time.monotonic()-started_at,0.05)
            self.assertTrue(row['prepare_job_id'].startswith('PREP-'))
            final=None
            for _ in range(50):
                final=state.get_intake_prepare_job(row['prepare_job_id'])
                if final and final.get('status')=='COMPLETE': break
                time.sleep(0.02)
            self.assertIsNotNone(final)
            self.assertEqual(final['status'],'COMPLETE')
            self.assertEqual(final['progress'],100.0)
            self.assertEqual(final['result']['intake']['id'],'I-ASYNC')
        finally:
            server.prepare_intake=original


    def test_source_prepare_request_is_persisted_and_can_resume_after_worker_loss(self):
        jid='PREP-TEST-RESUME-V43'
        payload={'prepare_request_id':'TEST-RESUME-V43','source_mode':'paste','source_text':'resume me'}
        state.create_intake_prepare_job(jid,request=payload)
        state.claim_intake_prepare_job(jid,'OLD-MAINFRAME','Old worker')
        original=server.prepare_intake
        def fake_prepare(body,progress=None):
            self.assertEqual(body.get('source_text'),'resume me')
            if progress:progress(55,'Recovered worker running')
            return {'intake':{'id':'I-RESUMED'}}
        server.prepare_intake=fake_prepare
        try:
            row=server._ensure_intake_prepare_worker(jid)
            self.assertIsNotNone(row)
            final=None
            for _ in range(80):
                final=state.get_intake_prepare_job(jid)
                if final and final.get('status')=='COMPLETE':break
                time.sleep(0.02)
            self.assertEqual(final.get('status'),'COMPLETE')
            self.assertEqual(final.get('result',{}).get('intake',{}).get('id'),'I-RESUMED')
            self.assertGreaterEqual(int(final.get('attempts') or 0),2)
            self.assertIsNone(state.load_intake_prepare_request(jid))
        finally:
            server.prepare_intake=original
            state.delete_intake_prepare_request(jid)

    def test_source_prepare_ui_has_bounded_offline_reconnect_and_restart_detection(self):
        js=(ROOT/'web'/'app.js').read_text(encoding='utf-8')
        self.assertIn('mainframeHealth',js)
        self.assertIn('Mainframe restarted — resuming the saved source-preparation job',js)
        self.assertIn('networkErrors >= 12',js)
        self.assertIn('interrupted source request has been saved for recovery',js)

    def test_health_exposes_mainframe_instance_for_restart_detection(self):
        srv=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start()
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{srv.server_port}/api/health',timeout=2) as r:
                payload=json.loads(r.read().decode('utf-8'))
            self.assertEqual(payload.get('instance_id'),server.INSTANCE_ID)
            self.assertIn('active_source_jobs',payload)
            self.assertIsInstance(payload.get('pid'),int)
        finally:
            srv.shutdown();srv.server_close()

    def test_source_prepare_progress_never_moves_backwards(self):
        jid='PREP-TEST-MONOTONIC'
        state.create_intake_prepare_job(jid)
        state.update_intake_prepare_job(jid,status='RUNNING',progress=60,message='AI')
        row=state.update_intake_prepare_job(jid,status='RUNNING',progress=25,message='Nested step')
        self.assertEqual(row['progress'],60.0)

    def test_source_prepare_ui_uses_background_job_and_reconnects(self):
        js=(ROOT/'web'/'app.js').read_text(encoding='utf-8')
        self.assertIn("'/api/intake/start'",js)
        self.assertIn('/api/intake-prepare/',js)
        self.assertIn('waitForIntakePreparation',js)
        self.assertIn('Agape connection interrupted — reconnecting to source preparation',js)
        self.assertNotIn("await api('/api/intake',",js)


    def test_projects_page_has_recovery_action(self):
        html=(ROOT/'web'/'index.html').read_text(encoding='utf-8')
        js=(ROOT/'web'/'app.js').read_text(encoding='utf-8')
        server_src=(ROOT/'agape_mainframe'/'server.py').read_text(encoding='utf-8')
        self.assertIn('Recover past projects',html)
        self.assertIn("/api/projects/recover",js)
        self.assertIn('/api/projects/recover',server_src)

    def test_project_recovery_module_is_bundled(self):
        self.assertTrue((ROOT/'agape_mainframe'/'project_recovery.py').is_file())


    def test_review_summary_counts_established_not_none_as_completed(self):
        js=(ROOT/'web'/'app.js').read_text(encoding='utf-8')
        self.assertIn('established · ${userQuestions.length} need your input',js)
        self.assertIn('public research opportunit',js)
        self.assertNotIn('fields completed · ${questions.length} need attention',js)

if __name__=='__main__':unittest.main(verbosity=2)
