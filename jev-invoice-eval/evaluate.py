"""One live creation task followed by clean and seeded-defect browser QA."""

import functools
import hashlib
import html
import http.server
import json
import subprocess
import threading
import time
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNNER = ROOT.parent / "jev-qa"
EXPECTED = {"customer": "Ada Example", "email": "ada@example.com", "quantity": 3,
            "unit_cents": 1995, "total_cents": 5985, "status": "Draft", "payment": "Unpaid"}
CRITERIA = [
    "The invoice identifies customer Ada Example and email ada@example.com.",
    "The invoice has quantity 3 at unit price $19.95 and shows the mathematically correct total $59.85.",
    "The invoice remains Draft and Unpaid.",
]
state = {"records": [], "submissions": 0}


def save(name, value):
    (ROOT / name).write_text(json.dumps(value, indent=2) + "\n")


FORM = """<!doctype html><html lang="en"><title>Create draft invoice</title>
<style>body{font:18px system-ui;max-width:700px;margin:40px auto}label,input,button{display:block;margin:12px 0}input,button{font:inherit;padding:8px}</style>
<h1>Create draft invoice</h1><p>Local fictional records only. Saving does not send an invoice.</p>
<form><label>Customer name<input name="customer" required></label>
<label>Customer email<input name="email" type="email" required></label>
<label>Quantity<input name="quantity" type="number" min="1" required></label>
<label>Unit price<input name="unit_price" type="number" min="0" step="0.01" required></label>
<button>Save draft</button></form><p id="status" role="status">No draft saved.</p>
<script>document.querySelector('form').onsubmit=async e=>{e.preventDefault();
const r=await fetch('/records',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify(Object.fromEntries(new FormData(e.target)))});
if(r.ok){location.href='/invoice/a'}else{document.querySelector('#status').textContent='Could not save draft.'}};</script></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, body, content_type="text/html", status=200):
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            return self.respond(FORM)
        if self.path in ("/invoice/a", "/invoice/b") and state["records"]:
            record = state["records"][-1]
            displayed_total = record["total_cents"] + (1000 if self.path.endswith("/b") else 0)
            fields = {**record, "unit_price": f"${record['unit_cents']/100:.2f}",
                      "total": f"${displayed_total/100:.2f}"}
            rows = "".join(f'<dt>{label}</dt><dd id="{key}">{html.escape(str(fields[key]))}</dd>' for key, label in
                           [("customer", "Customer"), ("email", "Email"), ("quantity", "Quantity"),
                            ("unit_price", "Unit price"), ("total", "Total"), ("status", "Status"), ("payment", "Payment")])
            return self.respond('<!doctype html><html lang="en"><title>Draft invoice</title>'
                                '<style>body{font:20px system-ui;max-width:700px;margin:40px auto}dt{font-weight:bold;margin-top:18px}dd{margin:4px 0}</style>'
                                '<h1>Draft invoice</h1><p id="saved">Draft saved.</p><dl>' + rows + '</dl></html>')
        self.respond("Not found", status=404)

    def do_POST(self):
        if self.path != "/records":
            return self.respond("Not found", status=404)
        state["submissions"] += 1
        try:
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            record = {"customer": data["customer"], "email": data["email"], "quantity": int(data["quantity"]),
                      "unit_cents": int(Decimal(data["unit_price"]) * 100), "status": "Draft", "payment": "Unpaid"}
            record["total_cents"] = record["quantity"] * record["unit_cents"]
            state["records"].append(record)
            save("server-state.json", state)
            self.respond(json.dumps(record), "application/json")
        except (ValueError, KeyError, TypeError):
            self.respond("Invalid form", status=400)


def assertions():
    return [{"kind": "text_equals", "selector": "#" + key, "expected": value} for key, value in
            {"customer": "Ada Example", "email": "ada@example.com", "quantity": "3", "unit_price": "$19.95",
             "total": "$59.85", "status": "Draft", "payment": "Unpaid"}.items()]


def run(name, task):
    save(name + "-task.json", task)
    print("Starting " + name, flush=True)
    started = time.perf_counter()
    completed = subprocess.run([str(RUNNER / "jev-qa"), "run", str(ROOT / (name + "-task.json")),
                                "--output", str(ROOT / name)], capture_output=True, text=True, timeout=110)
    elapsed = round((time.perf_counter() - started) * 1000)
    (ROOT / (name + "-stdout.json")).write_text(completed.stdout)
    (ROOT / (name + "-stderr.txt")).write_text(completed.stderr)
    report = json.loads((ROOT / name / "report.json").read_text())
    calls = [call for group in report.get("model_usage", {}).values() for call in group]
    metrics = {"status": report["status"], "exit_code": completed.returncode, "wall_ms": elapsed,
               "runner_ms": report.get("elapsed_ms"), "model_latency_ms": sum(c["latency_ms"] for c in calls),
               "model_responses": len(calls), "input_tokens": sum(c["usage"]["input_tokens"] for c in calls),
               "output_tokens": sum(c["usage"]["output_tokens"] for c in calls),
               "models": sorted({c["model"] for c in calls}), "actions": len(report.get("actions", []))}
    print(json.dumps({name: metrics}), flush=True)
    return report, metrics


def main():
    # Freeze task, known answers, limits and source hashes before any model request.
    if (ROOT / "protocol.json").exists():
        raise SystemExit("Use a fresh output directory; never overwrite an eval run.")
    save("protocol.json", {"case": "Create and audit a fictional draft invoice", "expected_record": EXPECTED,
         "criteria": CRITERIA, "expected_qa": {"qa-a": ["pass", "pass", "pass"], "qa-b": ["pass", "fail", "pass"]},
         "seeded_defect": "View b adds $10.00 to displayed total; stored record remains unchanged.",
         "attempts_per_stage": 1, "max_steps": 12, "max_seconds": 90, "min_confidence": 0.8,
         "scope": "Live installed runner. Native Codex role dispatch is outside this eval.",
         "source_sha256": {str(p.relative_to(ROOT.parent)): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in [Path(__file__), *sorted((RUNNER / "jev_qa").glob("*.py"))]}})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}"
    results = {}
    try:
        task = {"url": url + "/", "goal": "Create exactly one draft invoice for Ada Example, email ada@example.com, "
                "quantity 3, unit price 19.95. Fill all four fields, click Save draft once, then stop when the saved invoice appears. "
                "Keep it Draft and Unpaid. Do not send it.",
                "values": {"Customer name": "Ada Example", "Customer email": "ada@example.com", "Quantity": "3", "Unit price": "19.95"},
                "assertions": assertions(), "max_steps": 12, "max_seconds": 90, "min_confidence": 0.8}
        report, results["create"] = run("create", task)
        oracle = {"single_submission": state["submissions"] == 1, "single_record": len(state["records"]) == 1,
                  "fields": {key: len(state["records"]) == 1 and state["records"][0].get(key) == value
                             for key, value in EXPECTED.items()}}
        oracle["pass"] = oracle["single_submission"] and oracle["single_record"] and all(oracle["fields"].values())
        save("creation-oracle.json", oracle)
        if not oracle["pass"]:
            save("results.json", {"stages": results, "oracle": oracle, "qa": "Not run: creation precondition failed."})
            return
        scored = {}
        for view, expected in [("a", ["pass", "pass", "pass"]), ("b", ["pass", "fail", "pass"])]:
            name = "qa-" + view
            report, results[name] = run(name, {"url": url + "/invoice/" + view, "mode": "check",
                "assertions": assertions(), "criteria": CRITERIA, "max_seconds": 90, "min_confidence": 0.8})
            actual = [j["assessment"] for j in report.get("judgments", [])]
            scored[name] = {"expected_judgments": expected, "actual_judgments": actual,
                           "correct": sum(a == b for a, b in zip(actual, expected)), "total": len(expected),
                           "overall_status_correct": report["status"] == ("pass" if view == "a" else "fail"),
                           "failed_assertions": [a["selector"] for a in report["assertions"] if not a["passed"]]}
        save("results.json", {"stages": results, "oracle": oracle, "qa_scores": scored,
            "totals": {key: sum(stage[key] for stage in results.values()) for key in
                       ("wall_ms", "model_latency_ms", "model_responses", "input_tokens", "output_tokens")},
            "limitations": ["One attempt per stage; no estimate of general accuracy or repeatability.",
                            "QA sees browser text, not source or expected result labels.",
                            "Model judgments are scored separately from deterministic assertions.",
                            "Usage is provider-reported Jev usage, excluding parent orchestration tokens and any unreported failed requests.",
                            "Wall time includes launcher and browser setup; no native subagent dispatch measured."]})
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
