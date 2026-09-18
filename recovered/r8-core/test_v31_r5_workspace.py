import unittest
from pathlib import Path
class R5WorkspaceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls): cls.html=Path(__file__).with_name("index.html").read_text(encoding="utf-8")
 def test_two_top_level_pages(self):
  self.assertIn('data-page="chat" class="active">Project Workspace</button>',self.html)
  self.assertIn('data-page="settings">Settings</button>',self.html)
 def test_agent_team_on_one_page(self):
  for a in ['planner','developer','tester','debugger','reviewer','release','supervisor']: self.assertIn('id="agent-'+a+'"',self.html)
 def test_settings_categories(self):
  for x in ['General','Project','Agents','Models & Providers','Automation','Testing & Safety','Memory & Database','Tools & Terminal','Templates','Advanced']: self.assertIn(x,self.html)
 def test_auto_choose_still_requires_project(self):
  self.assertIn('id="auto-choose-model"',self.html)
  self.assertIn('wizardAutoChoose',self.html)
  self.assertIn('wizardInstructionReady',self.html)
if __name__=="__main__": unittest.main()
