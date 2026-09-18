import tempfile
import unittest
from pathlib import Path

from agape_studio.database import StudioDatabase
from agape_studio.quality import QUALITY_CATALOG


class QualityLedgerTests(unittest.TestCase):
    def test_passed_and_open_are_separated_and_persistent(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'db.sqlite3'
            db=StudioDatabase(path)
            db.seed_quality_items(QUALITY_CATALOG)
            db.set_quality_item('FREE-001','Free AI','Free online AI provider adapter','PASS','verified','report.md')
            first=db.quality_status()
            self.assertEqual(first['passed_count'],1)
            self.assertGreater(first['open_count'],0)
            db2=StudioDatabase(path)
            second=db2.quality_status()
            self.assertEqual(second['passed_count'],1)
            self.assertEqual(second['passed'][0]['item_id'],'FREE-001')


if __name__ == '__main__': unittest.main()
