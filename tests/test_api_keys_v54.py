import json, os, pathlib, tempfile, unittest
from unittest import mock

ROOT=pathlib.Path(__file__).resolve().parents[1]
os.environ.setdefault('AGAPE_MAINFRAME_DATA',str(pathlib.Path(tempfile.gettempdir())/'agape-mainframe-v54-keytests'))
from agape_mainframe import api_keys

class ApiKeyV54Tests(unittest.TestCase):
    def setUp(self):
        # Keep credential tests completely isolated from the developer/user machine.
        # Never read or write the real OS credential store during pytest.
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

        old_data_root = api_keys.DATA_ROOT
        old_key_file = api_keys.KEY_FILE
        self.addCleanup(setattr, api_keys, 'KEY_FILE', old_key_file)
        self.addCleanup(setattr, api_keys, 'DATA_ROOT', old_data_root)
        api_keys.DATA_ROOT = pathlib.Path(self._tmp.name)
        api_keys.KEY_FILE = api_keys.DATA_ROOT / 'api-keys.json'

        keyring_patch = mock.patch.object(api_keys, '_keyring_module', return_value=None)
        keyring_patch.start()
        self.addCleanup(keyring_patch.stop)

        previous_env = {meta['env']: os.environ.get(meta['env']) for meta in api_keys.PROVIDERS.values()}
        def restore_env():
            for name, value in previous_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        self.addCleanup(restore_env)
        for name in previous_env:
            os.environ.pop(name, None)

    def test_public_template_contains_no_key_values(self):
        raw=json.loads((ROOT/'API-KEYS.template.json').read_text(encoding='utf-8'))
        self.assertIn('keys',raw)
        self.assertTrue(raw['keys'])
        self.assertTrue(all(v=='' for v in raw['keys'].values()))

    def test_local_key_file_is_gitignored(self):
        text=(ROOT/'.gitignore').read_text(encoding='utf-8')
        self.assertIn('API-KEYS.local.json',text)
        self.assertIn('api-keys.json',text)

    def test_save_status_never_returns_secret(self):
        secret='openai-test-not-real-12345'
        api_keys.set_key('openai',secret)
        st=api_keys.status()
        row=next(x for x in st['providers'] if x['id']=='openai')
        self.assertTrue(row['configured'])
        self.assertNotIn(secret,json.dumps(st))
        self.assertEqual(os.environ.get('OPENAI_API_KEY'),secret)

    def test_import_template_shape_and_preserve_existing(self):
        api_keys.set_key('openai','existing-not-real')
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td)/'API-KEYS.local.json'
            p.write_text(json.dumps({'keys':{'openai':'replacement-not-real','anthropic':'anthropic-not-real'}}),encoding='utf-8')
            result=api_keys.import_key_file(p,overwrite=False)
        self.assertTrue(result['ok'])
        self.assertEqual(result['imported'],['anthropic'])
        self.assertEqual(api_keys._read_private()['openai'],'existing-not-real')

    def test_remove_key(self):
        api_keys.set_key('groq','gsk-not-real')
        api_keys.remove_key('groq')
        self.assertFalse(next(x for x in api_keys.status()['providers'] if x['id']=='groq')['configured'])

    def test_ui_has_one_key_at_a_time_setup(self):
        h=(ROOT/'web'/'index.html').read_text(encoding='utf-8')
        j=(ROOT/'web'/'app.js').read_text(encoding='utf-8')
        for marker in ['Connect an AI provider (optional)','setupKeyProvider','setupKeyValue','Save this key','API-KEYS.local.json']:
            self.assertIn(marker,h)
        for route in ['/api/keys/status','/api/keys/set','/api/keys/import','/api/keys/remove']:
            self.assertIn(route,(ROOT/'agape_mainframe'/'server.py').read_text(encoding='utf-8'))
        self.assertIn('setupKeysContinue',j)

if __name__=='__main__': unittest.main()
