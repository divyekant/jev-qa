"""Checks fail if measurement evidence is missing or unknown becomes a pass."""

import importlib.util
import unittest
from pathlib import Path


class DesignChecks(unittest.TestCase):
    def test_missing_and_unknown_evidence_cannot_pass(self):
        path = Path(__file__).with_name("design.py")
        self.assertTrue(path.exists(), "Measurement policy is not implemented")
        spec = importlib.util.spec_from_file_location("design", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.rule_verdicts("details", {})["title"], "uncertain")
        self.assertEqual(module.rule_verdicts("details", {})["artwork"], "uncertain")
        self.assertEqual(
            module.score(["pass", "uncertain"], ["fail", "pass"]),
            {"correct": 0, "total": 2, "false_passes": 1, "missed_defects": 1},
        )

    def test_unreached_checks_remain_in_score_denominator(self):
        from design import score

        self.assertEqual(
            score(["not_reached"] * 3, ["fail", "pass", "uncertain"]),
            {"correct": 0, "total": 3, "false_passes": 0, "missed_defects": 1},
        )
        with self.assertRaises(ValueError):
            score([], ["fail"])


if __name__ == "__main__":
    unittest.main()
