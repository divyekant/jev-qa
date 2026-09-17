# Jev QA

A browser QA worker and structured evidence reviewer. Jev selects actions and evaluates
supplied criteria. Deterministic assertions verify observable outcomes. A model's `DONE`
decision never proves a test passed.

By default, the browser runs in a disposable, headless Chrome profile with no personal
cookies or signed-in sessions. Each invocation owns and closes that browser and its
Browser Harness process. An explicit existing-Chrome mode can reuse your logged-in profile
through an owned temporary tab. Use only authorized targets and actions.

Read [the walkthrough](WALKTHROUGH.md) for the complete flow and Jev's role.

## Run

The global command is `/Users/dk/.local/bin/jev-qa`.

```sh
jev-qa doctor
jev-qa run task.json --output work/qa-result
jev-qa journey journey.json --output work/journey-result
jev-qa journey journey.json --browser existing-chrome --output work/signed-in-result
jev-qa review evidence.json --output work/qa-review
```

Output directories must be new. Browser runs save `report.json`, `trace.jsonl`, private
`decision-NNN.json` request/response evidence, and a final screenshot when available. Treat evidence as private: it can contain page content and form
values. Model input goes to TypeSafe. Journeys permit only Jev model calls. Legacy standalone
tasks must explicitly set `jev_only: false` to allow the optional text helper.

## Existing logged-in Chrome

`--browser existing-chrome` is available on `run` and `journey`. It connects to running
Google Chrome on this Mac and opens a new test tab in the connected browser profile.
It does not export cookies, copy your profile, restart Chrome, or take over an existing tab.
Existing tabs remain open. Cleanup closes only owned test/connection tabs and the private
Browser Harness process; it does not terminate your Chrome.

An independent Chrome connection closes explicitly recorded owned tabs if the daemon
crashes. If Chrome becomes unreachable or startup fails before the daemon reports its
tab ID, cleanup can remain incomplete. That condition is reported, including alongside
an original execution error. The runner never guesses ownership from new tabs.

Enable remote debugging at `chrome://inspect/#remote-debugging` and allow the connection
when Chrome asks. The runner cannot bypass that browser permission. Chrome's default
profile endpoint must be available; arbitrary remote endpoints and profile selection are
not exposed by this option. A new tab shares eligible cookies/local storage but does not
inherit another tab's unsaved forms or tab-specific session storage.

Page text and observed controls from the authorized target go to TypeSafe. This option
does not authorize real submissions, purchases, deletions, or messages outside your task.

## Codex subagent

The skill is installed at `~/.codex/skills/jev-qa/SKILL.md`. Ask:
“Use $jev-qa to test this local page against these expected outcomes.”

The native role at `~/.codex/agents/jev-qa.toml` is named `jev_qa` and pins
`gpt-5.6-luna` with low reasoning. Load a fresh session to discover the role. When that
role is unavailable in an existing session, the skill requests a Luna subagent explicitly,
with no inherited conversation. The wrapper launches one command and summarizes saved
evidence; it does not choose actions or replace Jev judgments. Wrapper usage is separate.

## Verified journeys: UAT and design QA

Current v4 evidence: three unchanged eight-case regression runs completed 24/24 journeys.
A fresh application completed another 4/4 journeys. Across those runs, all 304 checkpoints
completed, 224/224 supported checks matched their expected results, and all 48 seeded-defect
instances were detected. These are bounded synthetic tests, not a general reliability rate.
See the [v4 evaluation](../jev-design-eval-v4/REPORT.md).

UAT means user acceptance testing. Supply one current objective and a meaningful
postcondition per step. Assertions are checked before and after actions, so a verified
step can finish without an extra model DONE decision. Progress is fed into the next
objective together with confirmed action history and current assertion results. Jev makes
one target choice across eligible visible and offscreen controls, plus WAIT/DONE/ABSTAIN.
Code maps that choice to the observed interaction. Jev can select a finite `REVEAL` action
for an observed offscreen control. Code scrolls at most one viewport, then observes again;
a separate guarded click is still required. One low-confidence decision can refresh and
retry; uncertain mutations cannot.

