import hashlib,json,sys
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1]
root=PROJECT/'jev-design-eval-v4'
def relocated(value):
 value=str(value)
 for prefix in ('/Users/dk/Documents/Codex/2026-09-17/ok-x20/outputs/', 'outputs/'):
  if value.startswith(prefix): return PROJECT/value[len(prefix):]
 return Path(value)
accept=json.loads((root/'acceptance.json').read_text())
assert all(hashlib.sha256(relocated(f).read_bytes()).hexdigest()==h for f,h in accept['fixture_sha256'].items())
facts=[]
for argument in sys.argv[1:]:
 folder=Path(argument);rows=json.loads((folder/'results.json').read_text());protocol=json.loads((folder/'protocol.json').read_text())
 assert all(hashlib.sha256(relocated(f).read_bytes()).hexdigest()==h for f,h in protocol['source_sha256'].items()), folder
 counts={'journeys':0,'checkpoints':0,'supported_checks':0,'seeded_defects':0,'false_passes':0,'false_failures':0}
 decisions=reveals=0; models=set(); private_decisions=True
 for row in rows:
  report=row['report']; counts['journeys']+=report['navigation_status']=='pass'; counts['checkpoints']+=report['reached']
  assert not report['model_usage']['text']
  models.update(u['model'] for group in report['model_usage'].values() for u in group)
  for step in report['steps']:
   for check in step.get('design',{}).get('checks',[]):
    if check['kind'] in ('artwork','contextual'):continue
    expected=row['expected'][check['id']];actual=check['assessment']
    counts['supported_checks']+=expected==actual
    counts['seeded_defects']+=expected==actual=='fail'
    counts['false_passes']+=expected=='fail' and actual=='pass'
    counts['false_failures']+=expected=='pass' and actual=='fail'
  for tracefile in (folder/row['case']).glob('step-*/trace.jsonl'):
   events=[json.loads(s) for s in tracefile.read_text().splitlines()]
   for index,event in enumerate(events):
    if event['event']=='action_intent': assert event['confidence']>=0.8,(tracefile,event)
    if event['event']=='action_result' and str(event.get('action','')).startswith('REVEAL_'):
     reveals+=1
     tail=events[index+1:]
     next_decision=next((n for n,e in enumerate(tail) if e['event']=='decision'),None)
     if next_decision is not None: assert any(e['event']=='observe' for e in tail[:next_decision]),tracefile
  for file in (folder/row['case']).glob('step-*/decision-*.json'):
   data=json.loads(file.read_text());decisions+=1
   private_decisions = private_decisions and file.stat().st_mode & 0o777==0o600
   assert data['raw_response']['model']=='jev-1.13.0'
   assert data['decision']['decision_mode']=='target_first'
   offered=data['request']['questions']['target']['criteria'];answer=data['raw_answers']['target']
   assert set(answer['probabilities'])==set(offered)
   assert answer['choice'] in offered
   assert data['raw_response']['answers']==data['raw_answers']
   assert 'required_postconditions' in data['request']['state']
 assert models=={'jev-1.13.0'},models
 gate=accept['fresh_gate' if folder.name.startswith('fresh-') else 'regression_gate']
 facts.append({'run':str(folder),'counts':counts,'acceptance_passed':counts==gate,'decisions':decisions,'accepted_reveals':reveals,'source_hashes_match':True,'models':sorted(models),'text_helper_calls':0,'private_decisions':private_decisions})
print(json.dumps({'frozen_fixtures_match':True,'runs':facts},indent=2))
