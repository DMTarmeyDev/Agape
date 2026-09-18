import pathlib, sys, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agape_mainframe.writing_quality import safe_clean, check_text

class WritingQualityTests(unittest.TestCase):
    def test_safe_clean_fixes_only_high_confidence_mechanical_errors(self):
        text='teh buiness plan  has a space before punctuation , and i need it.'
        cleaned,changes=safe_clean(text)
        self.assertIn('the business plan has a space before punctuation, and i need it.',cleaned)
        self.assertGreaterEqual(len(changes),3)
    def test_checker_keeps_names_numbers_and_uk_terms(self):
        text='M6 Flooring proposes £150,000 for the Preston programme and colour catalogue.'
        cleaned,_=safe_clean(text)
        self.assertEqual(cleaned,text)
        report=check_text(text)
        self.assertEqual(report['language'],'en-GB')
        self.assertIn('issue_count',report)
    def test_escaped_newline_markers_do_not_become_fake_words(self):
        text=r"Please complate this.\nAgape will continue.\nBefore the next step dont choose the wrong eption."
        cleaned,_=safe_clean(text)
        self.assertIn("Please complete this.\nAgape will continue.\nBefore the next step don't choose the wrong option.", cleaned)
        report=check_text(text)
        bad={str(x.get('word') or '').lower() for x in report['spelling_suggestions']}
        self.assertFalse({'nagape','nbefore','nnext'} & bad)
        self.assertEqual(report['escaped_line_breaks_normalized'],2)


    def test_technical_terms_and_structured_json_are_not_prose_corrections(self):
        text=r'''{ "source_type": "saved_agape_project_snapshot", "engine": "ollama", "stdout": "ok" }\nNormal prose i wrote here.'''
        report=check_text(text)
        pairs={(str(x.get("word") or "").lower(),str(x.get("suggestion") or "").lower()) for x in report["spelling_suggestions"]}
        self.assertNotIn(("ollama","llama"),pairs)
        self.assertNotIn(("stdout","stout"),pairs)
        self.assertGreaterEqual(report.get("structured_lines_skipped",0),1)

    def test_checker_reports_repeated_word_grammar_issue(self):
        report=check_text('This is the the proposal.')
        self.assertTrue(any(x.get('issue')=='repeated_word' for x in report['grammar_suggestions']))

if __name__=='__main__': unittest.main(verbosity=2)
