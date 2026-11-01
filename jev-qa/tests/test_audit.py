"""Page audit against disposable Chrome. No model calls or remote pages."""

import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jev_qa import design  # noqa: E402

IMAGE = "data:image/svg+xml," + quote(
    '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"><rect width="200" height="100"/></svg>'
)
STYLE = "<style>body{margin:0;font:16px sans-serif;background:#fff;color:#111}button{width:120px;height:40px}</style>"
CLEAN = (
    f'<html lang="en"><title>Clean</title>{STYLE}<h1>Welcome</h1>'
    '<p>Read the <a href="#terms">terms</a> today.</p><button id="go">Continue</button>'
    f'<img id="photo" alt="Blue box" src="{IMAGE}" style="display:block;width:100px;height:50px">'
    '<div style="position:relative;height:40px"><span>Hidden page text</span>'
    '<div style="position:absolute;inset:0;background:#fff"><span>Panel text</span></div></div>'
)
BROKEN = (
    f'<html>{STYLE}<p id="faint" style="color:#ccc">Faint text</p>'
    '<div id="clip" style="width:40px;overflow:hidden;white-space:nowrap">A long clipped label</div>'
    '<div><button id="icon" style="width:40px"></button><button id="tiny" style="width:16px;height:16px;padding:0">x</button></div>'
    f'<img id="noalt" src="{IMAGE}" style="display:block;width:100px;height:50px">'
    '<img id="broken" alt="Broken" src="data:image/png;base64,broken" style="display:block;width:20px;height:20px">'
    '<div style="position:relative;height:40px"><span id="under-text">Overlap one</span>'
    '<span id="over-text" style="position:absolute;left:0;top:0">Overlap two</span></div>'
    '<div style="position:relative"><button id="covered">Covered</button>'
    '<div style="position:absolute;inset:0;background:#eee"></div></div>'
    '<div id="wide" style="width:600px">Wide row</div>'
)
EXPECTED_FAILURES = {
    ("contrast", "contrast_below_minimum", "faint"),
    ("unclipped", "content_clipped", "clip"),
    ("accessible_name", "control_missing_accessible_name", "icon"),
    ("target_size", "target_too_small", "tiny"),
    ("image_alt", "image_missing_alt", "noalt"),
    ("image_loaded", "image_broken", "broken"),
    ("text_overlap", "text_overlaps_text", "under-text"),
    ("unobstructed", "target_is_obstructed", "covered"),
    ("horizontal_fit", "horizontal_overflow", None),
    ("document_language", "document_language_missing", None),
    ("document_title", "document_title_missing", None),
}

LAYER = '<div style="position:relative;height:40px"><span id="t">Overlap one</span>{}' \
    '<span style="position:absolute;left:0;top:0{}">Overlap two</span></div>'
# Review regressions: (name, html, expected findings for #t as (kind, assessment, reason); empty means none).
REVIEW_CASES = [
    ("sibling layer under text", '<div style="position:relative"><div style="position:absolute;inset:0;background:#000">'
     '</div><p id="t" style="position:relative;color:#222">Dark layer</p></div>',
     {("contrast", "uncertain", "backdrop_layer_unknown")}),
    ("svg text fill", '<svg width="200" height="40" style="overflow:visible"><text id="t" x="0" y="20" fill="#eee">'
     'Svg</text></svg>', {("contrast", "uncertain", "svg_text_paint")}),
    ("aria-hidden name", '<button id="t"><span aria-hidden="true">&times;</span></button>',
     {("accessible_name", "fail", "control_missing_accessible_name")}),
    ("shadow root", '<div id="t"></div><script>document.getElementById("t").attachShadow({mode:"open"})'
     '.innerHTML="<p>x</p>"</script>', {("unswept", "uncertain", "shadow_root_not_swept")}),
    ("display contents", '<div id="t" style="display:contents;color:#eee">Contents</div>',
     {("unswept", "uncertain", "display_contents_text")}),
    ("translucent layer", LAYER.format('<div style="position:absolute;inset:0;background:#fff;opacity:.2"></div>', ""),
     {("text_overlap", "uncertain", "overlap_stacking_unavailable")}),
    ("opaque badge", LAYER.format("", ";background:#fff"), set()),
    ("offscreen control", '<div style="height:2000px"></div><button id="t">Below</button>',
     {("unobstructed", "uncertain", "offscreen_hit_points")}),
    ("screen-reader-only text", '<span id="t" style="position:absolute;width:1px;height:1px;overflow:hidden;'
     'clip:rect(0,0,0,0);white-space:nowrap">Screen reader only label</span>', set()),
    ("ellipsis with title", '<div id="t" style="width:60px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis"'
     ' title="A long truncated label">A long truncated label</div>', set()),
    ("ellipsis without title", '<div id="t" style="width:60px;overflow:hidden;white-space:nowrap;'
     'text-overflow:ellipsis">A long truncated label</div>', {("ellipsis", "uncertain", "full_text_unavailable")}),
    ("aria-disabled control", '<div id="t" role="button" tabindex="0" aria-disabled="true" '
     'style="color:#bbb;width:100px;height:40px">Off</div>', set()),
]


