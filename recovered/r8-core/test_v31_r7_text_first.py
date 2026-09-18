from pathlib import Path
import unittest

class R7TextFirstTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html=(Path(__file__).resolve().parent/'index.html').read_text(encoding='utf-8')
    def test_text_first_ui(self):
        self.assertIn('id="project-instructions-text"', self.html)
        self.assertIn('Save Project Information', self.html)
        self.assertNotIn('id="project-template-file"', self.html)
        self.assertNotIn('Fill blank template', self.html)
    def test_text_wrapped_into_template(self):
        self.assertIn("projectInstructionTemplate", self.html)
        self.assertIn("project_brief:{plain_text:text,source:String(window.DMT_PROJECT_INFO_SOURCE||'pasted-text')}", self.html)
        self.assertIn("system_instruction:text", self.html)
    def test_next_step_still_progressive(self):
        self.assertIn("wizardResetAfter(2)", self.html)
        self.assertIn("wizardShow('wizard-step-3',wizardTemplateReady)", self.html)
