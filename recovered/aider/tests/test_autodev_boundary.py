import unittest
from agape_studio.autodev import AutoDevBoundary

class AutoDevBoundaryTests(unittest.TestCase):
    def test_boundary_is_explicit(self):
        status=AutoDevBoundary().status()
        self.assertTrue(status['ok'])
        self.assertFalse(status['active'])
        self.assertEqual(status['phase'],'future-v0.6')

if __name__ == '__main__': unittest.main()
