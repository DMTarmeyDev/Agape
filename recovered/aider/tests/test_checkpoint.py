import json
import tempfile
import unittest
from pathlib import Path

from agape_studio.checkpoints import CheckpointService


class CheckpointTests(unittest.TestCase):
    def test_checkpoint_has_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / 'project'; project.mkdir(); (project / 'a.txt').write_text('A', encoding='utf-8')
            result = CheckpointService(root / 'checkpoints').create(str(project), 'known-good')
            self.assertTrue(result['ok'])
            manifest = Path(result['path']) / 'checkpoint-manifest.json'
            self.assertTrue(manifest.is_file())
            payload = json.loads(manifest.read_text(encoding='utf-8'))
            self.assertEqual(payload['files'][0]['path'], 'a.txt')


if __name__ == '__main__': unittest.main()
