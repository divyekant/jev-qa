"""Focused tests for bounded, rule-first design assessment."""

import math
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jev_qa import design  # noqa: E402


def box(x=0, y=0, width=100, height=20):
    return {"x": x, "y": y, "width": width, "height": height, "right": x + width, "bottom": y + height}


class FakeBrowser:
    def __init__(self, result):
        self.result = result
        self.expressions = []

    def evaluate(self, expression):
        self.expressions.append(expression)
        return self.result


class RaisingBrowser(FakeBrowser):
    def __init__(self, error):
        super().__init__(None)
        self.error = error

    def evaluate(self, expression):
        self.expressions.append(expression)
        raise self.error


class DesignTests(unittest.TestCase):
    def test_validation_normalizes_defaults_and_rejects_unsafe_descriptors(self):
        checks = design.validate_checks(
            [
                {"id": "contrast", "kind": "contrast", "selector": "#status"},
                {"id": "fit", "kind": "horizontal_fit"},
                {"id": "aligned", "kind": "aligned", "selector": "#a", "other": "#b"},
            ]
        )
        self.assertEqual(checks[0]["min_ratio"], 4.5)
        self.assertEqual(checks[1]["tolerance"], 1.0)
        self.assertEqual(checks[2]["tolerance"], 2.0)
        invalid = [
            {"id": "x", "kind": "contrast", "selector": "#x", "extra": True},
            {"id": "x", "kind": "horizontal_fit", "selector": "#x"},
            {"id": "x", "kind": "contrast", "selector": "#x", "min_ratio": math.nan},
            {"id": "x", "kind": "contrast", "selector": "#x", "min_ratio": 0},
            {"id": "x", "kind": "contrast", "selector": "#x", "min_ratio": 22},
        ]
        for descriptor in invalid:
            with self.subTest(descriptor=descriptor), self.assertRaises(ValueError):
                design.validate_checks([descriptor])

        with self.assertRaises(ValueError):
            design.validate_checks(
                [{"id": str(index), "kind": "artwork", "selector": "#art"} for index in range(21)]
            )

    def test_rule_classification_keeps_measurement_failure_uncertain(self):
        check = {"id": "title", "kind": "unclipped", "selector": "#title"}
        good = {
            "status": "measured",
            "visible": True,
            "box": box(width=100),
            "textBox": box(width=95),
            "overflowX": "hidden",
            "overflowY": "visible",
            "scrollWidth": 100,
            "clientWidth": 100,
            "scrollHeight": 20,
            "clientHeight": 20,
        }
        bad = {**good, "textBox": box(width=120), "scrollWidth": 120}
        self.assertEqual(design.classify_measurement(check, good)["assessment"], "pass")
        self.assertEqual(design.classify_measurement(check, bad)["assessment"], "fail")
        missing = {"status": "measurement_error", "reason": "selector_not_found"}
        result = design.classify_measurement(check, missing)
        self.assertEqual(result["assessment"], "uncertain")
        self.assertEqual(result["evidence"]["status"], "measurement_error")

    def test_native_disabled_and_unsupported_contrast_are_fail_closed(self):
        disabled = {"id": "control", "kind": "disabled", "selector": "#control"}
        native = {"status": "measured", "visible": True, "nativeDisabled": True, "ariaDisabled": False}
        aria_only = {"status": "measured", "visible": True, "nativeDisabled": False, "ariaDisabled": True}
        self.assertEqual(design.classify_measurement(disabled, native)["assessment"], "pass")
        self.assertEqual(design.classify_measurement(disabled, aria_only)["assessment"], "fail")

        contrast = {"id": "text", "kind": "contrast", "selector": "#text"}
        unsupported = {"status": "unsupported", "reason": "complex_background"}
        self.assertEqual(design.classify_measurement(contrast, unsupported)["assessment"], "uncertain")

    def test_geometry_hit_and_artwork_rules(self):
        hit = {"id": "save", "kind": "unobstructed", "selector": "#save"}
        offscreen = {"status": "measured", "visible": True, "inViewport": False, "hitSamples": []}
        self.assertEqual(design.classify_measurement(hit, offscreen)["assessment"], "uncertain")

        ellipsis = {"id": "reference", "kind": "ellipsis", "selector": "#reference"}
        valid = {
            "status": "measured", "visible": True, "clientWidth": 50, "scrollWidth": 100,
            "whiteSpace": "nowrap", "textOverflow": "ellipsis",
            "fullText": "A long reference", "title": "A long reference",
        }
        self.assertEqual(design.classify_measurement(ellipsis, valid)["assessment"], "pass")
        self.assertEqual(design.classify_measurement(ellipsis, {**valid, "title": "short"})["assessment"], "fail")

        artwork = {"id": "mark", "kind": "artwork", "selector": "#mark"}
        result = design.classify_measurement(artwork, {"status": "measured", "visible": True})
        self.assertEqual(result["assessment"], "uncertain")
        self.assertEqual(result["source"], "unsupported")

    def test_model_cannot_override_missing_evidence_or_deterministic_failure(self):
        checks = [
            {"id": "contrast", "kind": "contrast", "selector": "#status"},
            {"id": "semantic", "kind": "contextual", "selector": "#status", "criterion": "It is clear."},
        ]
        browser = FakeBrowser(
            {
                "checks": {
                    "contrast": {
                        "status": "measured",
                        "visible": True,
                        "contrastRatio": 2.0,
                        "contrastSupported": True,
                    },
                    "semantic": {"status": "measurement_error", "reason": "selector_not_found"},
                },
                "viewport": {"width": 800, "height": 600, "documentWidth": 800},
            }
        )
        with patch.object(
            design,
            "_review_contextual",
            return_value=[{"assessment": "pass", "confidence": 1.0, "model": "jev-latest"}],
        ) as review:
            report = design.inspect_design(browser, checks)
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["checks"][0]["assessment"], "fail")
        self.assertEqual(report["checks"][1]["assessment"], "uncertain")
        review.assert_not_called()
        self.assertEqual(len(browser.expressions), 1)

    def test_contextual_pass_is_advisory_and_empty_checks_do_not_evaluate(self):
        browser = FakeBrowser({"checks": {}, "viewport": {"width": 800, "height": 600, "documentWidth": 800}})
        self.assertEqual(design.inspect_design(browser, []), {"status": "pass", "checks": [], "model_usage": []})
        self.assertEqual(browser.expressions, [])

        checks = [{"id": "semantic", "kind": "contextual", "selector": "#status", "criterion": "It is clear."}]
        browser = FakeBrowser(
            {
                "checks": {
                    "semantic": {
                        "status": "measured",
                        "visible": True,
                        "box": box(),
                        "text": "Ready",
                        "role": "status",
                    }
                },
                "viewport": {"width": 800, "height": 600, "documentWidth": 800},
            }
        )
        with patch.object(
            design,
            "_review_contextual",
            return_value=[{"assessment": "pass", "confidence": 1.0, "model": "jev-latest"}],
        ):
            report = design.inspect_design(browser, checks)
        self.assertEqual(report["status"], "needs_review")
        self.assertEqual(report["checks"][0]["assessment"], "pass")
        self.assertTrue(report["checks"][0]["advisory"])

    def test_browser_measurement_exception_is_safe_and_reaches_affected_checks(self):
        browser = RaisingBrowser(RuntimeError("Bearer provider-secret-token"))
        checks = [{"id": "title", "kind": "unclipped", "selector": "#title"}]

        report = design.inspect_design(browser, checks)

        self.assertEqual(report["error"], {"type": "RuntimeError", "reason": "browser measurement failed"})
        check = report["checks"][0]
        self.assertEqual(check["assessment"], "uncertain")
        self.assertEqual(check["reason"], "browser measurement failed")
        self.assertEqual(check["evidence"]["reason"], "browser measurement failed")
        self.assertNotIn("provider-secret-token", repr(report))

    def test_report_retains_bounded_measurement_metadata(self):
        browser = FakeBrowser(
            {
                "checks": {
                    "fit": {
                        "status": "measured",
                        "viewportWidth": 390,
                        "documentWidth": 390,
                    }
                },
                "viewport": {"width": 390, "height": 844, "documentWidth": 390, "secret": "drop"},
                "coverage": {
                    "geometry": True,
                    "textBounds": False,
                    "contrast": False,
                    "hitTesting": False,
                    "pixelContentInspected": False,
                    "secret": "drop",
                },
            }
        )

        report = design.inspect_design(browser, [{"id": "fit", "kind": "horizontal_fit"}])

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["viewport"], {"width": 390, "height": 844, "documentWidth": 390})
        self.assertEqual(
            report["coverage"],
            {
                "geometry": True,
                "textBounds": False,
                "contrast": False,
                "hitTesting": False,
                "pixelContentInspected": False,
            },
        )


if __name__ == "__main__":
    unittest.main()
