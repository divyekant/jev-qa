import base64
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jev_qa import runner  # noqa: E402


def decision(action="click-1", confidence=1.0, target_confidence=1.0, model="jev-latest"):
    return {
        "choice": action,
        "operation": "CLICK",
        "target": "1",
        "confidence": confidence,
        "target_confidence": target_confidence,
        "probabilities": {action: 1.0},
        "operation_probabilities": {"CLICK": 1.0, "DONE": 0.0, "BLOCKED": 0.0},
        "target_probabilities": {"1": 1.0},
        "model": model,
        "usage": {"input_tokens": 1},
        "latency_ms": 1,
    }


def page(url="https://example.test/start"):
    return {
        "url": url,
        "title": "Fixture",
        "text": "Ready",
        "actions": [{"id": "click-1", "kind": "click", "label": "Continue", "role": "button", "node": 1}],
        "fingerprint": "page-1",
        "screenshot": base64.b64encode(b"jpeg").decode(),
    }


class FakeBrowser:
    def __init__(self, pages=None, evaluate_values=None):
        self.pages = list(pages or [page()])
        self.current = self.pages[0]
        self.evaluate_values = list(evaluate_values or [{"ok": True}])
        self.acts = []
        self.observes = 0
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.closed = True

    def observe(self, screenshot=True):
        self.observes += 1
        if self.pages:
            self.current = self.pages.pop(0)
        return self.current

    def fresh(self, _page, _action=None):
        return True

    def act(self, action, _page, text=None):
        self.acts.append((action, text))
        return {"executed": action["id"]}

    def evaluate(self, _expression):
        return self.evaluate_values.pop(0) if self.evaluate_values else {"ok": True}

    def call(self, *_args, **_kwargs):
        return {}


