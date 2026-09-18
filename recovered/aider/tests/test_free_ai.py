import tempfile
import unittest
from pathlib import Path

from agape_studio.ai import AIRouter, FakeProvider
from agape_studio.connections import ConnectionService
from agape_studio.database import StudioDatabase
from agape_studio.providers import OpenRouterFreeProvider, is_zero_cost_text_model
from tests.fake_openrouter import fake_openrouter


class FreeAITests(unittest.TestCase):
    def test_zero_cost_filter_blocks_paid_and_nontext(self):
        self.assertTrue(is_zero_cost_text_model({'id':'x','pricing':{'prompt':'0','completion':'0','request':None},'architecture':{'output_modalities':['text']}}))
        self.assertFalse(is_zero_cost_text_model({'id':'x','pricing':{'prompt':'0.01','completion':'0','request':'0'},'architecture':{'output_modalities':['text']}}))
        self.assertFalse(is_zero_cost_text_model({'id':'x','pricing':{'prompt':'0','completion':'0','request':'0'},'architecture':{'output_modalities':['image']}}))

    def test_openrouter_discovery_exposes_only_free_text_models(self):
        with fake_openrouter() as base:
            provider=OpenRouterFreeProvider(base_url=base,api_key='test-key')
            self.assertEqual(provider.models(), ['acme/coder-free','acme/general-free'])
            self.assertNotIn('acme/paid-model', provider.models())

    def test_best_free_coding_model(self):
        with fake_openrouter() as base:
            provider=OpenRouterFreeProvider(base_url=base,api_key='test-key')
            rec=provider.recommend('repair python code and run tests')
            self.assertEqual(rec['model'],'acme/coder-free')
            self.assertTrue(rec['is_free'])

    def test_local_to_free_fallback(self):
        with tempfile.TemporaryDirectory() as td, fake_openrouter() as base:
            db=StudioDatabase(Path(td)/'db.sqlite3')
            local=FakeProvider(provider_id='local-fail',model_name='qwen-coder:7b',tier='local',fail_chat=True)
            free=OpenRouterFreeProvider(base_url=base,api_key='test-key')
            router=AIRouter(db,[local,free])
            result=router.chat(td,'repair this python bug',task='code',mode='auto')
            self.assertEqual(result['provider'],'openrouter-free')
            self.assertEqual(result['model'],'acme/coder-free')
            self.assertGreaterEqual(result['fallbacks_used'],1)
            self.assertTrue(any(x['status']=='FAIL' for x in db.connection_test_history()))
            self.assertTrue(any(x['status']=='PASS' for x in db.connection_test_history()))

    def test_free_mode_never_routes_to_local(self):
        with tempfile.TemporaryDirectory() as td, fake_openrouter() as base:
            db=StudioDatabase(Path(td)/'db.sqlite3')
            local=FakeProvider(provider_id='local',model_name='qwen-coder:7b',tier='local')
            free=OpenRouterFreeProvider(base_url=base,api_key='test-key')
            router=AIRouter(db,[local,free])
            result=router.chat(td,'code',task='code',mode='free')
            self.assertEqual(result['tier'],'free-online')

    def test_connection_test_persists_provider_and_each_model(self):
        with tempfile.TemporaryDirectory() as td, fake_openrouter() as base:
            db=StudioDatabase(Path(td)/'db.sqlite3')
            provider=OpenRouterFreeProvider(base_url=base,api_key='test-key')
            router=AIRouter(db,[provider])
            service=ConnectionService(router)
            result=service.test_provider('openrouter-free',generation=True)
            self.assertTrue(result['ok'])
            self.assertEqual(result['generation']['status'],'PASS')
            history=db.connection_test_history()
            self.assertTrue(any(x['source']=='catalog' and x['status']=='PASS' for x in history))
            self.assertEqual(sum(1 for x in history if x['source']=='eligibility' and x['status']=='PASS'),2)
            self.assertTrue(any(x['source']=='generation-probe' and x['status']=='PASS' for x in history))

    def test_missing_key_allows_catalog_but_not_generation(self):
        with tempfile.TemporaryDirectory() as td, fake_openrouter() as base:
            db=StudioDatabase(Path(td)/'db.sqlite3')
            provider=OpenRouterFreeProvider(base_url=base,api_key='')
            router=AIRouter(db,[provider])
            service=ConnectionService(router)
            result=service.test_provider('openrouter-free',generation=True)
            self.assertTrue(result['ok'])
            self.assertEqual(result['generation']['status'],'SETUP_REQUIRED')


if __name__ == '__main__': unittest.main()