```json
{
  "url": "http://127.0.0.1:8769/form.html",
  "goal": "Subscribe a fictional tester and inspect the result.",
  "values": {"Email": "tester@example.com"},
  "viewport": {"width": 390, "height": 844},
  "max_steps": 20,
  "max_seconds": 120,
  "min_confidence": 0.8,
  "steps": [
    {
      "name": "Email entered",
      "goal": "Enter tester@example.com in Email.",
      "assertions": [
        {"kind": "value_equals", "selector": "#email", "expected": "tester@example.com"}
      ]
    },
    {
      "name": "Subscription saved",
      "goal": "Click Subscribe.",
      "assertions": [
        {"kind": "text_equals", "selector": "#status", "expected": "Subscription saved."}
      ],
      "checks": [
        {"id": "message-readable", "kind": "unclipped", "selector": "#status"},
        {"id": "page-width", "kind": "horizontal_fit"}
      ]
    }
  ]
}
```

Steps accept `name`, `goal`, `assertions`, and optional `checks`. Known input values use
exact observed field labels. No model generates selectors or executable scripts. The
parent supplies the test contract; the runner selects observed actions to satisfy it.
Navigation stops on an unverified step. A measured design defect is recorded without
preventing later authorized navigation. Later unperformed steps remain `not_reached`.

Design checks are explicit requirements, not an automatic full-page audit:

| Kind | Fields beyond `id` and `kind` | Requirement |
|---|---|---|
| `unclipped` | `selector` | Text fits its visible clipping bounds |
| `contrast` | `selector`, optional `min_ratio` (4.5) | Supported solid-background text contrast |
| `disabled` | `selector` | Control is genuinely disabled |
| `aligned` | `selector`, `other`, optional `tolerance` (2 px) | Left edges and widths match |
| `unobstructed` | `selector` | Nine visible interior points receive pointer hits |
| `horizontal_fit` | optional `tolerance` (1 px) | Document fits the viewport width |
| `ellipsis` | `selector` | Truncated reference exposes exactly the full native title |
| `decorative_overlap` | `selector`, `decorative`, `content` | Badge may overlap decoration but not meaningful content |
| `artwork` | `selector` | Always unsupported without pixel evidence |
| `contextual` | `selector`, `criterion` | Jev assesses compact observed text and facts |

Rules keep both their passes and failures. Jev does not override deterministic results.
Contextual assessments are advisory and cannot create a verified overall pass. Unsupported
measurements remain uncertain. An uncertain artwork check therefore leaves the overall
design status at `needs_review`, even when every supported check passed.

The top-level `report.json` separates `navigation_status` and `design_status`, keeps all
steps in the denominator, and aggregates provider usage. Step folders retain navigation
traces, assertions, final screenshots, and optional `design.json`. Screenshots are saved
for independent inspection; Jev does not receive them. Whole-journey action/time budgets
include all steps and recovery calls.

## Browser task

```json
{
  "url": "http://127.0.0.1:8769/form.html",
  "goal": "Enter tester@example.com in Email, click Subscribe, then stop.",
  "values": {"Email": "tester@example.com"},
  "assertions": [
    {"kind": "value_equals", "selector": "#email", "expected": "tester@example.com"},
    {"kind": "text_equals", "selector": "#status", "expected": "Subscription saved."}
  ],
  "criteria": ["The submission response clearly confirms success."],
  "max_steps": 20,
  "max_seconds": 120,
  "min_confidence": 0.8
}
```

Use `"mode": "check"` to inspect a page without executing actions. With only deterministic
assertions, check mode needs no model call. Assertion kinds are `text_contains`, `text_equals`,
`value_equals`, `checked`, `visible`, and `url_equals`. Selector assertions require one matching
element. Supply selectors yourself; Jev cannot generate executable code or selectors.
Use boolean `expected` for `checked` and `visible`, and strings for other kinds.

