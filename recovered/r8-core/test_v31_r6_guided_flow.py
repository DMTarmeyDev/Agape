from pathlib import Path
import unittest

class R6GuidedFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(__file__).resolve().parent
        cls.html=(cls.root/'index.html').read_text(encoding='utf-8')
        cls.app=(cls.root/'app.py').read_text(encoding='utf-8')
        cls.orch=(cls.root/'orchestrator.py').read_text(encoding='utf-8')
    def test_guided_order(self):
        for x in ['wizard-step-1','wizard-step-2','wizard-step-3','wizard-step-4','wizard-step-5']:
            self.assertIn(x,self.html)
        self.assertIn('Complete one step at a time',self.html)
    def test_plain_text_project_information_first(self):
        self.assertIn('project-instructions-text',self.html)
        self.assertIn('Paste or type the project information below',self.html)
        self.assertIn('Save Project Information',self.html)
        self.assertNotIn('project-template-file',self.html)
        self.assertNotIn('tpl-goal',self.html)
        self.assertIn('DMT-PROJECT-TEMPLATE-R1',self.html)
    def test_template_api_and_context(self):
        self.assertIn('/api/project-template/status',self.app)
        self.assertIn('/api/project-template/activate',self.app)
        self.assertIn('AGAPE PROJECT TEMPLATE ACTIVE',self.orch)
    def test_auto_choose_after_instruction(self):
        self.assertIn('wizardAutoChoose',self.html)
        self.assertIn('wizardInstructionReady',self.html)
