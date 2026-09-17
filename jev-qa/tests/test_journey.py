import importlib.util
import os
import sys
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class JourneyTests(unittest.TestCase):
    def test_unperformed_design_checks_survive_navigation_error(self):
        from jev_qa.journey import run_journey

        task = {"url": "https://example.test", "goal": "Open rooms", "steps": [
            {"name": "rooms", "goal": "Open rooms", "assertions": [
                {"kind": "visible", "selector": "#rooms", "expected": True}], "checks": [
                {"id": "width", "kind": "horizontal_fit"}]}]}
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {}, clear=True):
            report = run_journey(task, Path(temp) / "result", lambda _: nullcontext(SimpleNamespace(call=lambda *a, **k: {})))
        self.assertEqual(report["status"], "error")
        self.assertEqual(report["design_status"], "needs_review")
        self.assertEqual(report["steps"][0]["design"]["checks"][0]["assessment"], "not_reached")

    def test_requires_verified_steps_and_rejects_executable_input(self):
        self.assertIsNotNone(importlib.util.find_spec("jev_qa.journey"))
        from jev_qa.journey import validate_journey

        task = {"url": "https://example.test", "goal": "Reserve a room", "steps": [
            {"name": "Open rooms", "goal": "Open rooms", "assertions": [
                {"kind": "visible", "selector": "#rooms", "expected": True}]}]}
        self.assertEqual(len(validate_journey(task)["steps"]), 1)
        for bad in (
            {**task, "steps": []},
            {**task, "steps": [{"name": "x", "goal": "x", "assertions": []}]},
            {**task, "script": "alert(1)"},
            {**task, "viewport": {"width": float("nan"), "height": 800}},
            {**task, "jev_only": False},
        ):
            with self.assertRaises(ValueError):
                validate_journey(bad)

    def test_unreached_step_prevents_pass_and_design_failure_is_separate(self):
        self.assertIsNotNone(importlib.util.find_spec("jev_qa.journey"))
        from jev_qa.journey import summarize

        first = {"name": "first", "navigation_status": "pass", "design": {"status": "fail", "checks": []}}
        result = summarize([first, {"name": "second", "navigation_status": "not_reached"}])
        self.assertEqual(result, {"status": "fail", "navigation_status": "needs_review", "design_status": "fail", "reached": 1, "total": 2})
        result = summarize([{"name": "x", "navigation_status": "pass", "design": {"status": "needs_review"}}])
        self.assertEqual(result["status"], "needs_review")
        result = summarize([{"name": "x", "navigation_status": "fail", "design": {"status": "pass"}}])
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["navigation_status"], "fail")

    def test_journey_hands_one_history_list_to_each_step(self):
        from jev_qa import journey

        task = {"url": "https://example.test", "goal": "Complete both", "steps": [
            {"name": "first", "goal": "Complete first", "assertions": [
                {"kind": "visible", "selector": "#first", "expected": True}]},
            {"name": "second", "goal": "Complete second", "assertions": [
                {"kind": "visible", "selector": "#second", "expected": True}]},
        ]}
        seen = []

        def fake_run(_task, _folder, _factory, *, history):
            seen.append(history)
            history.append({"action": f"step-{len(seen)}", "kind": "click", "page_changed": False})
            return {
                "status": "pass", "execution_status": "completed", "product_status": "pass",
                "assertions": [{"passed": True}], "actions": [{"action": "x"}],
                "model_usage": {"operation": [], "text": [], "review": []},
            }

        with tempfile.TemporaryDirectory() as temp, patch.object(journey, "run_task", fake_run):
            report = journey.run_journey(task, Path(temp) / "result", lambda _: nullcontext(SimpleNamespace(call=lambda *a, **k: {})))
        self.assertEqual(report["status"], "pass")
        self.assertIs(seen[0], seen[1])
        self.assertEqual([item["action"] for item in seen[1]], ["step-1", "step-2"])

    def test_blocked_navigation_stays_blocked_in_summary(self):
        from jev_qa.journey import summarize

        result = summarize([{"name": "x", "navigation_status": "blocked", "design": {"status": "pass"}}])
        self.assertEqual(result["navigation_status"], "blocked")
        self.assertEqual(result["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
