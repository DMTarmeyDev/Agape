import pathlib, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]

class HumanFirstWorkflowContract(unittest.TestCase):
    def test_human_first_document_flow_is_visible(self):
        h=(ROOT/'web'/'index.html').read_text(encoding='utf-8')
        for marker in [
            '1 · Source','2 · Review','3 · Result','Paste text','Upload document','Saved project','Prepare with AI',
            'Agape prepared the brief','Extra information could be gathered','Gather public information','Change the brief with AI','Create Now','Gold Standard','Create result'
        ]:
            self.assertIn(marker,h)
        self.assertNotIn('4 · Result',h)
        self.assertNotIn('id="qualityCard"',h)
    def test_document_revision_control_exists(self):
        js=(ROOT/'web'/'app.js').read_text(encoding='utf-8')
        self.assertIn('Change this result with AI',js)
        self.assertIn('/revise',js)
        self.assertIn('wrapper.job || wrapper',js)
    def test_revision_backend_contract_exists(self):
        r=(ROOT/'recovered'/'unified-r24'/'app.py').read_text(encoding='utf-8')
        for marker in ['def revise_intake_with_ai','def revise_job_with_ai','revision_of','lineage_root','revision_number','revised_draft']:
            self.assertIn(marker,r)
    def test_mainframe_exposes_revision_endpoints(self):
        s=(ROOT/'agape_mainframe'/'server.py').read_text(encoding='utf-8')
        for marker in ['/api/intake','/improve','/answers','/revise']:
            self.assertIn(marker,s)
    def test_old_settings_are_not_top_level(self):
        h=(ROOT/'web'/'index.html').read_text(encoding='utf-8')
        self.assertIn('<summary>Advanced</summary>',h)
        # One current router control; no old duplicate provider/model selectors in normal Settings.
        self.assertEqual(h.count('id="settingRouter"'),1)
        for old in ['aiProvider','aiModel','reviewAfterCreate','leadReviewer','ingestionEngine','ragEnabled']:
            self.assertNotIn('id="'+old+'"',h)
    def test_active_recovered_capabilities_are_in_source_tree(self):
        required=[
            'recovered/agape-document-studio/document_studio.py',
            'recovered/agape-systems-engine/engine_entry.py',
            'recovered/agape-artifacts/agape_artifacts_tool.py',
            'recovered/agape-communications-hub/agape_comms_hub.py',
            'recovered/r8-core/app.py','recovered/aider/agape_studio/aider_tool.py'
        ]
        for rel in required:self.assertTrue((ROOT/rel).exists(),rel)

if __name__=='__main__': unittest.main(verbosity=2)
