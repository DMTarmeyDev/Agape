import unittest
from unittest.mock import patch
from agape_mainframe.state import DEFAULT_SETTINGS
from agape_mainframe.coding_tools import tool_status
from agape_mainframe.planner import plan

class CodingToolsV48Test(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(DEFAULT_SETTINGS['coding_model_mode'],'auto-coding')
        self.assertEqual(DEFAULT_SETTINGS['coding_agent'],'auto')
        self.assertEqual(DEFAULT_SETTINGS['code_manager'],'agape')
    def test_registry(self):
        data=tool_status()
        agents={x['id'] for x in data['agents']}
        managers={x['id'] for x in data['managers']}
        self.assertTrue({'agape-native','aider','openhands','open-interpreter','compare'} <= agents)
        self.assertTrue({'agape','theia-lite','theia-full','vscode'} <= managers)
    def test_development_plan_coding_metadata(self):
        # This test verifies the factory default, not the current user's saved
        # coding preference. Keep it isolated from live Settings data.
        with patch('agape_mainframe.planner.load_settings', return_value=dict(DEFAULT_SETTINGS)):
            p=plan('refactor the Python codebase',project_id=1)
        self.assertEqual(p['route'],'development')
        self.assertIn('coding',p)
        self.assertEqual(p['coding']['model_mode'],'auto-coding')

if __name__=='__main__': unittest.main()
