from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import autodev_pipeline
import context_pack
import evidence_bundle
import goal_spec
import patch_plan
import patch_transaction
import repair_cycle
import test_matrix
import work_breakdown
import workspace_snapshot


class V18FeatureTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="agape-v18-test-"))
        (self.root / "src").mkdir()
        (self.root / "src" / "api.py").write_text("def add(a,b):\n    return a+b\n", encoding="utf-8")
        (self.root / "SELFTEST.py").write_text("print('ok')\n", encoding="utf-8")
        (self.root / "README.md").write_text("API project tests\n", encoding="utf-8")
        (self.root / "blob.bin").write_bytes(b"\x00\x01\x02")
        (self.root / ".git").mkdir()
        (self.root / ".git" / "secret.txt").write_text("ignore", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_31_goal_normalizer(self):
        r = goal_spec.normalize_goal("  Fix   the API and run tests  ", ["stay safe", "stay safe"])
        self.assertTrue(r["ok"])
        self.assertEqual(r["goal"], "Fix the API and run tests")
        self.assertEqual(r["constraints"], ["stay safe"])
        self.assertEqual(r["task_type"], "coding")
        with self.assertRaises(ValueError):
            goal_spec.normalize_goal("   ")

    def test_32_workspace_snapshot(self):
        r = workspace_snapshot.create_snapshot(str(self.root), 100)
        paths = {x["path"] for x in r["files"]}
        self.assertTrue(r["ok"])
        self.assertIn("src/api.py", paths)
        self.assertIn("SELFTEST.py", paths)
        self.assertNotIn("blob.bin", paths)
        self.assertFalse(any(x.startswith(".git/") for x in paths))
        self.assertEqual(len(r["snapshot_sha256"]), 64)

    def test_33_context_pack(self):
        s = workspace_snapshot.create_snapshot(str(self.root), 100)
        r = context_pack.build_context_pack(str(self.root), "fix api", s, 4, 3000)
        self.assertTrue(r["ok"])
        self.assertGreaterEqual(r["file_count"], 1)
        self.assertIn("src/api.py", [x["path"] for x in r["files"]])

    def test_34_work_breakdown(self):
        g = goal_spec.normalize_goal("fix api and test")
        r = work_breakdown.build_work_plan(g, {"files": [{"path": "src/api.py"}]}, 6)
        self.assertTrue(r["ok"])
        self.assertEqual(r["task_count"], 6)
        self.assertEqual(r["tasks"][0]["depends_on"], [])
        self.assertEqual(r["tasks"][1]["depends_on"], [1])

    def test_35_patch_validation(self):
        target = self.root / "src" / "api.py"
        before = workspace_snapshot.create_snapshot(str(self.root), 100)
        old_hash = next(x["sha256"] for x in before["files"] if x["path"] == "src/api.py")
        r = patch_plan.validate_patch_plan(
            str(self.root),
            [{"path": "src/api.py", "content": "def add(a,b):\n    return a+b+0\n", "expected_sha256": old_hash}],
            ["security.py"],
        )
        self.assertTrue(r["safe"])
        self.assertEqual(r["change_count"], 1)
        with self.assertRaises(ValueError):
            patch_plan.validate_patch_plan(str(self.root), [{"path": "../escape.py", "content": "x"}], [])
        with self.assertRaises(ValueError):
            patch_plan.validate_patch_plan(str(self.root), [{"path": "security.py", "content": "x"}], ["security.py"])
        target.write_text("changed", encoding="utf-8")
        with self.assertRaises(ValueError):
            patch_plan.validate_patch_plan(str(self.root), [{"path": "src/api.py", "content": "x", "expected_sha256": old_hash}], [])

    def test_36_transactional_patch(self):
        target = self.root / "src" / "api.py"
        plan = patch_plan.validate_patch_plan(str(self.root), [{"path": "src/api.py", "content": "VALUE=2\n"}], [])
        dry = patch_transaction.apply_transaction(str(self.root), plan, True)
        self.assertTrue(dry["ok"])
        self.assertFalse(dry["applied"])
        self.assertNotIn("VALUE=2", target.read_text(encoding="utf-8"))
        real = patch_transaction.apply_transaction(str(self.root), plan, False)
        self.assertTrue(real["applied"])
        self.assertEqual(target.read_text(encoding="utf-8"), "VALUE=2\n")
        self.assertTrue(Path(real["backup_root"]).is_dir())
        shutil.rmtree(real["backup_root"], ignore_errors=True)

    def test_37_test_matrix(self):
        r = test_matrix.build_test_matrix({"ok": True, "command": "python SELFTEST.py"}, ["test_one.py"])
        self.assertTrue(r["ok"])
        self.assertEqual([x["name"] for x in r["phases"]], ["targeted", "project"])
        self.assertTrue(r["stop_on_failure"])
        self.assertFalse(test_matrix.build_test_matrix({}, [])["ok"])

    def test_38_repair_cycle(self):
        self.assertEqual(repair_cycle.decide_repair(True, 1)["action"], "checkpoint")
        self.assertEqual(repair_cycle.decide_repair(False, 1, 3, ["x"], True)["action"], "repair")
        self.assertEqual(repair_cycle.decide_repair(False, 2, 3, ["x", "y"], True)["action"], "escalate")
        self.assertEqual(repair_cycle.decide_repair(False, 3, 3, ["x"], True)["action"], "rollback")
        self.assertEqual(repair_cycle.decide_repair(False, 1, 3, ["x"], False)["action"], "stop_no_progress")

    def test_39_evidence_bundle(self):
        out = self.root / "evidence"
        r = evidence_bundle.build_evidence_bundle(str(out), "unit proof", {"passed": 3})
        self.assertTrue(r["ok"])
        p = Path(r["path"])
        self.assertTrue(p.is_file())
        self.assertEqual(len(r["sha256"]), 64)
        loaded = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(loaded["evidence"]["passed"], 3)

    def test_40_pipeline_plan(self):
        r = autodev_pipeline.prepare_pipeline(str(self.root), "fix api and run tests", ["stay inside workspace"], 4)
        self.assertTrue(r["ok"])
        self.assertTrue(r["ready"])
        self.assertEqual(r["tests"]["command"], "python SELFTEST.py")
        self.assertEqual(r["execution_engine"], "project_loop")
        self.assertEqual(r["max_steps"], 4)
        self.assertTrue(r["context"]["paths"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
