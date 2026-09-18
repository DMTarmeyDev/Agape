import inspect, pathlib, sys, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agape_mainframe import bridge, state

class PerformanceAndLogicTests(unittest.TestCase):
    def test_new_install_defaults_to_faster_standard_quality(self):
        self.assertEqual(state.DEFAULT_SETTINGS['quality'],'standard')
    def test_document_service_uses_private_bundled_python_service(self):
        src=inspect.getsource(bridge.ensure_existing_services)
        self.assertIn('8851',src)
        self.assertIn('EXPECTED_DOC_VERSION',src)
        self.assertNotIn('OPEN-AGAPE-DOCUMENT-STUDIO.ps1',src)
    def test_workflow_bridge_uses_private_compatible_service(self):
        self.assertEqual(bridge.R24,'http://127.0.0.1:8852')
        self.assertEqual(bridge.DOC,'http://127.0.0.1:8851')
        self.assertEqual(bridge.EXPECTED_R24_BUILD,'AGAPE-UNIFIED-R4.7-TARGETED-VALIDATION-REPAIR')
    def test_boot_does_not_require_full_setup_probe_when_setup_complete(self):
        js=(ROOT/'web'/'app.js').read_text(encoding='utf-8')
        health_pos=js.index("api('/api/health')")
        setup_pos=js.index("api('/api/setup/status')")
        self.assertLess(health_pos,setup_pos)
        self.assertIn('if (!SETUP.settings.setup_complete)',js)
    def test_save_and_continue_buttons_removed_from_create_flow(self):
        html=(ROOT/'web'/'index.html').read_text(encoding='utf-8')
        self.assertNotIn('id="saveEdits"',html)
        self.assertNotIn('id="toQuality"',html)
        self.assertNotIn('id="qualityCard"',html)
        self.assertIn('id="createDocument"',html)

if __name__=='__main__': unittest.main(verbosity=2)
