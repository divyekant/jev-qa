"""Real browser lifecycle check. No models, network websites, or personal profile."""

import http.server
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote


class BrowserLifecycleTest(unittest.TestCase):
    def test_existing_chrome_endpoint_uses_validated_active_port(self):
        from jev_qa.browser import existing_chrome_ws

        with tempfile.TemporaryDirectory() as temp:
            active_port = Path(temp) / "DevToolsActivePort"
            active_port.write_text("45678\n/devtools/browser/fake-browser\n")
            with patch("jev_qa.browser.sys.platform", "darwin"):
                self.assertEqual(
                    existing_chrome_ws(active_port, validate=False),
                    "ws://127.0.0.1:45678/devtools/browser/fake-browser",
                )

    def test_existing_chrome_endpoint_rejects_invalid_port_and_path(self):
        from jev_qa.browser import BrowserSetupError, existing_chrome_ws

        with tempfile.TemporaryDirectory() as temp:
            active_port = Path(temp) / "DevToolsActivePort"
            with patch("jev_qa.browser.sys.platform", "darwin"):
                for value in ("0\n/devtools/browser/id\n", "65536\n/devtools/browser/id\n",
                              "1234\nhttp://127.0.0.1/devtools/browser/id\n"):
                    active_port.write_text(value)
                    with self.assertRaisesRegex(BrowserSetupError, "DevToolsActivePort"):
                        existing_chrome_ws(active_port, validate=False)

    def test_existing_chrome_constructor_failure_closes_created_target(self):
        from jev_qa import browser as module

        class FailedBrowser:
            def __init__(self, _url):
                self.target = "owned-target"
                raise RuntimeError("constructor failed")

        owned_targets = []
        with patch.object(module, "_close_target") as close_target:
            with self.assertRaisesRegex(RuntimeError, "constructor failed"):
                module._new_browser(FailedBrowser, "http://127.0.0.1:1", owned_targets)
        close_target.assert_called_once_with("owned-target")
        self.assertEqual(owned_targets, ["owned-target"])

    def test_cleanup_failure_is_visible_with_original_error(self):
        from jev_qa import browser as module

        original_message = "run failed " + ("x" * 500) + " token=private"
        original = RuntimeError(original_message)
        module._surface_cleanup_error(original, module.BrowserCleanupError("Browser cleanup incomplete."))
        self.assertEqual(str(original), original_message)
        self.assertTrue(original.jev_qa_cleanup_incomplete)
        self.assertEqual(original.jev_qa_cleanup_message, "Browser cleanup incomplete.")

    @unittest.skipUnless(sys.platform == "darwin", "existing Chrome mode is macOS-only")
    def test_existing_browser_preserves_process_and_preexisting_tabs(self):
        if not os.environ.get("JEV_QA_BROWSER_TEST_CHILD"):
            result = subprocess.run(
                [
                    sys.executable,
                    __file__,
                    "BrowserLifecycleTest.test_existing_browser_preserves_process_and_preexisting_tabs",
                ],
                env={
                    **os.environ,
                    "JEV_QA_BROWSER_TEST_CHILD": "1",
                    "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
                },
                capture_output=True,
                text=True,
                timeout=75,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return

        from jev_qa.browser import browser_session, chrome_path, isolated_runtime

        class FixtureHandler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                authenticated = "fixture_auth=ok" in self.headers.get("Cookie", "").split("; ")
                self.send_response(200 if authenticated else 401)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                body = (
                    "<title>Authenticated fixture</title><p>Fictional session.</p>"
                    if authenticated
                    else "<title>Unauthenticated</title>"
                )
                self.wfile.write(body.encode())

        class Cdp:
            def __init__(self, url):
                from websockets.sync.client import connect

                self.socket = connect(url, open_timeout=5)
                self.next_id = 0

            def call(self, method, params=None, session_id=None):
                self.next_id += 1
                message = {"id": self.next_id, "method": method, "params": params or {}}
                if session_id:
                    message["sessionId"] = session_id
                self.socket.send(json.dumps(message))
                while True:
                    response = json.loads(self.socket.recv())
                    if response.get("id") == self.next_id:
                        if "error" in response:
                            raise RuntimeError(response["error"])
                        return response.get("result", {})

            def close(self):
                self.socket.close()

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        profile = Path(tempfile.mkdtemp(prefix="jevqa-existing-browser-"))
        process = None
        connection = None
        try:
            process = subprocess.Popen(
                [
                    chrome_path(),
                    "--headless=new",
                    "--remote-debugging-port=0",
                    "--remote-debugging-address=127.0.0.1",
                    "--remote-allow-origins=*",
                    f"--user-data-dir={profile}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "about:blank",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            active_port = profile / "DevToolsActivePort"
            deadline = time.monotonic() + 15
            while not active_port.exists():
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("fixture Chrome did not start")
                time.sleep(0.05)
            port, endpoint = active_port.read_text().splitlines()[:2]
            connection = Cdp(f"ws://127.0.0.1:{int(port)}{endpoint}")
            sentinel = connection.call("Target.createTarget", {
                "url": "data:text/html,<title>Preexisting sentinel</title>", "background": True,
            })["targetId"]
            sentinel_session = connection.call(
                "Target.attachToTarget", {"targetId": sentinel, "flatten": True},
            )["sessionId"]
            fixture_url = f"http://127.0.0.1:{server.server_port}/app"
            connection.call(
                "Network.setCookie",
                {"name": "fixture_auth", "value": "ok", "url": fixture_url, "httpOnly": True, "path": "/"},
                sentinel_session,
            )
            before = {
                target["targetId"]
                for target in connection.call("Target.getTargets")["targetInfos"]
                if target["type"] == "page"
            }
            with isolated_runtime() as runtime:
                with patch(
                    "jev_qa.browser._discover_existing_chrome_ws",
                    return_value=f"ws://127.0.0.1:{int(port)}{endpoint}",
                ):
                    with browser_session(fixture_url, existing=True) as browser:
                        self.assertEqual(browser.evaluate("document.title"), "Authenticated fixture")
                        self.assertEqual(browser.evaluate("document.cookie"), "")
                        self.assertNotIn(browser.target, before)
                        owned = set(browser._jevqa_owned_target_ids)
                        self.assertEqual(len(owned), 2)
                        concurrent = connection.call("Target.createTarget", {
                            "url": "data:text/html,<title>User concurrent tab</title>", "background": True,
                        })["targetId"]
                        daemon_pid = int((Path(os.environ["BH_RUNTIME_DIR"]) / "bu.pid").read_text())
                        os.kill(daemon_pid, signal.SIGKILL)
                        time.sleep(0.1)
            self.assertIsNone(process.poll())
            after_targets = connection.call("Target.getTargets")["targetInfos"]
            after = {
                target["targetId"]
                for target in after_targets
                if target["type"] == "page"
            }
            self.assertTrue({sentinel, concurrent} <= after)
            self.assertTrue(owned.isdisjoint(after))
            cookies = connection.call("Network.getCookies", {
                "urls": [fixture_url],
            }, sentinel_session)["cookies"]
            self.assertTrue(any(cookie["name"] == "fixture_auth" and cookie["value"] == "ok" for cookie in cookies))
            self.assertFalse(runtime.exists())
            self.assertNotIn(str(runtime), subprocess.check_output(["ps", "-axo", "command"], text=True))
        finally:
            if connection is not None:
                connection.close()
            server.shutdown()
            server.server_close()
            if process is not None:
                process.terminate()
                process.wait(timeout=10)
            shutil.rmtree(profile, ignore_errors=True)

    def test_ellipsis_sensor_reads_current_native_title(self):
        if not os.environ.get("JEV_QA_BROWSER_TEST_CHILD"):
            result = subprocess.run(
                [sys.executable, __file__, "BrowserLifecycleTest.test_ellipsis_sensor_reads_current_native_title"],
                env={**os.environ, "JEV_QA_BROWSER_TEST_CHILD": "1", "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
                capture_output=True, text=True, timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return
        from jev_qa.browser import browser_session, isolated_runtime
        from jev_qa.design import inspect_design

        html = '<p id="ref" style="width:50px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="Long native reference">Long native reference</p>'
        with isolated_runtime():
            with browser_session("data:text/html," + html) as browser:
                check = [{"id": "reference", "kind": "ellipsis", "selector": "#ref"}]
                self.assertEqual(inspect_design(browser, check)["checks"][0]["assessment"], "pass")
                browser.evaluate("document.getElementById('ref').title='Wrong reference'")
                self.assertEqual(inspect_design(browser, check)["checks"][0]["assessment"], "fail")
                observations = []
                def capture(facts, criteria, confidence):
                    observations.extend(facts)
                    return []
                with patch("jev_qa.design._review_contextual", capture):
                    inspect_design(browser, [{"id": "meaning", "kind": "contextual", "selector": "#ref",
                                              "criterion": "The text describes a reference."}])
                self.assertEqual(observations[0]["element"].get("text"), "Long native reference")

    def test_owned_browser_closes_and_removes_profile(self):
        if not os.environ.get("JEV_QA_BROWSER_TEST_CHILD"):
            result = subprocess.run(
                [sys.executable, __file__, "BrowserLifecycleTest.test_owned_browser_closes_and_removes_profile"],
                env={
                    **os.environ,
                    "JEV_QA_BROWSER_TEST_CHILD": "1",
                    "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
                },
                capture_output=True,
                text=True,
                timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return
        from jev_qa.browser import browser_session, isolated_runtime

        with isolated_runtime() as root:
            with browser_session("data:text/html,<title>QA lifecycle</title><button>Continue</button>") as browser:
                self.assertEqual(browser.evaluate("document.title"), "QA lifecycle")
                state = browser.observe(screenshot=False)
                self.assertTrue(any(a["label"] == "Continue" for a in state["actions"]))
                self.assertTrue(Path(os.environ["BH_HOME"]).is_relative_to(root))
            self.assertFalse((root / "chrome" / "SingletonLock").exists())
        self.assertFalse(root.exists())

    def test_compatibility_snapshot_names_controls_and_enforces_fresh_clicks(self):
        if not os.environ.get("JEV_QA_BROWSER_TEST_CHILD"):
            result = subprocess.run(
                [
                    sys.executable,
                    __file__,
                    "BrowserLifecycleTest.test_compatibility_snapshot_names_controls_and_enforces_fresh_clicks",
                ],
                env={
                    **os.environ,
                    "JEV_QA_BROWSER_TEST_CHILD": "1",
                    "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
                },
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return

        from jev_qa import browser as module

        html = """<!doctype html>
<dialog id="dialog" open>
  <label for="language">Preferred language <span> (optional) </span></label>
  <input id="language" type="text">
  <button id="keep" type="button" value="cancel">Keep records</button>
  <button id="delete" type="reset" value="reset">Delete demo records</button>
  <input id="submit" type="submit" value="Submit records">
  <button id="aria" type="button" value="wrong" aria-label="Accessible action">Visible text</button>
</dialog>
<script>
  document.getElementById("keep").addEventListener("click", () => document.getElementById("dialog").close());
</script>"""
        url = "data:text/html," + quote(html)
        with module.isolated_runtime():
            _, first_browser_class = module._load_harness()
            first_read_state = module.sys.modules["jev_ultrafast.browser"].READ_STATE
            first_marker = module.sys.modules["jev_ultrafast.browser"].MARKER
            _, second_browser_class = module._load_harness()
            jev_browser = module.sys.modules["jev_ultrafast.browser"]
            self.assertIs(first_browser_class, second_browser_class)
            self.assertEqual(first_read_state, jev_browser.READ_STATE)
            self.assertEqual(first_marker, jev_browser.MARKER)

            with module.browser_session(url) as browser:
                state = browser.observe(screenshot=False)
                self.assertTrue(browser.fresh(state))
                labels = {action["label"] for action in state["actions"]}
                self.assertIn("Preferred language (optional)", labels)
                self.assertIn("Keep records", labels)
                self.assertIn("Delete demo records", labels)
                self.assertIn("Submit records", labels)
                self.assertIn("Accessible action", labels)

                language = next(
                    action
                    for action in state["actions"]
                    if action["kind"] == "fill" and action["label"] == "Preferred language (optional)"
                )
                entered = "हिन्दी  value"
                self.assertEqual(browser.act(language, state, text=entered), {"executed": language["id"]})
                state = browser.observe(screenshot=False)
                self.assertEqual(browser.evaluate("document.getElementById('language').value"), entered)

                keep = next(action for action in state["actions"] if action["label"] == "Keep records")
                self.assertTrue(browser.fresh(state, keep))
                browser.evaluate("document.getElementById('keep').textContent = 'Keep records changed'")
                self.assertFalse(browser.fresh(state, keep))
                with self.assertRaisesRegex(ValueError, "changed since this decision"):
                    browser.act(keep, state)

                changed = browser.observe(screenshot=False)
                changed_keep = next(
                    action for action in changed["actions"] if action["label"] == "Keep records changed"
                )
                self.assertTrue(browser.fresh(changed, changed_keep))
                self.assertEqual(browser.act(changed_keep, changed), {"executed": changed_keep["id"]})
                self.assertFalse(browser.evaluate("document.getElementById('dialog').open"))

    def test_deadline_stops_browser_and_daemon(self):
        if not os.environ.get("JEV_QA_BROWSER_TEST_CHILD"):
            result = subprocess.run(
                [sys.executable, __file__, "BrowserLifecycleTest.test_deadline_stops_browser_and_daemon"],
                env={
                    **os.environ,
                    "JEV_QA_BROWSER_TEST_CHILD": "1",
                    "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
                },
                capture_output=True,
                text=True,
                timeout=45,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return
        from jev_qa.__main__ import deadline
        from jev_qa.browser import RunDeadline, browser_session, isolated_runtime

        with self.assertRaises(RunDeadline):
            with isolated_runtime() as root:
                with browser_session("data:text/html,<title>Timeout</title>"):
                    signal.signal(signal.SIGALRM, deadline)
                    signal.setitimer(signal.ITIMER_REAL, 0.05)
                    time.sleep(5)
        self.assertFalse(root.exists())
        processes = subprocess.check_output(["ps", "-axo", "command"], text=True)
        self.assertNotIn(str(root), processes)


if __name__ == "__main__":
    unittest.main()
