import json
import sys
import unittest
from contextlib import nullcontext
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class CliBrowserModeTests(unittest.TestCase):
    def test_cleanup_failure_survives_original_error_redaction(self):
        from jev_qa.__main__ import main
        from jev_qa.browser import _surface_cleanup_error

        original = RuntimeError("authorization " + "x" * 400)
        _surface_cleanup_error(original, RuntimeError("private cleanup detail"))
        with patch.object(sys, "argv", ["jev-qa", "run", "task.json"]), \
             patch("jev_qa.__main__.load_env"), \
             patch("jev_qa.__main__.read_json", side_effect=original), \
             patch("sys.stderr", new_callable=StringIO) as stderr:
            self.assertEqual(main(), 2)
        result = json.loads(stderr.getvalue())
        self.assertEqual(result["reason"], "RuntimeError")
        self.assertIs(result["cleanup_incomplete"], True)
        self.assertEqual(result["cleanup_message"], "Browser cleanup incomplete.")
        self.assertNotIn("private", stderr.getvalue())

    def test_run_defaults_to_isolated_and_accepts_existing_chrome(self):
        from jev_qa.__main__ import build_parser

        parser = build_parser()
        self.assertEqual(parser.parse_args(["run", "task.json"]).browser, "isolated")
        self.assertEqual(
            parser.parse_args(["journey", "task.json", "--browser", "existing-chrome"]).browser,
            "existing-chrome",
        )

    def test_review_rejects_browser_mode(self):
        from jev_qa.__main__ import build_parser

        with self.assertRaises(SystemExit):
            build_parser().parse_args(["review", "evidence.json", "--browser", "existing-chrome"])

    def test_existing_browser_setup_error_keeps_actionable_reason(self):
        from jev_qa import runner
        from jev_qa.__main__ import BrowserSetupError, main

        task = {
            "url": "http://127.0.0.1:8769/fixture",
            "goal": "Inspect the fixture.",
            "assertions": [{"kind": "visible", "selector": "#fixture", "expected": True}],
        }

        def fail_factory(_url, *, existing=False):
            raise BrowserSetupError("Existing Chrome remote debugging is unreachable; accept Chrome's prompt.")

        def fail_run(_task, _output, factory):
            factory(task["url"])

        with TemporaryDirectory() as temp, patch.object(sys, "argv", [
            "jev-qa", "run", "task.json", "--browser", "existing-chrome", "--output", temp + "/result",
        ]), patch("jev_qa.__main__.load_env"), patch("jev_qa.__main__.read_json", return_value=task), \
             patch("jev_qa.__main__.isolated_runtime", return_value=nullcontext()), \
             patch("jev_qa.__main__.browser_session", side_effect=fail_factory), \
             patch.object(runner, "validate_task", return_value=task), \
             patch.object(runner, "run_task", side_effect=fail_run), \
             patch("sys.stderr", new_callable=StringIO) as stderr:
            self.assertEqual(main(), 2)
        self.assertIn("Existing Chrome remote debugging is unreachable", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
