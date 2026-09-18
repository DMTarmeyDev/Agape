import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class ReleaseScriptTests(unittest.TestCase):
    def test_installer_is_temp_first_and_quality_gated(self):
        text=(ROOT/'INSTALL-TEST-REPORT.ps1').read_text(encoding='utf-8')
        for marker in ('AgapeAIStudio','candidate-','verify_manifest.py','run_full_test_process.py','--packaged','BLOCKED_TEST_FAILURE','BLOCKED_OPEN_QUALITY_ITEMS','current.txt','previous.txt','REPORT_TO_UPLOAD','PAID_AUTO_FALLBACK=DISABLED'):
            self.assertIn(marker,text)


    def test_aider_install_is_isolated_and_pinned(self):
        text=(ROOT/'INSTALL-AIDER.ps1').read_text(encoding='utf-8')
        for marker in ("$Version = '0.86.0'", 'AgapeAIStudio\\tools', '-m venv', 'aider-chat==', 'AIDER_INSTALL=PASS'):
            self.assertIn(marker,text)

    def test_external_probes_are_process_isolated_and_bounded(self):
        text=(ROOT/'scripts'/'run_full_test_process.py').read_text(encoding='utf-8')
        for marker in ('run_live_case.py', 'external_timeouts', 'real_ollama_probe', 'real_openrouter_catalog_optional', 'real_aider_probe', 'subprocess.run(', 'timeout=timeout', 'EXTERNAL_PROBE_TIMEOUT'):
            self.assertIn(marker,text)

    def test_powershell_51_no_known_ps7_operators(self):
        for name in ('INSTALL-TEST-REPORT.ps1','INSTALL-AIDER.ps1','RUN-ALL-TESTS.ps1','TEST-AFTER-PATCH.ps1','START-STUDIO.ps1'):
            text=(ROOT/name).read_text(encoding='utf-8')
            self.assertNotIn(' && ',text,name)
            self.assertNotIn(' || ',text,name)
            self.assertNotIn('??',text,name)
            self.assertNotIn('ForEach-Object -Parallel',text,name)

if __name__=='__main__':unittest.main()
