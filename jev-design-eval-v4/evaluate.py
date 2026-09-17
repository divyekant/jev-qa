"""Frozen regression and fresh-page evaluations. Each case owns one CLI process."""
import argparse
import base64
import hashlib
import http.server
import json
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNNER = ROOT.parent / 'jev-qa'
V2 = ROOT.parent / 'jev-design-eval-v2'
PAGES = {'original': ROOT.parent / 'jev-design-eval/index.html', 'holdout': V2 / 'holdout/index.html', 'fresh': ROOT / 'fresh/index.html'}
sys.path.insert(0, str(RUNNER))


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def preflight(task, instructions, output):
    from jev_qa.browser import browser_session, isolated_runtime
    output.mkdir(parents=True)
    report = {'steps': [], 'errors': []}
    with isolated_runtime():
        from jev_qa.runner import _check_assertions
        from jev_qa.design import inspect_design
        with browser_session(task['url']) as browser:
            browser.call('Emulation.setDeviceMetricsOverride', **task['viewport'], deviceScaleFactor=1, mobile=False)
            for index, (step, command) in enumerate(zip(task['steps'], instructions, strict=True)):
                # Independent fixture oracle only. Paid runs never use this scripted visibility/action path.
                browser.evaluate('document.querySelector(' + json.dumps(command['selector']) + ').scrollIntoView({block:"center"})')
                page = browser.observe(screenshot=False)
                candidates = [a for a in page['actions'] if a['kind'] == command['kind'] and (
                    a['label'] == command['label'] if command['kind'] != 'select' else
                    a['label'].startswith(command['label'] + ' → ') and a.get('value') == command['value'])]
                if len(candidates) != 1:
                    raise ValueError('Preflight action unavailable: ' + command['label'])
                browser.act(candidates[0], page, text=command.get('value') if command['kind'] == 'fill' else None)
                browser.observe(screenshot=False)
                checks = [c for c in step['checks'] if c['kind'] != 'contextual']
                measured = inspect_design(browser, checks) if checks else {'checks': []}
                assertions = _check_assertions(browser, step['assertions'])
                report['steps'].append({'name': step['name'], 'assertions': assertions, 'design': measured})
                if checks:
                    image = browser.call('Page.captureScreenshot', format='png')['data']
                    (output / f'step-{index + 1:02d}.png').write_bytes(base64.b64decode(image))
                if not all(a['passed'] for a in assertions):
                    report['errors'].append('Failed assertion: ' + step['name'])
                    break
    save(output / 'report.json', report)


def main(args):
    if args.preflight_case:
        from jev_qa.__main__ import deadline
        signal.signal(signal.SIGALRM, deadline)
        signal.alarm(90)
        preflight(json.loads(args.preflight_case.read_text()), json.loads((ROOT/'fresh/preflight.json').read_text()), args.output)
        return
    cases, truth = [], {}
    suites = [('original', V2/'original-cases.json', V2/'original-truth.json'), ('holdout', V2/'holdout/cases.json', V2/'holdout/truth.json')]
    if args.suite == 'fresh':
        suites = [('fresh', ROOT/'fresh/cases.json', ROOT/'fresh/truth.json')]
    for page, case_file, truth_file in suites:
        cases += [{**c, 'page': page} for c in json.loads(case_file.read_text())]
        truth.update(json.loads(truth_file.read_text()))
    if args.case:
        unknown = set(args.case) - {c['name'] for c in cases}
        if unknown:
            raise ValueError('Unknown case name')
        cases = [c for c in cases if c['name'] in args.case]
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_GET(self):
            path = self.path.split('?')[0].lstrip('/')
            if path not in PAGES:
                self.send_error(404)
                return
            content = PAGES[path].read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    label = 'preflight' if args.preflight else args.suite
    output = ROOT/'runs'/(label + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    output.mkdir(parents=True)
    sources = [Path(__file__), *PAGES.values(), *(RUNNER/'jev_qa').glob('*.py'), *(RUNNER/'jev_qa').glob('*.js')]
    sources += [p for _, a, b in suites for p in (a, b)]
    save(output/'protocol.json', {'attempts_per_case':1, 'confidence':0.8, 'max_steps':60, 'max_seconds':180,
         'cases':cases, 'expected':truth, 'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}})
    rows=[]
    try:
        for case in cases:
            task={**case['task'], 'url':f"http://127.0.0.1:{server.server_port}/{case['page']}?build={case['build']}",
                'viewport':{'width':case['width'], 'height':case['height']}, 'max_steps':60, 'max_seconds':180, 'min_confidence':0.8}
            task_file=output/(case['name']+'-task.json'); save(task_file,task)
            destination=output/case['name']
            command=([sys.executable,str(Path(__file__)),'--preflight-case',str(task_file),'--output',str(destination)] if args.preflight else
                     [str(RUNNER/'jev-qa'),'journey',str(task_file),'--output',str(destination)])
            started=time.perf_counter()
            try:
                process=subprocess.run(command,capture_output=True,text=True,timeout=210)
                code,stdout,stderr=process.returncode,process.stdout,process.stderr
            except (subprocess.TimeoutExpired,OSError) as error:
                code,stdout,stderr=2,'',type(error).__name__
            elapsed=round((time.perf_counter()-started)*1000)
            (output/(case['name']+'-stdout.txt')).write_text(stdout)
            (output/(case['name']+'-stderr.txt')).write_text(stderr)
            report=json.loads((destination/'report.json').read_text()) if (destination/'report.json').exists() else {'status':'error','steps':[]}
            actual={c['id']:c['assessment'] for s in report['steps'] for c in s.get('design',{}).get('checks',[])}
            expected=truth[case['name']]
            if args.preflight:
                expected={k:v for k,v in expected.items() if k not in {c['id'] for s in task['steps'] for c in s['checks'] if c['kind']=='contextual'}}
            row={'case':case['name'],'wall_ms':elapsed,'exit_code':code,'actual':actual,'expected':expected,'report':report,
                 'score':{'correct':sum(actual.get(k)==v for k,v in expected.items()),'total':len(expected),
                          'missed_defects':sum(v=='fail' and actual.get(k)!='fail' for k,v in expected.items()),
                          'false_passes':sum(v=='fail' and actual.get(k)=='pass' for k,v in expected.items())}}
            rows.append(row);save(output/'results.json',rows)
            print(json.dumps({k:row[k] for k in ('case','wall_ms','exit_code','score')}),flush=True)
    finally:
        server.shutdown();server.server_close()
    print(output,flush=True)
    if args.preflight and any(r['exit_code'] or r['score']['correct']!=r['score']['total'] or r['report'].get('errors') for r in rows):
        raise SystemExit('Fixture preflight failed; paid fresh evaluation is not valid.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite',choices=['regression','fresh'],default='regression')
    parser.add_argument('--preflight',action='store_true')
    parser.add_argument('--case',action='append',help='Bounded development probe; omit for final gate')
    parser.add_argument('--preflight-case',type=Path)
    parser.add_argument('--output',type=Path)
    options=parser.parse_args()
    if options.preflight and options.suite!='fresh':parser.error('Use the existing v2 preflight for regression fixtures.')
    main(options)
