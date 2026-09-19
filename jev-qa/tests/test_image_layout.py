"""Image layout checks against disposable Chrome. No model calls or remote pages."""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from urllib.parse import quote


IMAGE = "data:image/svg+xml," + quote(
    '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">'
    '<rect width="200" height="100" fill="blue"/></svg>'
)


def fixture(image_css="", card_css="", outer_css="", source=IMAGE):
    return (
        '<style>body{margin:0}#outer{width:300px;height:200px}'
        '#card{width:100px;height:100px}img{display:block;width:100px;height:100px}</style>'
        f'<div id="outer" style="{outer_css}"><div id="card" style="{card_css}">'
        f'<img id="image" src="{source}" style="{image_css}"></div></div>'
        '<div id="unrelated" style="width:100px;height:100px"></div>'
    )


class ImageLayoutTest(unittest.TestCase):
    def test_image_geometry_and_crop_policy_in_chrome(self):
        if not os.environ.get("JEV_QA_IMAGE_TEST_CHILD"):
            result = subprocess.run(
                [sys.executable, __file__],
                env={**os.environ, "JEV_QA_IMAGE_TEST_CHILD": "1",
                     "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
                capture_output=True, text=True, timeout=90,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return

        from jev_qa.browser import browser_session, isolated_runtime
        from jev_qa.design import inspect_design

        checks = [
            {"id": "bounds", "kind": "image_contained", "selector": "#image", "container": "#card"},
            {"id": "full", "kind": "image_crop", "selector": "#image", "expected": "full"},
            {"id": "allowed", "kind": "image_crop", "selector": "#image", "expected": "allowed"},
        ]
        # Expected outcomes are hand-derived from a 200x100 source and 100x100 card.
        cases = [
            ("fill", fixture(), ("pass", "pass", "pass")),
            ("contain", fixture("object-fit:contain"), ("pass", "pass", "pass")),
            ("cover crops", fixture("object-fit:cover"), ("pass", "fail", "pass")),
            ("cover same ratio", fixture("object-fit:cover;height:50px"), ("pass", "pass", "pass")),
            ("none crops", fixture("object-fit:none"), ("pass", "fail", "pass")),
            ("scale down", fixture("object-fit:scale-down"), ("pass", "pass", "pass")),
            ("scale down does not enlarge", fixture("object-fit:scale-down;width:250px;height:150px",
                                                    "width:250px;height:150px"), ("pass", "pass", "pass")),
            ("contained source shifted", fixture("object-fit:contain;object-position:0px 80px"),
             ("pass", "fail", "pass")),
            ("percent position crops", fixture("object-fit:contain;object-position:50% 150%"),
             ("pass", "fail", "pass")),
            ("edge position fits", fixture("object-fit:contain;object-position:right bottom"),
             ("pass", "pass", "pass")),
            ("overflow inside page", fixture("width:160px"), ("fail", "pass", "pass")),
            ("vertical overflow", fixture("height:160px"), ("fail", "pass", "pass")),
            ("left overflow", fixture("margin-left:-20px"), ("fail", "pass", "pass")),
            ("card clips overflow", fixture("width:160px", "overflow:hidden"), ("pass", "fail", "pass")),
            ("card clips vertically", fixture("height:160px", "overflow:clip"), ("pass", "fail", "pass")),
            ("ancestor above card clips", fixture("", "", "width:70px;overflow:hidden"),
             ("pass", "fail", "pass")),
            ("scroll container clips", fixture("width:160px", "overflow:auto"), ("pass", "fail", "pass")),
            ("border and padding", fixture("box-sizing:border-box;padding:10px;border:5px solid;object-fit:contain",
                                           "padding:10px;border:5px solid"), ("pass", "pass", "pass")),
            ("border box cover crops", fixture("box-sizing:border-box;padding:10px;border:5px solid;object-fit:cover"),
             ("pass", "fail", "pass")),
            ("offscreen is not cropping", fixture("", "margin-top:1200px", "height:1400px"),
             ("pass", "pass", "pass")),
            ("hidden image", fixture("display:none"), ("uncertain", "uncertain", "uncertain")),
            ("broken image", fixture(source="data:image/png;base64,broken"),
             ("uncertain", "uncertain", "uncertain")),
            ("transformed ancestor", fixture(outer_css="transform:scale(.8)"),
             ("uncertain", "uncertain", "uncertain")),
            ("individual rotation", fixture("rotate:10deg"), ("uncertain", "uncertain", "uncertain")),
            ("clip path", fixture("clip-path:inset(10px)"), ("uncertain", "uncertain", "uncertain")),
            ("rounded crop", fixture("border-radius:50%"), ("uncertain", "uncertain", "uncertain")),
            ("extended clip margin", fixture("width:120px", "overflow:clip;overflow-clip-margin:20px"),
             ("uncertain", "uncertain", "uncertain")),
            ("stylesheet content clip", fixture("margin-left:-20px", "padding:20px;overflow:clip") +
             '<style>#card{overflow-clip-margin:content-box}</style>',
             ("uncertain", "uncertain", "uncertain")),
            ("body overflow propagation", fixture("width:160px") +
             '<style>body{width:100px;height:100px;overflow:hidden}</style>',
             ("uncertain", "uncertain", "uncertain")),
        ]
        with isolated_runtime():
            with browser_session("about:blank") as browser:
                browser.call("Emulation.setDeviceMetricsOverride", width=390, height=844,
                             deviceScaleFactor=1, mobile=False)

                def load(html):
                    browser.evaluate("document.open();document.write(" + json.dumps("<!doctype html>" + html) +
                                     ");document.close()")
                    self.assertEqual(browser.evaluate("document.compatMode"), "CSS1Compat")
                    ready = browser.call(
                        "Runtime.evaluate",
                        expression="(async()=>{await Promise.all([...document.images].map(i=>i.decode().catch(()=>{})));"
                        "return [...document.images].every(i=>i.complete)})()",
                        awaitPromise=True, returnByValue=True,
                    )
                    self.assertTrue(ready.get("result", {}).get("value"), "fixture images did not finish loading")

                for name, html, expected in cases:
                    with self.subTest(case=name):
                        load(html)
                        report = inspect_design(browser, checks)
                        self.assertEqual(tuple(row["assessment"] for row in report["checks"]), expected, report)
                        self.assertEqual(report["model_usage"], [])
                        self.assertFalse(report["coverage"]["pixelContentInspected"])
                        self.assertNotIn(IMAGE, json.dumps(report))

                load(fixture())
                for changes in ({"selector": "#missing"}, {"selector": "img, #card"},
                                {"selector": "#card"}, {"container": "#unrelated"}, {"container": "#image"}):
                    with self.subTest(invalid=changes):
                        report = inspect_design(browser, [{**checks[0], **changes}])
                        self.assertEqual(report["status"], "needs_review", report)

                load(fixture("width:100.4px;height:50px;object-fit:cover"))
                report = inspect_design(browser, [{**checks[1], "tolerance": 0}])
                self.assertEqual(report["checks"][0]["assessment"], "fail", report)

                for width, expected in ((390, "fail"), (1280, "pass")):
                    with self.subTest(viewport=width):
                        browser.call("Emulation.setDeviceMetricsOverride", width=width, height=844,
                                     deviceScaleFactor=1, mobile=False)
                        load(fixture("width:400px", "width:80vw", "width:100vw"))
                        report = inspect_design(browser, [checks[0]])
                        self.assertEqual(report["checks"][0]["assessment"], expected, report)


if __name__ == "__main__":
    unittest.main()
