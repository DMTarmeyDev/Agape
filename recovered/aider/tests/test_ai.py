import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from agape_studio.ai import AIRouter, FakeProvider, OllamaProvider
from agape_studio.database import StudioDatabase


class AIModelTests(unittest.TestCase):
    def test_fake_model_live_contract_and_history(self):
        with tempfile.TemporaryDirectory() as td:
            db = StudioDatabase(Path(td) / 'db.sqlite3')
            router = AIRouter(db, [FakeProvider(model_name='qwen-test-coder:7b')])
            result = router.chat(td, 'fix the code', task='code', context='x=1')
            self.assertTrue(result['ok'])
            self.assertEqual(result['model'], 'qwen-test-coder:7b')
            self.assertIn('fix the code', result['reply'])
            self.assertEqual(db.table_counts()['ai_history'], 2)

    def test_ollama_uses_longer_chat_timeout_than_discovery(self):
        provider = OllamaProvider(timeout=3, chat_timeout=90)
        seen = []

        class Response:
            def __init__(self, payload):
                self.payload = payload
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return self.payload

        def fake_urlopen(req, timeout=None):
            seen.append(timeout)
            if req.full_url.endswith('/api/tags'):
                return Response(b'{"models":[{"name":"qwen2.5-coder:1.5b-instruct"}]}')
            return Response(b'{"message":{"content":"PASS"}}')

        with patch('urllib.request.urlopen', side_effect=fake_urlopen):
            self.assertEqual(provider.models(), ['qwen2.5-coder:1.5b-instruct'])
            self.assertEqual(provider.chat('qwen2.5-coder:1.5b-instruct', [{'role':'user','content':'PASS'}]), 'PASS')
        self.assertEqual(seen, [3, 90])


if __name__ == '__main__': unittest.main()