class RunnerTests(unittest.TestCase):
    def test_expired_time_budget_cannot_early_pass(self):
        class SlowBrowser(FakeBrowser):
            def observe(self, screenshot=True):
                time.sleep(0.02)
                return super().observe(screenshot)

        result, _ = self.run_with(SlowBrowser(), self.task(stop_when_assertions_pass=True, max_seconds=0.001))
        self.assertEqual(result["terminal_status"], "blocked")
        self.assertNotEqual(result["status"], "pass")

    def task(self, **overrides):
        task = {
            "url": "https://example.test/start",
            "goal": "Continue",
            "assertions": [{"kind": "text_equals", "selector": "main", "expected": "Ready"}],
            "max_steps": 2,
        }
        task.update(overrides)
        return task

    def run_with(self, browser, task=None, chooser=None):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "evidence"
            with (
                patch.object(
                    runner,
                    "_jev_choose",
                    chooser
                    or (
                        lambda *_args: {
                            **decision("DONE"),
                            "operation": "DONE",
                            "target": None,
                            "choice": "DONE",
                            "operation_probabilities": {"CLICK": 0.0, "DONE": 1.0, "BLOCKED": 0.0},
                        }
                    ),
                ),
                patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}, clear=False),
            ):
                return runner.run_task(task or self.task(), out, lambda _url: browser), out

    def test_validation_rejects_unknown_fields_and_missing_expected(self):
        with self.assertRaises(ValueError):
            runner.validate_task({"url": "https://example.test", "goal": "x", "criteria": ["x"], "extra": 1})
        with self.assertRaises(ValueError):
            runner.validate_task(
                {"url": "https://example.test", "goal": "x", "assertions": [{"kind": "visible", "selector": "#x"}]}
            )

    def test_run_options_default_and_validate_bounds(self):
        normalized = runner.validate_task(self.task())
        self.assertFalse(normalized["stop_when_assertions_pass"])
        self.assertEqual(normalized["recovery_attempts"], 0)
        self.assertTrue(normalized["jev_only"])
        with self.assertRaises(ValueError):
            runner.validate_task(self.task(stop_when_assertions_pass=True, assertions=[]))
        with self.assertRaises(ValueError):
            runner.validate_task(self.task(stop_when_assertions_pass=True, mode="check", goal=""))
        with self.assertRaises(ValueError):
            runner.validate_task(self.task(recovery_attempts=2))

    def test_verified_initial_assertions_skip_done_model_call(self):
        browser = FakeBrowser(evaluate_values=[{"ok": True}])
        chooser_calls = []

        def chooser(*_args):
            chooser_calls.append(True)
            raise AssertionError("DONE model call was not skipped")

        result, _ = self.run_with(
            browser,
            self.task(stop_when_assertions_pass=True, jev_only=True),
            chooser=chooser,
        )
        self.assertEqual(result["terminal_status"], "done")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(chooser_calls, [])
        self.assertEqual(result["model_usage"]["operation"], [])

    def test_verified_last_action_wins_before_step_budget_cutoff(self):
        browser = FakeBrowser(evaluate_values=[{"ok": False}, {"ok": True}])
        chooser_calls = []

        def chooser(*_args):
            chooser_calls.append(True)
            return decision()

        result, _ = self.run_with(
            browser,
            self.task(stop_when_assertions_pass=True, max_steps=1, jev_only=True),
            chooser=chooser,
        )
        self.assertEqual(result["terminal_status"], "done")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(len(chooser_calls), 1)
        self.assertEqual(len(browser.acts), 1)

    def test_offscreen_control_is_context_only_until_scroll(self):
        class OffscreenBrowser(FakeBrowser):
            def __init__(self):
                initial = page()
                initial["actions"] = [{"id": "scroll_down", "kind": "scroll", "label": "Scroll down", "delta": 560}]
                scrolled = page()
                scrolled["actions"] = [
                    {"id": "click-1", "kind": "click", "label": "Inspect session", "role": "button", "node": 1}
                ]
                clicked = page()
                clicked["actions"] = scrolled["actions"]
                super().__init__(pages=[initial, scrolled, clicked])
                self.scrolled = False
                self.clicked = False

            def evaluate(self, expression):
                if "__jevFast" in expression:
                    return [] if self.scrolled else [{"direction": "below", "role": "button", "label": "Inspect session"}]
                return {"ok": self.clicked}

            def act(self, action, _page, text=None):
                result = super().act(action, _page, text)
                self.scrolled |= action["id"] == "scroll_down"
                self.clicked |= action["id"] == "click-1"
                return result

        browser = OffscreenBrowser()
        seen = []

        def chooser(state, *_args):
            seen.append((state["text"], [action["id"] for action in state["actions"]]))
            if not browser.scrolled:
                self.assertIn("Offscreen controls below: button Inspect session", state["text"])
                self.assertNotIn("click-1", seen[-1][1])
                return {
                    **decision("scroll_down"),
                    "operation": "SCROLL_DOWN",
                    "target": None,
                    "choice": "scroll_down",
                    "operation_probabilities": {
                        "SCROLL_DOWN": 1.0, "REVEAL_R1": 0.0, "DONE": 0.0, "BLOCKED": 0.0
                    },
                }
            self.assertNotIn("Offscreen controls", state["text"])
            self.assertIn("click-1", seen[-1][1])
            return decision("click-1")

        result, _ = self.run_with(
            browser,
            self.task(stop_when_assertions_pass=True, max_steps=2, jev_only=True),
            chooser=chooser,
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual([item["action"] for item in result["actions"]], ["scroll_down", "click-1"])

    def test_origin_mismatch_cannot_early_pass(self):
        browser = FakeBrowser(pages=[page("https://evil.test/start")], evaluate_values=[{"ok": True}])
        result, _ = self.run_with(
            browser,
            self.task(stop_when_assertions_pass=True, jev_only=True),
        )
        self.assertNotEqual(result["status"], "pass")
        self.assertTrue(any(item["code"] == "origin_mismatch" for item in result["errors"]))

    def test_stale_observation_cannot_early_pass(self):
        class StaleBrowser(FakeBrowser):
            def fresh(self, _page, _action=None):
                return False

        browser = StaleBrowser(pages=[page(), page(), page(), page(), page(), page()])
        result, _ = self.run_with(
            browser,
            self.task(stop_when_assertions_pass=True, jev_only=True),
        )
        self.assertNotEqual(result["status"], "pass")
        self.assertEqual(browser.acts, [])

    def test_low_confidence_recovery_is_bounded_and_does_not_mutate(self):
        browser = FakeBrowser(pages=[page(), page(), page()])
        low = decision(confidence=0.5, target_confidence=1.0)
        calls = []

        def chooser(*_args):
            calls.append(True)
            return low

        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}, clear=False):
            out = Path(temp) / "evidence"
            with patch.object(runner, "_jev_choose", chooser):
                result = runner.run_task(self.task(recovery_attempts=1, jev_only=True), out, lambda _url: browser)
            trace = (out / "trace.jsonl").read_text()
        self.assertEqual(result["terminal_status"], "low_confidence")
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(result["model_usage"]["operation"]), 2)
        self.assertEqual(browser.acts, [])
        self.assertEqual(trace.count('"event":"recovery"'), 1)

    def test_jev_only_disables_text_helper_even_when_key_is_present(self):
        browser = FakeBrowser()
        browser.current["actions"] = [
            {"id": "fill-1", "kind": "fill", "label": "Email", "role": "textbox", "node": 1}
        ]
        choice = {
            **decision("fill-1"),
            "operation": "TYPE_TEXT",
            "target": "1",
            "operation_probabilities": {"TYPE_TEXT": 1.0, "DONE": 0.0, "BLOCKED": 0.0},
            "target_probabilities": {"1": 1.0},
        }
        with patch.object(runner, "field_text", return_value=("generated", {"model": "helper"})) as helper:
            result, _ = self.run_with(
                browser,
                self.task(values={}, jev_only=True),
                chooser=lambda *_args: choice,
            )
        self.assertEqual(result["terminal_status"], "needs_review")
        self.assertFalse(helper.called)
        self.assertEqual(browser.acts, [])

    def test_explicit_legacy_mode_can_use_text_helper(self):
        browser = FakeBrowser()
        browser.current["actions"] = [
            {"id": "fill-1", "kind": "fill", "label": "Email", "role": "textbox", "node": 1}
        ]
        choice = {
            **decision("fill-1"),
            "operation": "TYPE_TEXT",
            "target": "1",
            "operation_probabilities": {"TYPE_TEXT": 1.0, "DONE": 0.0, "BLOCKED": 0.0},
            "target_probabilities": {"1": 1.0},
        }
        with (
            patch.object(runner, "field_text", return_value=("generated", {"model": "helper"})) as helper,
            patch.dict(
                os.environ,
                {"TYPESAFE_API_KEY": "test", "TEXT_MODEL_API_KEY": "test-helper"},
                clear=False,
            ),
            tempfile.TemporaryDirectory() as temp,
        ):
            out = Path(temp) / "evidence"
            with patch.object(runner, "choose", lambda *_args: choice):
                runner.run_task(self.task(values={}, jev_only=False, max_steps=1), out, lambda _url: browser)
        helper.assert_called_once()
        self.assertEqual(browser.acts[0][1], "generated")

    def test_non_jev_operation_model_is_rejected_before_mutation(self):
        browser = FakeBrowser()
        result, _ = self.run_with(
            browser,
            self.task(jev_only=True),
            chooser=lambda *_args: decision(model="other-model"),
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(browser.acts, [])
        self.assertTrue(any(item["code"] == "non_jev_model" for item in result["errors"]))

    def test_jev_versioned_operation_model_is_accepted(self):
        browser = FakeBrowser()
        done = {
            **decision("DONE", model="jev-1.13.0"),
            "operation": "DONE",
            "target": None,
            "choice": "DONE",
            "operation_probabilities": {"CLICK": 0.0, "DONE": 1.0, "BLOCKED": 0.0},
        }
        result, _ = self.run_with(browser, self.task(jev_only=True), chooser=lambda *_args: done)
        self.assertEqual(result["status"], "pass")

    def test_jev_only_review_rejects_non_jev_result(self):
        answer = {"choice": "pass", "confidence": 1.0, "probabilities": {"pass": 1.0, "fail": 0.0, "uncertain": 0.0}}
        with (
            patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}, clear=False),
            patch.object(
                runner, "post_json", return_value={"model": "other-model", "answers": {"criterion_0": answer}}
            ),
        ):
            result = runner.review_evidence({"url": "https://example.test", "text": "Ready"}, ["Ready"], jev_only=True)
        self.assertFalse(result["all_pass"])
        self.assertEqual(result["judgments"][0]["assessment"], "uncertain")

    def test_jev_only_forces_model_alias_and_restores_environment(self):
        browser = FakeBrowser()
        observed_models = []
        with patch.dict(os.environ, {"TYPESAFE_MODEL": "legacy-model"}, clear=False):
            result, _ = self.run_with(
                browser,
                self.task(jev_only=True),
                chooser=lambda *_args: (
                    observed_models.append(os.environ.get("TYPESAFE_MODEL"))
                    or {
                        **decision("DONE"),
                        "operation": "DONE",
                        "target": None,
                        "choice": "DONE",
                        "operation_probabilities": {"CLICK": 0.0, "DONE": 1.0, "BLOCKED": 0.0},
                    }
                ),
            )
            self.assertEqual(os.environ.get("TYPESAFE_MODEL"), "legacy-model")
        self.assertEqual(observed_models, ["jev-latest"])
        self.assertEqual(result["status"], "pass")

    def test_false_done_cannot_pass_without_deterministic_assertion(self):
        browser = FakeBrowser(evaluate_values=[{"ok": True}])
        with patch.object(
            runner,
            "review_evidence",
            return_value={"status": "needs_review", "all_pass": True, "judgments": [], "model_usage": []},
        ):
            result, _ = self.run_with(browser, self.task(assertions=[], criteria=["The result is complete"]))
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(browser.acts, [])

    def test_low_confidence_prevents_action(self):
        browser = FakeBrowser()
        low = decision(confidence=0.79, target_confidence=0.99)
        result, _ = self.run_with(browser, chooser=lambda *_args: low)
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(browser.acts, [])

    def test_mutation_failure_is_not_retried(self):
        browser = FakeBrowser()

        def fail(*_args, **_kwargs):
            browser.acts.append(("attempt", None))
            raise RuntimeError("ambiguous browser result")

        browser.act = fail
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(runner, "_jev_choose", lambda *_args: decision()),
            patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}, clear=False),
        ):
            out = Path(temp) / "evidence"
            result = runner.run_task(self.task(assertions=[], criteria=["done"]), out, lambda _url: browser)
            self.assertEqual(result["status"], "error")
            self.assertEqual(browser.acts, [("attempt", None)])
            trace = (out / "trace.jsonl").read_text()
            self.assertEqual(trace.count('"event":"action_intent"'), 1)

    def test_missing_model_key_fails_before_browser(self):
        browser = FakeBrowser()
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {}, clear=True):
            result = runner.run_task(self.task(), Path(temp) / "evidence", lambda _url: browser)
        self.assertEqual(result["status"], "error")
        self.assertEqual(browser.observes, 0)

    def test_malformed_model_judgment_is_uncertain(self):
        with (
            patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}, clear=False),
            patch.object(
                runner,
                "post_json",
                return_value={"model": "reviewer", "answers": {"criterion_0": {"choice": "pass"}}},
            ),
        ):
            result = runner.review_evidence({"url": "https://example.test", "text": "Ready"}, ["Ready"], 0.8)
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["judgments"][0]["assessment"], "uncertain")

    def test_review_preserves_arbitrary_evidence_fields_in_one_request(self):
        answer = {"choice": "pass", "confidence": 1.0, "probabilities": {"pass": 1.0, "fail": 0.0, "uncertain": 0.0}}
        with (
            patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}, clear=False),
            patch.object(
                runner, "post_json", return_value={"model": "reviewer", "answers": {"criterion_0": answer}}
            ) as post,
        ):
            result = runner.review_evidence(
                {"requirement": "Reject empty email", "input": {"email": ""}, "observed_response": "Rejected"},
                ["The empty value is rejected"],
            )
        self.assertTrue(result["all_pass"])
        body = post.call_args.args[2]
        self.assertEqual(body["state"]["evidence"]["requirement"], "Reject empty email")
        self.assertEqual(set(body["questions"]), {"criterion_0"})

    def test_trace_and_report_are_private_and_output_is_not_overwritten(self):
        browser = FakeBrowser()
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "evidence"
            result = runner.run_task(self.task(mode="check", goal=""), out, lambda _url: browser)
            self.assertIn(result["status"], {"pass", "error", "fail", "needs_review"})
            self.assertTrue((out / "report.json").exists())
            self.assertTrue((out / "trace.jsonl").exists())
            self.assertEqual((out / "report.json").stat().st_mode & 0o777, 0o600)
            self.assertEqual((out / "trace.jsonl").stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                runner.run_task(self.task(mode="check", goal=""), out, lambda _url: browser)

    def test_report_roundtrip_preserves_nested_model_usage(self):
        browser = FakeBrowser()
        done = {
            **decision("DONE"),
            "operation": "DONE",
            "target": None,
            "choice": "DONE",
            "operation_probabilities": {"CLICK": 0.0, "DONE": 1.0, "BLOCKED": 0.0},
        }
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(runner, "_jev_choose", lambda *_args: done),
            patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}, clear=False),
        ):
            out = Path(temp) / "evidence"
            runner.run_task(self.task(), out, lambda _url: browser)
            report = json.loads((out / "report.json").read_text())
        self.assertEqual(report["model_usage"]["operation"][0]["usage"]["input_tokens"], 1)

    def test_missing_field_value_is_review_required_before_typing(self):
        browser = FakeBrowser()
        browser.current["actions"] = [{"id": "fill-1", "kind": "fill", "label": "Email", "role": "textbox", "node": 1}]
        choice = {
            **decision("fill-1"),
            "operation": "TYPE_TEXT",
            "target": "1",
            "operation_probabilities": {"TYPE_TEXT": 1.0, "DONE": 0.0, "BLOCKED": 0.0},
            "target_probabilities": {"1": 1.0},
        }
        with (
            tempfile.TemporaryDirectory() as temp,
            patch.object(runner, "_jev_choose", lambda *_args: choice),
            patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}, clear=False),
        ):
            result = runner.run_task(self.task(), Path(temp) / "evidence", lambda _url: browser)
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(browser.acts, [])

    def test_shared_history_receives_only_confirmed_actions(self):
        browser = FakeBrowser(pages=[page(), page()])
        shared = []
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}, clear=False):
            out = Path(temp) / "evidence"
            with patch.object(runner, "_jev_choose", lambda *_args: decision()):
                result = runner.run_task(
                    self.task(max_steps=1, stop_when_assertions_pass=False), out, lambda _url: browser, history=shared
                )
        self.assertEqual(result["terminal_status"], "blocked")
        self.assertEqual(len(shared), 1)
        self.assertEqual(shared[0]["action"], "Continue")
        self.assertIs(shared[0].get("page_changed"), False)

    def test_blocked_before_completion_does_not_report_product_failure(self):
        browser = FakeBrowser(evaluate_values=[{"ok": False}, {"ok": True}, {"ok": False}])
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}, clear=False):
            with patch.object(runner, "_jev_choose", lambda *_args: decision(confidence=0.5)):
                result = runner.run_task(
                    self.task(stop_when_assertions_pass=True), Path(temp) / "evidence", lambda _url: browser,
                    history=[],
                )
        self.assertEqual(result["terminal_status"], "low_confidence")
        self.assertEqual(result["execution_status"], "blocked")
        self.assertEqual(result["product_status"], "not_tested")
        self.assertEqual(result["status"], "needs_review")
        self.assertFalse(result["assertions"][0]["passed"])

    def test_completed_assertion_failure_is_a_product_failure(self):
        browser = FakeBrowser(evaluate_values=[{"ok": True}, {"ok": False}])
        done = {
            **decision("DONE"),
            "operation": "DONE",
            "target": None,
            "choice": "DONE",
            "operation_probabilities": {"CLICK": 0.0, "DONE": 1.0, "BLOCKED": 0.0},
        }
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"TYPESAFE_API_KEY": "test"}, clear=False):
            with patch.object(runner, "_jev_choose", lambda *_args: done):
                result = runner.run_task(
                    self.task(stop_when_assertions_pass=False), Path(temp) / "evidence", lambda _url: browser,
                    history=[],
                )
        self.assertEqual(result["terminal_status"], "done")
        self.assertEqual(result["execution_status"], "completed")
        self.assertEqual(result["product_status"], "fail")
        self.assertEqual(result["status"], "fail")

    def test_check_mode_deterministic_failure_remains_failure(self):
        browser = FakeBrowser(evaluate_values=[{"ok": False}, {"ok": False}])
        with tempfile.TemporaryDirectory() as temp:
            result = runner.run_task(
                self.task(mode="check", goal=""), Path(temp) / "evidence", lambda _url: browser, history=[]
            )
        self.assertEqual(result["execution_status"], "completed")
        self.assertEqual(result["product_status"], "fail")
        self.assertEqual(result["status"], "fail")

    def test_reveal_action_is_finite_and_does_not_mutate_observed_actions(self):
        original = page()
        original_actions = list(original["actions"])

        class RevealDiscoveryBrowser(FakeBrowser):
            def evaluate(self, expression):
                if "__jevFast" in expression:
                    return {
                        "token": "page-token",
                        "controls": [{"ref": "R1", "direction": "below", "role": "button", "label": "Inspect session"}],
                    }
                return {"ok": True}

        model_page = runner._offscreen_page(RevealDiscoveryBrowser(), original)
        self.assertEqual([action["id"] for action in original["actions"]], [action["id"] for action in original_actions])
        reveals = [action for action in model_page["actions"] if action["kind"] == "reveal"]
        self.assertEqual(len(reveals), 1)
        self.assertEqual(reveals[0]["id"], "REVEAL_R1")
        self.assertIn("Inspect session", reveals[0]["label"])

    def test_reveal_scrolls_with_one_native_wheel_then_requires_new_observation(self):
        browser = FakeBrowser()
        calls = []
        browser.current.update({"w": 390, "h": 844})
        browser.fresh = lambda *_args: True
        browser.evaluate = lambda expression: calls.append(("evaluate", expression)) or {"ok": True}
        browser.call = lambda *args, **kwargs: calls.append((args, kwargs)) or {}
        action = {
            "id": "REVEAL_R1", "kind": "reveal", "direction": "below", "_reveal_ref": "R1",
            "_reveal_token": "page-token", "_reveal_guard": [1, "button", "Inspect session"],
        }
        result = runner._execute_reveal(browser, browser.current, action)
        self.assertEqual(result["executed"], "REVEAL_R1")
        wheel = [item for item in calls if isinstance(item, tuple) and item[0][0] == "Input.dispatchMouseEvent"]
        self.assertEqual(len(wheel), 1)
        self.assertEqual(wheel[0][1]["type"], "mouseWheel")
        self.assertLessEqual(abs(wheel[0][1]["deltaY"]), 844)

    def test_reveal_rejects_stale_or_forged_target_before_wheel(self):
        browser = FakeBrowser()
        calls = []
        browser.call = lambda *args, **kwargs: calls.append((args, kwargs)) or {}
        browser.evaluate = lambda _expression: {"ok": False, "reason": "stale_reveal"}
        action = {
            "id": "REVEAL_R1", "kind": "reveal", "direction": "below", "_reveal_ref": "forged",
            "_reveal_token": "page-token", "_reveal_guard": [1, "button", "Inspect session"],
        }
        with self.assertRaises(runner.RevealError):
            runner._execute_reveal(browser, browser.current, action)
        self.assertEqual(calls, [])

    def test_decision_evidence_preserves_request_answers_and_distributions_without_key(self):
        browser = FakeBrowser()
        raw_request = {
            "model": "jev-latest",
            "state": {"page": {"text": "all of it"}, "elements": [{"index": "1"}]},
            "questions": {"operation": {"criteria": {"DONE": "finish"}}},
        }
        chosen = {
            **decision("DONE"),
            "operation": "DONE",
            "target": None,
            "choice": "DONE",
            "operation_probabilities": {"CLICK": 0.0, "DONE": 1.0, "BLOCKED": 0.0},
            "request": raw_request,
            "raw_answers": {"operation": {"choice": "DONE", "probabilities": {"DONE": 1.0}}},
        }
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"TYPESAFE_API_KEY": "configured-secret"}, clear=False
        ):
            out = Path(temp) / "evidence"
            with patch.object(runner, "_jev_choose", lambda *_args: chosen):
                runner.run_task(self.task(), out, lambda _url: browser, history=[])
            files = sorted(out.glob("decision-*.json"))
            self.assertEqual(len(files), 1)
            evidence = json.loads(files[0].read_text())
            mode = (out / files[0].name).stat().st_mode & 0o777
        self.assertEqual(evidence["request"], raw_request)
        self.assertEqual(evidence["raw_answers"], chosen["raw_answers"])
        self.assertEqual(evidence["probabilities"]["operation"], chosen["operation_probabilities"])
        self.assertNotIn("TYPESAFE_API_KEY", json.dumps(evidence))
        self.assertEqual(mode, 0o600)

    def test_cleanup_failure_flag_survives_safe_exception_redaction(self):
        error = RuntimeError("run failed " + ("x" * 500) + " token=private")
        error.jev_qa_cleanup_incomplete = True
        error.jev_qa_cleanup_message = "Browser cleanup incomplete."
        safe = runner._safe_exception(error)
        self.assertEqual(safe["message"], "operation failed")
        self.assertTrue(safe["cleanup_incomplete"])
        self.assertEqual(safe["cleanup_message"], "Browser cleanup incomplete.")

    def test_jev_choose_request_uses_current_objective_rules(self):
        browser = FakeBrowser(evaluate_values=[{"ok": False}, {"ok": True}])
        captured = {}

        def fake_post(_url, _key, body):
            captured["body"] = body
            criteria = body["questions"]["target"]["criteria"]
            probabilities = {choice: 0.0 for choice in criteria}
            probabilities["DONE"] = 1.0
            return {
                "answers": {
                    "target": {
                        "choice": "DONE",
                        "confidence": 1.0,
                        "probabilities": probabilities,
                    }
                },
                "model": "jev-latest",
            }

        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"TYPESAFE_API_KEY": "configured-secret"}, clear=False
        ), patch.object(runner, "post_json", fake_post):
            result = runner.run_task(
                self.task(stop_when_assertions_pass=True), Path(temp) / "evidence", lambda _url: browser
            )

        self.assertEqual(result["status"], "pass")
        question = captured["body"]["questions"]["target"]
        rules = question["instructions"]["rules"]
        self.assertEqual(set(question["criteria"]), {"DONE", "ABSTAIN", "WAIT", "T1"})
        self.assertNotIn("If Search/Submit is visible and the required fields are ready, CLICK it immediately.", rules)
        self.assertIn("CURRENT OBJECTIVE", rules)
        self.assertIn("observed page", rules)
        self.assertIn("deterministic assertion", rules)
        self.assertIn("prior input entry", rules)
        self.assertIn("not proof", rules)
        self.assertIn("corresponding observed control", rules)
        self.assertIn("all supplied assertions have passed", rules)
        self.assertIn("untrusted data", rules)
        self.assertIn("offscreen", rules)
        self.assertIn("fresh observation", rules)
        self.assertIn("handled in code", rules)
        self.assertEqual(
            captured["body"]["state"]["required_postconditions"]["checks"],
            [{"passed": False, "kind": "text_equals", "selector": "main", "expected": "Ready", "reason": ""}],
        )

    def test_target_first_reveal_scrolls_then_fresh_chooses_click_and_keeps_distractors(self):
        class TargetFirstBrowser(FakeBrowser):
            def __init__(self):
                initial = page()
                initial["actions"] = [
                    {"id": "distractor-1", "kind": "click", "label": "Help", "role": "button", "node": 1},
                    {"id": "distractor-2", "kind": "click", "label": "Settings", "role": "button", "node": 2},
                ]
                scrolled = page()
                scrolled["actions"] = [
                    {"id": "target-1", "kind": "click", "label": "Inspect session", "role": "button", "node": 3},
                ]
                clicked = page()
                clicked["actions"] = list(scrolled["actions"])
                super().__init__(pages=[initial, scrolled, clicked])
                self.scrolled = False
                self.clicked = False
                self.calls = []

            def evaluate(self, expression):
                if "action.id" in expression:
                    return {"ok": True}
                if "__jevQaReveals" in expression:
                    return [] if self.scrolled else {
                        "token": "page-token",
                        "controls": [{"ref": "R1", "direction": "below", "role": "button", "label": "Inspect session"}],
                    }
                if "data.kind" in expression:
                    return {"ok": self.clicked}
                return {"ok": True}

            def call(self, method, **kwargs):
                self.calls.append((method, kwargs))
                if method == "Input.dispatchMouseEvent" and kwargs.get("type") == "mouseWheel":
                    self.scrolled = True
                return {}

            def act(self, action, _page, text=None):
                result = super().act(action, _page, text)
                if action["id"] == "target-1":
                    self.clicked = True
                return result

        browser = TargetFirstBrowser()
        requests = []

        def fake_post(_url, _key, body):
            requests.append(body)
            criteria = body["questions"]["target"]["criteria"]
            if len(requests) == 1:
                visible = [item["label"] for item in criteria.values() if item.get("visibility") == "visible"]
                self.assertEqual(visible, ["Help", "Settings"])
                selected = next(key for key, item in criteria.items() if item.get("visibility") == "offscreen")
            else:
                self.assertNotIn('"visibility": "offscreen"', json.dumps(criteria))
                selected = next(key for key, item in criteria.items() if item.get("identity") == "target-1")
            probabilities = {choice: 0.0 for choice in criteria}
            probabilities[selected] = 1.0
            return {
                "answers": {"target": {"choice": selected, "confidence": 1.0, "probabilities": probabilities}},
                "model": "jev-latest",
                "usage": {"input_tokens": len(requests)},
            }

        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"TYPESAFE_API_KEY": "configured-secret"}, clear=False
        ), patch.object(runner, "post_json", fake_post):
            result = runner.run_task(
                self.task(stop_when_assertions_pass=True, max_steps=3), Path(temp) / "evidence", lambda _url: browser
            )
            evidence = sorted((Path(temp) / "evidence").glob("decision-*.json"))
            self.assertEqual(len(evidence), 2)
            self.assertEqual(json.loads(evidence[0].read_text())["request"], requests[0])

        self.assertEqual(result["status"], "pass")
        self.assertEqual([action["action"] for action in result["actions"]], ["REVEAL_R1", "target-1"])
        self.assertEqual(len([call for call in browser.calls if call[0] == "Input.dispatchMouseEvent"]), 1)
        self.assertTrue(browser.clicked)
        self.assertEqual(len(requests), 2)

    def test_target_first_low_confidence_and_forged_ref_do_not_mutate(self):
        browser = FakeBrowser(evaluate_values=[{"ok": False}, {"ok": False}])

        def low_confidence(_url, _key, body):
            criteria = body["questions"]["target"]["criteria"]
            selected = next(choice for choice in criteria if choice.startswith("T"))
            return {
                "answers": {
                    "target": {
                        "choice": selected,
                        "confidence": 0.5,
                        "probabilities": {choice: (1.0 if choice == selected else 0.0) for choice in criteria},
                    }
                },
                "model": "jev-latest",
            }

        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"TYPESAFE_API_KEY": "configured-secret"}, clear=False
        ), patch.object(runner, "post_json", low_confidence):
            result = runner.run_task(
                self.task(stop_when_assertions_pass=True), Path(temp) / "evidence", lambda _url: browser
            )
        self.assertEqual(result["execution_status"], "blocked")
        self.assertEqual(browser.acts, [])

        browser = FakeBrowser()

        def forged(_url, _key, body):
            criteria = body["questions"]["target"]["criteria"]
            probabilities = {choice: 0.0 for choice in criteria}
            return {
                "answers": {
                    "target": {"choice": "T999", "confidence": 1.0, "probabilities": probabilities}
                },
                "model": "jev-latest",
            }

        with self.assertRaises(ValueError):
            with patch.dict(os.environ, {"TYPESAFE_API_KEY": "configured-secret"}, clear=False), patch.object(
                runner, "post_json", forged
            ):
                runner._target_first_choose(runner._offscreen_page(browser, browser.current), "Current objective", [])
        self.assertEqual(browser.acts, [])


if __name__ == "__main__":
    unittest.main()
