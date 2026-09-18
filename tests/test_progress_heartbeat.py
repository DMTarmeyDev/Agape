from __future__ import annotations
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class ProgressHeartbeatTests(unittest.TestCase):
    def test_browser_shows_still_active_when_percent_does_not_change(self):
        js=(ROOT/'web'/'app.js').read_text(encoding='utf-8')
        self.assertIn('still active',js)
        self.assertIn('lastChangedAt',js)

    def test_document_worker_has_monotonic_heartbeat_progress(self):
        py=(ROOT/'recovered'/'agape-document-studio'/'document_studio.py').read_text(encoding='utf-8')
        self.assertIn('def _agent_create_job_heartbeat',py)
        self.assertIn("max(float(row.get('progress') or 0)",py)
        self.assertIn('still working',py)

if __name__=='__main__': unittest.main()