class AuditUnitTest(unittest.TestCase):
    def test_validation_defaults_and_limits(self):
        self.assertEqual(design.validate_checks([{"id": "page", "kind": "audit"}])[0], {
            "id": "page", "kind": "audit", "scope": "body", "min_ratio": 4.5, "large_text_min_ratio": 3.0,
            "max_elements": 300})
        for bad in ({"max_elements": 0}, {"max_elements": 1.5}, {"scope": ""}, {"selector": "#x"}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                design.validate_checks([{"id": "page", "kind": "audit", **bad}])

    def test_large_text_threshold_and_fail_closed_items(self):
        check = design.validate_checks([{"id": "page", "kind": "audit"}])[0]
        text = {"status": "measured", "visible": True, "contrastSupported": True, "contrastRatio": 3.5}
        evidence = {"status": "measured", "truncated": False, "items": [
            {"kind": "contrast", "selector": "h1", "evidence": {**text, "fontSizePx": 24, "fontWeight": 400}},
            {"kind": "contrast", "selector": "p", "evidence": {**text, "fontSizePx": 16, "fontWeight": 700}},
            {"kind": "text_overlap", "selector": "span", "evidence": {"status": "measured", "covered": None}},
            {"kind": "invented", "selector": "x", "evidence": {"status": "measured"}},
            "malformed",
        ]}
        result = design.classify_measurement(check, evidence)
        self.assertEqual(result["assessment"], "fail")
        self.assertEqual([row["assessment"] for row in result["findings"]], ["fail", "uncertain", "uncertain", "uncertain"])
        self.assertEqual(result["findings"][0]["selector"], "p")
        self.assertEqual(result["evidence"]["counts"]["contrast"], {"pass": 1, "fail": 1, "uncertain": 0})

    def test_malformed_item_reason_stays_uncertain(self):
        check = design.validate_checks([{"id": "page", "kind": "audit"}])[0]
        evidence = {"status": "measured", "truncated": False, "items": [
            {"kind": "contrast", "selector": "p", "evidence": {"status": "measurement_error", "reason": ["x"]}},
            {"kind": "text_overlap", "selector": "p", "evidence": {"status": "measured", "covered": "no"}},
        ]}
        result = design.classify_measurement(check, evidence)
        self.assertEqual([row["assessment"] for row in result["findings"]], ["uncertain", "uncertain"])

    def test_truncated_or_missing_sweep_is_never_a_pass(self):
        check = design.validate_checks([{"id": "page", "kind": "audit"}])[0]
        self.assertEqual(design.classify_measurement(check, {"status": "measured", "truncated": True, "items": []})
                         ["reason"], "audit_truncated")
        self.assertEqual(design.classify_measurement(check, {"status": "measured"})["assessment"], "uncertain")


class AuditChromeTest(unittest.TestCase):
    def test_page_audit_in_chrome(self):
        if not os.environ.get("JEV_QA_AUDIT_TEST_CHILD"):
            result = subprocess.run(
                [sys.executable, __file__, "AuditChromeTest"],
                env={**os.environ, "JEV_QA_AUDIT_TEST_CHILD": "1", "PYTHONPATH": str(ROOT)},
                capture_output=True, text=True, timeout=90,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return

        from jev_qa.browser import browser_session, isolated_runtime
        from jev_qa.design import inspect_design

        with isolated_runtime():
            with browser_session("about:blank") as browser:
                browser.call("Emulation.setDeviceMetricsOverride", width=390, height=844,
                             deviceScaleFactor=1, mobile=False)

                def load(html):
                    browser.evaluate("document.open();document.write(" + json.dumps("<!doctype html>" + html) +
                                     ");document.close()")
                    browser.call("Runtime.evaluate", awaitPromise=True, returnByValue=True, expression=(
                        "Promise.all([...document.images].map(i=>i.decode().catch(()=>{})))"))

                load(CLEAN)
                report = inspect_design(browser, [{"id": "page", "kind": "audit"}])
                self.assertEqual(report["status"], "pass", report)
                self.assertEqual(report["model_usage"], [])
                self.assertFalse(report["coverage"]["pixelContentInspected"])

                load(BROKEN)
                report = inspect_design(browser, [{"id": "page", "kind": "audit"}])
                audit = report["checks"][0]
                self.assertEqual((report["status"], audit["reason"]), ("fail", "audit_failures"), report)
                found = set()
                for row in audit["findings"]:
                    if row["assessment"] != "fail":
                        continue
                    target = None
                    if row["selector"] not in ("html", "title"):
                        target = browser.evaluate(
                            f"(() => {{const n = document.querySelectorAll({json.dumps(row['selector'])});"
                            "return n.length === 1 ? n[0].id : null})()")
                    found.add((row["kind"], row["reason"], target))
                self.assertEqual(found, EXPECTED_FAILURES, audit)

                report = inspect_design(browser, [{"id": "part", "kind": "audit", "scope": "#faint"}])
                kinds = {row["kind"] for row in report["checks"][0]["findings"]}
                self.assertEqual(kinds, {"contrast"}, report)

                bare = '<p id="text" style="color:#666">Grey text</p>'
                for head, expected in (("", "pass"), ('<meta name="color-scheme" content="dark">', "uncertain"),
                                       ('<style>:root{color-scheme:dark}</style>', "uncertain")):
                    with self.subTest(canvas=head):
                        load(head + bare)
                        report = inspect_design(browser, [{"id": "c", "kind": "contrast", "selector": "#text"}])
                        self.assertEqual(report["checks"][0]["assessment"], expected, report)

                for name, html, expected in REVIEW_CASES:
                    with self.subTest(review=name):
                        load(STYLE + html)
                        report = inspect_design(browser, [{"id": "page", "kind": "audit"}])
                        rows = set()
                        for row in report["checks"][0].get("findings", []):
                            target = browser.evaluate(
                                f"(() => {{const n = document.querySelectorAll({json.dumps(row['selector'])});"
                                "return n.length === 1 ? n[0].id : null})()")
                            if target == "t":
                                rows.add((row["kind"], row["assessment"], row["reason"]))
                        self.assertEqual(rows, expected, report)

                load(STYLE + '<div style="position:relative;height:40px">' +
                     '<span style="position:absolute;left:0;top:0">Stacked label</span>' * 400 + '</div>')
                started = time.monotonic()
                report = inspect_design(browser, [{"id": "page", "kind": "audit", "max_elements": 1000}])
                self.assertLess(time.monotonic() - started, 5)
                self.assertTrue(report["checks"][0]["evidence"]["truncated"], report)
                self.assertIn(report["checks"][0]["evidence"]["truncated_reason"], {"overlap_limit", "time_budget"})

                load('<html lang="en"><title>Root</title><script>const d = document.createElement("div");'
                     'd.textContent = "Outside body"; d.style.color = "#eee";'
                     'document.documentElement.appendChild(d)</script>')
                report = inspect_design(browser, [{"id": "page", "kind": "audit", "scope": "html"}])
                selectors = [row["selector"] for row in report["checks"][0]["findings"] if row["kind"] == "contrast"]
                self.assertEqual(len(selectors), 1, report)
                self.assertTrue(selectors[0].startswith("html > "), selectors)
                self.assertEqual(browser.evaluate(f"document.querySelectorAll({json.dumps(selectors[0])}).length"), 1)

                load(CLEAN)
                for check, reason in (({"max_elements": 2}, "audit_truncated"), ({"scope": "#missing"}, "selector_not_found")):
                    with self.subTest(check=check):
                        report = inspect_design(browser, [{"id": "page", "kind": "audit", **check}])
                        self.assertEqual((report["status"], report["checks"][0]["reason"]), ("needs_review", reason), report)


if __name__ == "__main__":
    unittest.main()
