import importlib.util, pathlib, tempfile, unittest
from unittest import mock
import requests

ROOT=pathlib.Path(__file__).resolve().parents[1]
DOC=ROOT/'recovered'/'agape-document-studio'/'document_studio.py'
spec=importlib.util.spec_from_file_location('agape_doc_provider_test',DOC)
ds=importlib.util.module_from_spec(spec); spec.loader.exec_module(ds)

class ProviderReliabilityTests(unittest.TestCase):
    def setUp(self):
        ds._AUTH_CACHE.clear(); ds._AUTH_SESSION_HOLD.clear(); ds.AI_PREFLIGHT_CACHE.clear(); ds.AI_RUN_DISABLED.clear()

    def test_stale_chatgpt_session_does_not_trust_missing_executable(self):
        ds._AUTH_SESSION_HOLD['chatgpt']={'provider':'chatgpt','expires_at':ds.time.time()+600,'executable':r'C:\missing\codex.exe'}
        with mock.patch.object(ds,'_which_cli',return_value=None):
            got=ds._run_status_command('chatgpt')
        self.assertFalse(got['logged_in'])
        self.assertEqual(got['status'],'NOT_INSTALLED')
        self.assertNotIn('chatgpt',ds._AUTH_SESSION_HOLD)

    def test_ollama_preflight_fails_fast_when_live_probe_times_out(self):
        with mock.patch.object(ds,'_ollama_models',return_value=['qwen2.5-coder:1.5b-instruct']), \
             mock.patch.object(ds,'ensure_ollama_engine',return_value={'ok':True,'running':True,'models':['qwen2.5-coder:1.5b-instruct']}), \
             mock.patch.object(ds.requests,'post',side_effect=requests.Timeout('probe timeout')):
            got=ds._provider_runtime_preflight('ollama',force=True)
        self.assertFalse(got['ok'])
        self.assertIn('probe timeout',got['detail'])

    def test_ai_generate_returns_no_ready_provider_when_all_preflights_fail(self):
        def no(provider,task='general',force=False):
            return {'ok':False,'provider':provider,'detail':'not ready'}
        with mock.patch.object(ds,'_provider_order_for_task',return_value=['chatgpt','ollama']), \
             mock.patch.object(ds,'_provider_runtime_preflight',side_effect=no):
            with self.assertRaisesRegex(RuntimeError,'NO_READY_AI_PROVIDER'):
                ds.ai_generate('hello',task='business_writing')

    def test_local_fallback_prefers_small_model_by_default(self):
        self.assertEqual(ds.AI_PROVIDER_MODELS['ollama'],'qwen2.5-coder:1.5b-instruct')

    def test_review_pool_skips_dead_online_reviewers_and_adds_healthy_local(self):
        def pf(provider,task='general',force=False):
            if provider=='ollama': return {'ok':True,'provider':'ollama','model':'qwen2.5-coder:1.5b-instruct'}
            return {'ok':False,'provider':provider,'detail':'not usable'}
        with mock.patch.object(ds,'_provider_credentials',return_value=True), \
             mock.patch.object(ds,'_provider_runtime_preflight',side_effect=pf):
            ready,errors=ds._review_ready_pool(['chatgpt','gemini','xai'])
        self.assertEqual(ready,['ollama'])
        self.assertEqual({x['provider'] for x in errors},{'chatgpt','gemini','xai'})

    def test_review_worker_uses_ollama_if_online_reviewer_fails_at_generation(self):
        ds.REVIEW_JOBS.clear()
        review={'provider':'ollama','provider_name':'Ollama','model':'qwen2.5-coder:1.5b-instruct','scores':{'overall':8},'short_summary':'ok'}
        def one(provider,draft,title,context):
            if provider=='xai': raise RuntimeError('no credits')
            return dict(review)
        with mock.patch.object(ds,'_review_ready_pool',return_value=(['xai'],[])), \
             mock.patch.object(ds,'_provider_credentials',side_effect=lambda p:p=='ollama'), \
             mock.patch.object(ds,'_provider_runtime_preflight',return_value={'ok':True,'provider':'ollama'}), \
             mock.patch.object(ds,'_review_one_provider',side_effect=one), \
             mock.patch.object(ds,'_lead_review',return_value={'revised_draft':'A revised document with enough content to be valid.','lead_provider':'ollama'}):
            ds._multi_review_worker('R-FALLBACK',{'draft':'This is a finished document with enough content for a reviewer to inspect properly.','title':'Plan','reviewers':['xai']})
        got=ds.multi_review_status('R-FALLBACK')
        self.assertEqual(got['state'],'ready')
        self.assertEqual(got['lead']['lead_provider'],'ollama')
        self.assertTrue(any(x.get('provider')=='xai' for x in got.get('errors',[])))

    def test_lead_review_failure_returns_unavailable_not_failed(self):
        ds.REVIEW_JOBS.clear()
        review={'provider':'ollama','provider_name':'Ollama','model':'local','scores':{'overall':8},'short_summary':'ok'}
        with mock.patch.object(ds,'_review_ready_pool',return_value=(['ollama'],[])), \
             mock.patch.object(ds,'_review_one_provider',return_value=review), \
             mock.patch.object(ds,'_lead_review',side_effect=RuntimeError('lead failed')):
            ds._multi_review_worker('R-LEAD',{'draft':'This is a finished document with enough content for a reviewer to inspect properly.','title':'Plan','reviewers':['ollama']})
        got=ds.multi_review_status('R-LEAD')
        self.assertEqual(got['state'],'unavailable')
        self.assertEqual(got['error'],'LEAD_REVIEW_UNAVAILABLE')

    def test_review_worker_marks_unavailable_instead_of_failed_when_no_reviewer_ready(self):
        ds.REVIEW_JOBS.clear()
        with mock.patch.object(ds,'_review_ready_pool',return_value=([],[{'provider':'chatgpt','error':'missing path'}])):
            ds._multi_review_worker('R-NONE',{'draft':'This is a finished document with enough content for a reviewer to inspect properly.','title':'Plan','reviewers':['chatgpt']})
        got=ds.multi_review_status('R-NONE')
        self.assertEqual(got['state'],'unavailable')
        self.assertEqual(got['error'],'NO_READY_REVIEW_PROVIDER')

if __name__=='__main__': unittest.main(verbosity=2)
