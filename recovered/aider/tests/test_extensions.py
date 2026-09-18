import unittest
from pathlib import Path

from agape_studio.extensions import ExtensionHost


ROOT = Path(__file__).resolve().parents[1]


class ExtensionTests(unittest.TestCase):
    def test_discovery_and_tools(self):
        host = ExtensionHost(ROOT / 'extensions')
        ids = {x['id'] for x in host.discover()}
        self.assertEqual(ids, {'agape.basic-formatter', 'agape.spell-checker', 'agape.code-cleaner'})
        formatted = host.run('agape.basic-formatter', 'format_text', {'text': 'x  \n\n'})
        self.assertEqual(formatted['result']['text'], 'x\n')
        spelling = host.run('agape.spell-checker', 'check_text', {'text': 'teh adress'})
        self.assertEqual(spelling['result']['count'], 2)
        cleaner = host.run('agape.code-cleaner', 'inspect_text', {'text': 'x \n\tbad'})
        self.assertGreaterEqual(cleaner['result']['count'], 2)


if __name__ == '__main__': unittest.main()
