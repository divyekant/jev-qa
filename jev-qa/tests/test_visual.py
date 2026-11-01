"""Jev screenshot review. Model calls are stubbed; screenshots come from disposable Chrome."""

import base64
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jev_qa import design  # noqa: E402

PASS = {"choice": "pass", "confidence": 0.95, "probabilities": {"pass": 0.95, "fail": 0.03, "uncertain": 0.02}}


class VisualUnitTest(unittest.TestCase):
    def test_validation_selector_is_optional_and_criterion_required(self):
        checks = design.validate_checks([
            {"id": "page", "kind": "visual", "criterion": "No element looks broken."},
            {"id": "logo", "kind": "visual", "selector": "#logo", "criterion": "The logo is legible."},
        ])
        self.assertNotIn("selector", checks[0])
        self.assertEqual(checks[1]["selector"], "#logo")
        for bad in ({"kind": "visual"}, {"kind": "visual", "criterion": "x", "selector": ""}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                design.validate_checks([{"id": "v", **bad}])

    def test_request_puts_each_image_in_its_own_question_with_opt_in_header(self):
        from jev_qa import runner

        sent = {}

        def fake_post(url, key, body):
            sent.update(body)
            return {"model": "jev-1.13.0", "answers": {"criterion_0": PASS, "criterion_1": PASS}}

        image = {"ref": "jev-qa-abc", "data_base64": "AAAA"}
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test-key"}), \
                patch.object(runner, "post_json_images", fake_post), \
                patch.object(runner, "post_json", side_effect=AssertionError("text path used")):
            result = runner.review_evidence({"x": 1}, ["First.", "Second."], jev_only=True, images={0: image})
        self.assertEqual(sent["assets"], {"jev-qa-abc": {"type": "image", "format": "jpg", "data_base64": "AAAA"}})
        self.assertEqual(sent["questions"]["criterion_0"]["instructions"]["screenshot"], "jev-qa-abc")
        self.assertNotIn("screenshot", sent["questions"]["criterion_1"]["instructions"])
        self.assertNotIn("jev-qa-abc", json.dumps(sent["state"]))
        self.assertEqual(result["judgments"][0]["assessment"], "pass")
        self.assertEqual(runner.IMAGE_HEADER, {"TypeSafe-Danger-Zone-Images": "true"})

    def test_text_review_still_uses_upstream_post_without_assets(self):
        from jev_qa import runner

        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test-key"}), \
                patch.object(runner, "post_json", return_value={"model": "jev-1.13.0", "answers": {}}) as post:
            runner.review_evidence({"x": 1}, ["First."], jev_only=True)
        self.assertNotIn("assets", post.call_args.args[2])

    def test_clip_meets_image_limits_and_offscreen_target_is_uncertain(self):
        raw = {"viewport": {"x": 0, "y": 0, "width": 390, "height": 844, "right": 390, "bottom": 844},
               "box": {"x": 380, "y": 10, "width": 10, "height": 10, "right": 390, "bottom": 20},
               "scroll": {"x": 0, "y": 0}, "target": "element", "inViewport": True}
        clip = design._visual_clip(raw)
        self.assertEqual((clip["x"], clip["y"], clip["width"], clip["height"]), (110, 0, 280, 280))
        wide = {**raw, "box": {"x": 0, "y": 400, "width": 390, "height": 2, "right": 390, "bottom": 402}}
        self.assertGreaterEqual(design._visual_clip(wide)["height"], 280)
        self.assertEqual(design._visual_clip({**raw, "inViewport": False}), "visual_target_not_in_viewport")
        small = {**raw, "viewport": {"x": 0, "y": 0, "width": 200, "height": 844, "right": 200, "bottom": 844}}
        self.assertEqual(design._visual_clip(small), "viewport_below_image_minimum")

    def test_longest_criterion_fits_runner_limit_and_write_failure_is_kept(self):
        from jev_qa import runner

        sent = []

        def fake_review(observation, criterion, image, min_confidence):
            sent.append(criterion)
            return {"judgments": [{"assessment": "pass", "confidence": 0.9, "model": "jev-1.13.0"}]}

        longest = "x" * design.MAX_VISUAL_CRITERION
        check = design.validate_checks([{"id": "v", "kind": "visual", "selector": "#a", "criterion": longest}])[0]
        with self.assertRaises(ValueError):
            design.validate_checks([{"id": "v", "kind": "visual", "criterion": longest + "x"}])
        shot = {"jpeg": b"jpeg", "size": [280, 280], "target_box": {"x": 0, "y": 0, "width": 10, "height": 10}}
        raw = {"status": "measured", "visible": True, "target": "element"}
        with patch.object(design, "_review_visual", fake_review):
            result = design._visual_entry(shot, check, raw, 0.8, Path("/nonexistent/jev-qa"), 1, [])
        self.assertEqual(runner._criteria(sent), sent)
        self.assertEqual(result["evidence"]["screenshot"]["file_error"], "evidence_write_failed")
        self.assertTrue(result["advisory"])


class VisualChromeTest(unittest.TestCase):
    def test_screenshot_capture_and_advisory_review_in_chrome(self):
        if not os.environ.get("JEV_QA_VISUAL_TEST_CHILD"):
            result = subprocess.run(
                [sys.executable, __file__, "VisualChromeTest"],
                env={**os.environ, "JEV_QA_VISUAL_TEST_CHILD": "1", "PYTHONPATH": str(ROOT)},
                capture_output=True, text=True, timeout=90,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return

        from PIL import Image

        from jev_qa.browser import browser_session, isolated_runtime

        calls = []

        def fake_review(observation, criterion, image, min_confidence):
            calls.append((observation, criterion, image))
            return {"judgments": [{"assessment": "fail", "confidence": 0.9, "model": "jev-1.13.0"}],
                    "model_usage": [{"model": "jev-1.13.0", "usage": {"input_tokens": 1}}]}

        def decode(image):
            return Image.open(io.BytesIO(base64.b64decode(image["data_base64"]))).convert("RGB")

        page = ('<!doctype html><style>body{margin:0;background:#fff}</style><div style="height:1200px"></div>'
                '<div id="mark" style="width:40px;height:40px;background:rgb(255,0,0)"></div>'
                '<div style="height:1200px"></div>')
        checks = [{"id": "mark", "kind": "visual", "selector": "#mark", "criterion": "The mark is green."},
                  {"id": "page", "kind": "visual", "criterion": "The page has no broken layout."},
                  {"id": "rule", "kind": "horizontal_fit"}]
        with isolated_runtime(), browser_session("about:blank") as browser, \
                patch.object(design, "_review_visual", fake_review), tempfile.TemporaryDirectory() as folder:
            for width, height, scale in ((390, 844, 1), (390, 844, 2), (2000, 900, 1)):
                with self.subTest(viewport=(width, height, scale)):
                    calls.clear()
                    browser.call("Emulation.setDeviceMetricsOverride", width=width, height=height,
                                 deviceScaleFactor=scale, mobile=False)
                    browser.evaluate("document.open();document.write(" + json.dumps(page) + ");document.close()")
                    browser.evaluate("document.getElementById('mark').scrollIntoView({block:'center'})")
                    report = inspect = design.inspect_design(browser, checks, evidence_dir=Path(folder))
                    rows = {row["id"]: row for row in inspect["checks"]}
                    # Jev's visual fail stays advisory: it cannot fail the report or override the rule pass.
                    self.assertEqual(report["status"], "needs_review", report)
                    self.assertEqual(rows["rule"]["assessment"], "pass")
                    self.assertTrue(rows["mark"]["advisory"] and rows["mark"]["source"] == "jev", rows["mark"])
                    self.assertEqual(len(calls), 2)
                    self.assertEqual(len(report["model_usage"]), 2)
                    self.assertNotIn(calls[0][2]["data_base64"][:200], json.dumps(report))
                    for _observation, _criterion, image in calls:
                        size = decode(image).size
                        self.assertTrue(280 <= min(size) and max(size) <= 1568, size)
                    mark = decode(calls[0][2])
                    box = calls[0][0]["screenshot"]["target_box"]
                    centre = mark.getpixel((int(box["x"] + box["width"] / 2), int(box["y"] + box["height"] / 2)))
                    self.assertGreater(centre[0], 200, (centre, box))
                    self.assertLess(centre[1], 60, (centre, box))
                    saved = Path(folder) / rows["mark"]["evidence"]["screenshot"]["file"]
                    self.assertEqual(oct(saved.stat().st_mode & 0o777), "0o600")

            browser.evaluate("window.scrollTo(0, 0)")
            report = design.inspect_design(browser, checks[:1])
            self.assertEqual(report["checks"][0]["reason"], "visual_target_not_in_viewport", report)

            # The page scrolls after measurement: the stale clip must not be captured or sent.
            browser.evaluate("document.getElementById('mark').scrollIntoView({block:'center'})")
            original = design._measure
            moved = []

            def measure_then_scroll(target, checks_):
                result = original(target, checks_)
                if not moved:
                    moved.append(True)
                    target.evaluate("window.scrollBy(0, 300)")
                return result

            calls.clear()
            with patch.object(design, "_measure", measure_then_scroll):
                report = design.inspect_design(browser, checks[:1])
            self.assertEqual(report["checks"][0]["reason"], "page_moved_before_capture", report)
            self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
