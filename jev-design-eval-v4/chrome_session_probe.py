"""Opt-in live probe: use only a fictional local session in existing Chrome."""

import http.server
import json
import signal
import sys
import threading
from contextlib import nullcontext
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "jev-qa"))


def main():
    from jev_qa.__main__ import CONFIG, deadline, load_env
    from jev_qa.browser import browser_session, isolated_runtime

    load_env(CONFIG)
    token = uuid4().hex
    prefix = "/jev-session-" + token
    cookie = "jev_qa_session_" + token
    visits = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            if self.path not in (prefix + "/seed", prefix + "/app"):
                self.send_error(404)
                return
            seeded = self.path.endswith("/seed")
            authenticated = cookie + "=fictional" in self.headers.get("Cookie", "").split("; ")
            visits.append({"path": "seed" if seeded else "app", "authenticated": authenticated})
            self.send_response(200 if seeded or authenticated else 401)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            if seeded:
                self.send_header("Set-Cookie", f"{cookie}=fictional; Path={prefix}; HttpOnly; SameSite=Strict; Max-Age=300")
            self.end_headers()
            if seeded:
                body = "<title>Jev local session seed</title><p>Fictional session created.</p>"
            elif authenticated:
                body = '''<title>Jev local authenticated fixture</title>
                    <h1>Fictional signed-in session</h1><p id="status">Ready to verify.</p>
                    <button onclick="document.querySelector('#status').textContent='Existing session verified.'">Verify session</button>'''
            else:
                body = "<title>Unauthenticated</title><p>Session absent.</p>"
            self.wfile.write(body.encode())

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}{prefix}"
    evidence = {"scope": "fictional local HttpOnly session only; no private account pages", "visits": visits}
    signal.signal(signal.SIGALRM, deadline)
    signal.setitimer(signal.ITIMER_REAL, 60)
    try:
        with isolated_runtime():
            from jev_ultrafast.browser import Browser
            from jev_qa.journey import run_journey

            print("Connecting to existing Chrome for the local session probe.", flush=True)
            with browser_session(base + "/seed", existing=True) as seed:
                original_targets = {t["targetId"] for t in seed.call("Target.getTargets")["targetInfos"]}
                child = Browser.__new__(Browser)
                try:
                    child.__init__(base + "/app")
                    evidence["authenticated_new_tab"] = child.evaluate("document.title") == "Jev local authenticated fixture"
                    task = {"url": base + "/app", "goal": "Verify the fictional existing session.",
                        "max_steps": 5, "max_seconds": 30, "min_confidence": 0.8,
                        "steps": [{"name": "Verify", "goal": "Click Verify session.", "assertions": [
                            {"kind": "text_equals", "selector": "#status", "expected": "Existing session verified."}]}]}
                    evidence["journey"] = run_journey(task, ROOT / "existing-chrome-live", lambda _: nullcontext(child))
                finally:
                    if getattr(child, "target", None):
                        child.close()
                    seed.call("Network.deleteCookies", name=cookie, url=base + "/app", path=prefix)
                after_targets = {t["targetId"] for t in seed.call("Target.getTargets")["targetInfos"]}
                evidence["preexisting_targets_preserved_during_probe"] = original_targets <= after_targets
                evidence["probe_child_tab_closed"] = after_targets == original_targets
                evidence["cookie_cleanup_requested"] = True
        evidence["connection_closed"] = True
    except BaseException as error:
        evidence["error"] = type(error).__name__
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        server.shutdown()
        server.server_close()
        (ROOT / "existing-chrome-probe.json").write_text(json.dumps(evidence, indent=2) + "\n")
    assert evidence["authenticated_new_tab"] and evidence["journey"]["navigation_status"] == "pass", evidence
    assert evidence["probe_child_tab_closed"] and evidence["preexisting_targets_preserved_during_probe"], evidence
    print(json.dumps({k: v for k, v in evidence.items() if k != "journey"}, indent=2))


if __name__ == "__main__":
    main()
