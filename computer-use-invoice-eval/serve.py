import http.server, json, runpy
from pathlib import Path
root = Path(__file__).resolve().parent
module = runpy.run_path(str(root.parent / "jev-invoice-eval/evaluate.py"), run_name="fixture")
module["Handler"].do_POST.__globals__["ROOT"] = root
server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), module["Handler"])
(root / "server.json").write_text(json.dumps({"url": f"http://127.0.0.1:{server.server_port}", "records_at_start": 0}))
print(f"http://127.0.0.1:{server.server_port}", flush=True)
try:
    server.serve_forever()
finally:
    server.server_close()
