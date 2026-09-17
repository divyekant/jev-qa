"""Frozen paired evals for the reusable Jev journey command."""
import argparse
import base64
import hashlib
import http.server
import importlib.util
import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNNER = ROOT.parent / "jev-qa"
ORIGINAL = ROOT.parent / "jev-design-eval"
sys.path.insert(0, str(RUNNER))


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        route = self.path.split("?")[0]
        paths = {"/original": ORIGINAL / "index.html", "/holdout": ROOT / "holdout/index.html"}
        if route not in paths:
            self.send_error(404)
            return
        data = paths[route].read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def preflight(task, actions, out):
    from jev_qa.browser import isolated_runtime, browser_session
    sys.path.append(str(ORIGINAL))
    spec = importlib.util.spec_from_file_location("original_eval", ORIGINAL / "evaluate.py")
    original_eval = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original_eval)
    out.mkdir(parents=True)
    result = {"steps": [], "errors": []}
    with isolated_runtime():
        from jev_qa.runner import _check_assertions
        from jev_qa.design import inspect_design
        with browser_session(task["url"]) as browser:
            browser.call("Emulation.setDeviceMetricsOverride", **task["viewport"], deviceScaleFactor=1, mobile=False)
            browser.call("Emulation.setEmulatedMedia", features=[{"name": "prefers-reduced-motion", "value": "reduce"}])
            for index, (step, action) in enumerate(zip(task["steps"], actions, strict=True)):
                original_eval.scripted_stage(browser, [(action["kind"], action["label"], action.get("value"))])
                assertions = _check_assertions(browser, step["assertions"])
                checks = [c for c in step.get("checks", []) if c["kind"] != "contextual"]
                design = inspect_design(browser, checks) if checks else {"checks": []}
                if checks:
                    capture = browser.call("Page.captureScreenshot", format="png")
                    (out / f"step-{index + 1:02d}-screen.png").write_bytes(base64.b64decode(capture["data"]))
                result["steps"].append({"name": step["name"], "assertions": assertions, "design": design})
                if not all(a["passed"] for a in assertions):
                    result["errors"].append("Assertion failed: " + step["name"])
                    break
            result["oracle"] = browser.evaluate("({testState:window.testState||null,reservation:window.reservation||null,eventLog:window.eventLog||null})")
    save(out / "report.json", result)


def run(args):
    cases = json.loads((ROOT / "original-cases.json").read_text())
    truth = json.loads((ROOT / "original-truth.json").read_text())
    cases += json.loads((ROOT / "holdout/cases.json").read_text())
    truth.update(json.loads((ROOT / "holdout/truth.json").read_text()))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    out = ROOT / "runs" / (("preflight-" if args.preflight else "live-") + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    out.mkdir(parents=True)
    sources = [p for p in ROOT.glob("*.json")] + list((ROOT / "holdout").glob("*"))
    sources += [ORIGINAL / "index.html", Path(__file__).resolve()] + list((RUNNER / "jev_qa").glob("*.py")) + list((RUNNER / "jev_qa").glob("*.js"))
    save(out / "protocol.json", {"attempts_per_case": 1, "confidence": 0.8, "cases": cases, "expected": truth,
        "routing": "Jev-only actions and contextual assessment; deterministic measurements authoritative",
        "source_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources if p.is_file()}})
    results = []
    try:
        for case in cases:
            original = case["name"].startswith("original-")
            task = {**case["task"], "url": f"http://127.0.0.1:{server.server_port}/{'original' if original else 'holdout'}?build={case['build']}",
                "viewport": {"width": case["width"], "height": case["height"]}, "max_steps": 60, "max_seconds": 180, "min_confidence": 0.8}
            task_path = out / (case["name"] + "-task.json")
            save(task_path, task)
            folder = out / case["name"]
            if args.preflight:
                actions = ROOT / ("original-preflight.json" if original else "holdout/preflight.json")
                command = [sys.executable, str(Path(__file__).resolve()), "--preflight-case", str(task_path), "--actions", str(actions), "--output", str(folder)]
            else:
                command = [str(RUNNER / "jev-qa"), "journey", str(task_path), "--output", str(folder)]
            started = time.perf_counter()
            try:
                completed = subprocess.run(command, capture_output=True, text=True, timeout=210)
                exit_code, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
            except (subprocess.TimeoutExpired, OSError) as error:
                exit_code, stdout, stderr = 2, "", type(error).__name__
            (out / (case["name"] + "-stdout.txt")).write_text(stdout)
            (out / (case["name"] + "-stderr.txt")).write_text(stderr)
            path = folder / "report.json"
            report = json.loads(path.read_text()) if path.exists() else {"status": "error", "steps": []}
            actual = {c["id"]: c["assessment"] for s in report["steps"] for c in s.get("design", {}).get("checks", [])}
            expected = truth[case["name"]]
            if args.preflight:
                context_ids = {c["id"] for s in task["steps"] for c in s.get("checks", []) if c["kind"] == "contextual"}
                expected = {k: v for k, v in expected.items() if k not in context_ids}
            result = {"case": case["name"], "wall_ms": round((time.perf_counter()-started)*1000),
                "exit_code": exit_code, "actual": actual, "expected": expected,
                "score": {"correct": sum(actual.get(k, "not_reached") == v for k,v in expected.items()), "total": len(expected),
                          "missed_defects": sum(v == "fail" and actual.get(k) != "fail" for k,v in expected.items()),
                          "false_passes": sum(v == "fail" and actual.get(k) == "pass" for k,v in expected.items())},
                "report": report}
            results.append(result)
            save(out / "results.json", results)
            print(json.dumps({k: result[k] for k in ("case", "wall_ms", "exit_code", "score", "actual")}), flush=True)
    finally:
        server.shutdown()
        server.server_close()
    print(str(out), flush=True)
    if args.preflight and any(r["exit_code"] != 0 or r["score"]["correct"] != r["score"]["total"] or r["report"].get("errors") for r in results):
        raise SystemExit("Preflight failed; do not run paid evaluation")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--preflight-case", type=Path)
    parser.add_argument("--actions", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.preflight_case:
        from jev_qa.__main__ import deadline
        signal.signal(signal.SIGALRM, deadline)
        signal.alarm(90)
        preflight(json.loads(args.preflight_case.read_text()), json.loads(args.actions.read_text()), args.output)
    else:
        run(args)
