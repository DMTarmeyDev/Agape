from pathlib import Path
import base64, io, json, unittest, zipfile

class R8DocumentImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).resolve().parent
        cls.html=(root/'index.html').read_text(encoding='utf-8')
        cls.app=(root/'app.py').read_text(encoding='utf-8')
        cls.config=(root/'config.py').read_text(encoding='utf-8')
    def test_ui_has_text_and_document_choice(self):
        self.assertIn('id="project-instructions-text"',self.html)
        self.assertIn('id="project-document-choose"',self.html)
        self.assertIn('id="project-document-file"',self.html)
        self.assertIn('Choose Document',self.html)
        self.assertIn('Save Project Information',self.html)
    def test_import_loads_same_text_box(self):
        self.assertIn("$('project-instructions-text').value=String(d.text||'')",self.html)
        self.assertIn('Review it, then choose Save Project Information.',self.html)
    def test_backend_supports_docx_and_text(self):
        self.assertIn('/api/project-template/import-document',self.app)
        self.assertIn('suffix==".docx"',self.app)
        self.assertIn('zipfile.ZipFile',self.app)
        self.assertIn('DOCUMENT_TYPE_NOT_SUPPORTED',self.app)
    def test_build(self):
        self.assertIn('DMT-CORE-V3.1-EARLY-ALPHA-R8',self.config)
