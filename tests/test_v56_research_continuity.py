import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class V56ResearchContinuityContract(unittest.TestCase):
    def test_extra_information_is_hidden_and_collapsed_until_needed(self):
        html = (ROOT / 'web' / 'index.html').read_text(encoding='utf-8')
        js = (ROOT / 'web' / 'app.js').read_text(encoding='utf-8')
        self.assertIn('id="extraInfoDetails"', html)
        self.assertIn('class="notice extra-info-details hidden"', html)
        self.assertIn('Extra information could be gathered', html)
        self.assertIn('Gather public information', html)
        self.assertIn("extra.classList.toggle('hidden', !opportunities.length)", js)
        self.assertIn("sameExtraIntake", js)
        self.assertIn("extra.open=extraWasOpen", js)
        self.assertIn('allUnresolved', js)

    def test_public_research_is_real_backend_flow(self):
        r24 = (ROOT / 'recovered' / 'unified-r24' / 'app.py').read_text(encoding='utf-8')
        studio = (ROOT / 'recovered' / 'agape-document-studio' / 'document_studio.py').read_text(encoding='utf-8')
        self.assertIn('/api/public-research', r24)
        self.assertIn('research_evidence', r24)
        self.assertIn('def public_research(', studio)
        self.assertIn('/api/public-research', studio)
        self.assertIn('route_research', studio)

    def test_bundled_flooring_research_project_exists(self):
        p = ROOT / 'web' / 'project_templates.js'
        self.assertTrue(p.is_file())
        text = p.read_text(encoding='utf-8')
        self.assertIn('flooring-recycling-north-west', text)
        self.assertIn('Commercial flooring recovery', text)
        self.assertIn('North West England', text)
        self.assertIn('Companies House', text)
        self.assertIn('public-sector', text.lower())

    def test_new_source_autosaves_project_and_refreshes_ui(self):
        bridge = (ROOT / 'agape_mainframe' / 'bridge.py').read_text(encoding='utf-8')
        js = (ROOT / 'web' / 'app.js').read_text(encoding='utf-8')
        self.assertIn('def _save_new_source_as_project', bridge)
        self.assertIn('/api/intakes/', bridge)
        self.assertIn('/project', bridge)
        self.assertIn('await loadProjects()', js)
        self.assertIn('await loadWorkspace()', js)

    def test_download_manager_is_persistent_across_jobs(self):
        js = (ROOT / 'web' / 'app.js').read_text(encoding='utf-8')
        self.assertIn("agape.download-manager.v2", js)
        self.assertIn('hydrateDownloadHistory', js)
        self.assertIn('saveDownloadManagerState', js)
        self.assertIn('row.jobId', js)

    def test_browser_qa_uses_top_level_advanced_summary(self):
        qa = (ROOT / 'agape_mainframe' / 'browser_qa.py').read_text(encoding='utf-8')
        self.assertIn('#advancedSettings > summary', qa)

    def test_windows_runtime_directories_are_self_healed(self):
        studio = (ROOT / 'recovered' / 'agape-document-studio' / 'document_studio.py').read_text(encoding='utf-8')
        self.assertIn('def ensure_runtime_paths()', studio)
        self.assertIn('ensure_runtime_paths()', studio)

    def test_v56_windows_launcher_targets_current_build(self):
        ps=(ROOT/'START-AGAPE-LATEST.ps1').read_text(encoding='utf-8')
        cmd=(ROOT/'OPEN AGAPE.cmd').read_text(encoding='utf-8')
        self.assertIn('AGAPE-MAINFRAME-V5.6.1-CANONICAL-STATUS-SYNC',ps)
        self.assertIn('START-AGAPE-LATEST.ps1',cmd)
        self.assertNotIn('V4.6',cmd)


if __name__ == '__main__':
    unittest.main(verbosity=2)
