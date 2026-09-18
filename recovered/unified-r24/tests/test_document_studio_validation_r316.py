import sys
import unittest
from pathlib import Path
from unittest import mock

DOC_DIR = Path(__file__).resolve().parents[2] / "agape-document-studio"
if str(DOC_DIR) not in sys.path:
    sys.path.insert(0, str(DOC_DIR))
import document_studio as ds


class DocumentStudioValidationR316Tests(unittest.TestCase):
    def test_findings_and_analysis_are_repaired_individually_past_minimum(self):
        plan = {"doc_type": "Business Report", "required_sections": ["Findings", "Analysis"]}
        draft = "# Findings\nThin.\n\n# Analysis\nShort."
        calls = []

        def fake_generate(prompt, system, **kwargs):
            calls.append(prompt)
            heading = "Findings" if "TARGET SECTION: # Findings" in prompt else "Analysis"
            body = (
                "This section uses only the supplied project context and research evidence. "
                "It separates established information from assumptions and explains the practical implications for decision-makers. "
                "Where evidence is incomplete, that limitation is stated clearly and no private facts or unsupported figures are invented. "
            ) * 3
            return {"content": f"# {heading}\n{body}", "provider": "test", "model": "test-model"}

        with mock.patch.object(ds, "ai_generate", side_effect=fake_generate), \
             mock.patch.object(ds, "_ai_context_snapshot", return_value={}), \
             mock.patch.object(ds, "_research_for_prompt", return_value="research"):
            repaired, audit, models = ds.repair_draft({}, plan, {}, draft, "auto", max_rounds=1)

        self.assertTrue(audit["ok"], audit)
        self.assertEqual(audit["short"], [])
        self.assertGreaterEqual(len(ds._r316_section_body(repaired, "Findings")), ds._r310_min_section_chars("Business Report", "Findings"))
        self.assertGreaterEqual(len(ds._r316_section_body(repaired, "Analysis")), ds._r310_min_section_chars("Business Report", "Analysis"))
        self.assertTrue(any("REPAIR_TARGET_BODY_CHARACTERS" in p for p in calls))
        self.assertTrue(any("TARGET SECTION: # Findings" in p for p in calls))
        self.assertTrue(any("TARGET SECTION: # Analysis" in p for p in calls))
        self.assertEqual({m.get("section") for m in models}, {"Findings", "Analysis"})

    def test_short_only_after_repairs_is_recoverable_warning_but_missing_is_not(self):
        self.assertTrue(ds._r316_short_only_warning({"missing": [], "short": ["Findings", "Analysis"]}))
        self.assertFalse(ds._r316_short_only_warning({"missing": ["Findings"], "short": []}))
        self.assertFalse(ds._r316_short_only_warning({"missing": [], "short": []}))


if __name__ == "__main__":
    unittest.main()
