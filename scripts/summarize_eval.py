import json
import statistics
import sys
from pathlib import Path

folder = Path(sys.argv[1])
rows = json.loads((folder / 'results.json').read_text())
cases = []
for row in rows:
    report = row['report']
    checks = {c['id']: c for s in report['steps'] for c in s.get('design', {}).get('checks', [])}
    uses = [u for values in report['model_usage'].values() for u in values]
    assert not report['model_usage']['text']
    assert all(u['model'].startswith('jev-') for u in uses)
    counts = {}
    for kind in ('rule', 'artwork', 'contextual'):
        selected = {k: v for k, v in row['expected'].items()
                    if ('artwork' if checks[k]['kind'] == 'artwork' else 'contextual'
                        if checks[k]['kind'] == 'contextual' else 'rule') == kind}
        counts[kind] = {'correct': sum(row['actual'].get(k) == v for k, v in selected.items()),
                        'total': len(selected)}
    cases.append({'case': row['case'], 'status': report['status'], 'navigation': report['navigation_status'],
        'steps': report['reached'], 'steps_total': report['total'], 'actions': report['actions'],
        'score': row['score'], 'groups': counts, 'runner_ms': report['elapsed_ms'],
        'process_ms': row['wall_ms'], 'api_ms': sum(u['latency_ms'] for u in uses),
        'calls': len(uses), 'input_tokens': sum(u['usage']['input_tokens'] for u in uses),
        'output_tokens': sum(u['usage']['output_tokens'] for u in uses),
        'models': sorted({u['model'] for u in uses})})
totals = {k: sum(c[k] for c in cases) for k in ('steps', 'steps_total', 'actions', 'runner_ms',
          'process_ms', 'api_ms', 'calls', 'input_tokens', 'output_tokens')}
totals['journeys_completed'] = sum(c['navigation'] == 'pass' for c in cases)
totals['journeys_total'] = len(cases)
totals['median_process_ms'] = statistics.median(c['process_ms'] for c in cases)
totals['groups'] = {g: {k: sum(c['groups'][g][k] for c in cases) for k in ('correct', 'total')}
                   for g in ('rule', 'artwork', 'contextual')}
totals['score'] = {k: sum(c['score'][k] for c in cases) for k in cases[0]['score']}
print(json.dumps({'run': str(folder), 'totals': totals, 'cases': cases}, indent=2))