Known input values use exact field labels. If a value is missing, an optional text helper can
generate it; without that helper the run returns for review. Passwords are not supported.

## Evidence review

```json
{
  "evidence": {
    "requirement": "Reject empty email addresses.",
    "input": {"email": ""},
    "observed_response": "Subscription saved."
  },
  "criteria": ["The observed behavior meets the stated requirement."]
}
```

This returns structured judgments and probabilities, not a general code review or prose
explanation. Model-only conclusions require review. They cannot produce a verified pass.

## Results

- `pass`: run completed, at least one deterministic assertion passed, all assertions passed,
  and any requested model criteria passed the confidence threshold.
- `fail`: an executed design check or a completed task assertion failed. An unmet goal
  during blocked navigation does not establish a product defect.
- `needs_review`: insufficient evidence, uncertain judgments, model-only conclusions, or missing input.
- `blocked`: a journey could not establish the next required outcome. Later checks remain
  `not_reached`. Individual task reports use `execution_status: blocked` and
  `product_status: not_tested`, with overall `needs_review`.
- `error`: execution or a dependency failed.

Command exit codes: `0` for pass, `1` for fail, `2` for all other outcomes.
Reports retain provider usage and elapsed time. Decision evidence preserves the full
request body and returned probabilities; configured credentials and authentication fields
are removed, and any redaction is marked. Evidence files use owner-only permissions. Token counts are not a bill, and confidence
is not an established accuracy rate for your application.

## Credentials

The launcher reads `~/.config/jev-qa/env` with mode `600`. Existing environment variables
take precedence. Use `--env-file /private/path` before the command to select another file.

```sh
jev-qa --env-file /private/path run task.json --output work/result
```

The required setting for Jev calls is `TYPESAFE_API_KEY`. Optional settings are `TYPESAFE_MODEL`,
`TEXT_MODEL_API_KEY`, `TEXT_MODEL_BASE_URL`, `TEXT_MODEL`, `TEXT_MODEL_REASONING`, and
`JEV_QA_CHROME`. No credential is stored in this source directory or agent configuration.
Other projects can load the same private environment file explicitly, for example with
`uv run --env-file ~/.config/jev-qa/env ...`.

## Local example

From this directory, serve the fixture in one terminal:

```sh
python3 -m http.server 8769 --bind 127.0.0.1 --directory examples
```

Then run `jev-qa run examples/empty-form.json --output work/empty-form` or the
`examples/filled-form.json` task. The fixture sends no requests and uses fictional data.
Adding `?broken=1` to the fixture URL deliberately removes required-field validation.
The same empty-form assertion must then fail.

## Limits

The pinned upstream reader supports common HTML/ARIA controls. Frames, shadow DOM, canvas,
uploads, pop-up tabs, and some custom controls are outside its scope. This does not replace
visual layout review. Origin changes stop further model-driven work after navigation; this
is not a network sandbox. Same-origin actions can still change server state.
Offscreen recovery scrolls the document; dedicated nested-container scrolling is unsupported.

Deadlines include browser setup. In-flight operations can be interrupted; they are never
automatically replayed. Cleanup can add several seconds after a timeout. An uncertain
mutation must be inspected before another run.

See [VALIDATION.md](VALIDATION.md) for live trial outcomes and verification limits.

## Development

```sh
uv sync --frozen
PYTHONPATH=. uv run --frozen python -m unittest discover -s tests -v
uv build
```

Tests use controlled model responses; the browser lifecycle check opens local `data:` HTML
without model calls. Live examples make paid API calls. Source dependency:
[Browser Use jev-ultrafast](https://github.com/browser-use/jev-ultrafast), pinned at
`452c1ad2dd628008f1d5608f28158d76e49e6cc0` (MIT). The wrapper uses its observation,
action execution, and typed decision helpers without modifying upstream.
