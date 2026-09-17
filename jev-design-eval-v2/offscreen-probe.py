import json
from urllib.parse import quote

from jev_qa.browser import browser_session, isolated_runtime

html = '''<!doctype html>
<meta charset="utf-8">
<style>
  body { margin: 0; min-height: 2200px; }
  .below { position: absolute; top: 1000px; left: 10px; }
  .above { position: absolute; top: -100px; left: 10px; }
</style>
<button id="valid" class="below">Inspect session</button>
<button id="hidden-visibility" class="below" style="visibility:hidden">Visibility hidden</button>
<button id="hidden-opacity" class="below" style="opacity:0">Opacity hidden</button>
<div aria-hidden="true"><button id="hidden-ancestor" class="below">Hidden ancestor</button></div>
<button id="disabled" class="below" disabled>Disabled</button>
<input id="password" class="below" type="password" aria-label="Password">
<input id="hidden-input" class="below" type="hidden" value="secret">
<button id="above" class="above">Above button</button>
'''
url = 'data:text/html,' + quote(html, safe='')

with isolated_runtime():
    from jev_qa import runner
    with browser_session(url) as browser:
        initial = browser.observe(screenshot=False)
        context = runner._offscreen_page(browser, initial)
        collector = browser.evaluate(runner._OFFSCREEN_JS)
        initial_ids = [action['id'] for action in initial['actions']]
        below_labels = [action['label'] for action in initial['actions'] if action['kind'] == 'scroll']
        result = {
            'initial_scroll_actions': initial_ids,
            'initial_context_text': context['text'],
            'collector': collector,
            'initial_has_valid_action': any(action.get('label') == 'Inspect session' for action in initial['actions']),
            'initial_has_scroll': 'scroll_down' in initial_ids,
        }
        scroll = next(action for action in initial['actions'] if action['id'] == 'scroll_down')
        browser.act(scroll, initial)
        after = browser.observe(screenshot=False)
        after_context = runner._offscreen_page(browser, after)
        result.update({
            'after_actions': after['actions'],
            'after_context_text': after_context['text'],
            'after_has_valid_action': any(action.get('label') == 'Inspect session' for action in after['actions']),
            'after_has_scroll': 'scroll_down' in [action['id'] for action in after['actions']],
        })
        print(json.dumps(result, indent=2))
