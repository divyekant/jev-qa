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
values. Model input goes to TypeSafe. A `visual` check also sends a screenshot to TypeSafe.
Use `visual` checks only on pages whose pixels you are allowed to share. Journeys permit only Jev model calls. Legacy standalone
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
observed field labels with whitespace normalized. No model generates selectors or executable scripts. The
parent supplies the test contract; the runner selects observed actions to satisfy it.
Navigation stops on an unverified step. A measured design defect is recorded without
preventing later authorized navigation. Later unperformed steps remain `not_reached`.

Design checks are explicit requirements. The `audit` kind adds a rule-based sweep of a page or component.

| Kind | Fields beyond `id` and `kind` | Requirement |
|---|---|---|
| `unclipped` | `selector` | Text fits its visible clipping bounds |
| `contrast` | `selector`, optional `min_ratio` (4.5) | Supported solid-background text contrast |
| `disabled` | `selector` | Control is genuinely disabled |
| `aligned` | `selector`, `other`, optional `tolerance` (2 px) | Left edges and widths match |
| `unobstructed` | `selector` | Nine visible interior points receive pointer hits |
| `horizontal_fit` | optional `tolerance` (1 px) | Document fits the viewport width |
| `image_contained` | `selector`, `container`, optional `tolerance` (1 px) | Visible image content stays inside the named ancestor container |
| `image_crop` | `selector`, `expected` (`full` or `allowed`), optional `tolerance` (1 px) | Full image content is visible, or measured cropping is explicitly allowed |
| `ellipsis` | `selector` | Truncated reference exposes exactly the full native title |
| `decorative_overlap` | `selector`, `decorative`, `content` | Badge may overlap decoration but not meaningful content |
| `artwork` | `selector` | Always unsupported. Use `visual` with a criterion to have Jev assess artwork |
| `contextual` | `selector`, `criterion` | Jev assesses compact observed text and facts |
| `visual` | `criterion`, optional `selector` | Jev assesses a screenshot of the viewport, or of the region around the element |
| `audit` | optional `scope` (`body`), `min_ratio` (4.5), `large_text_min_ratio` (3.0), `max_elements` (300, at most 1000) | Each visible element in the scope meets the page audit rules below |

Image checks require a loaded `<img>` and explicit selectors. For example, add these
checks to a step that shows a product image:

```json
[
  {"id": "photo-bounds", "kind": "image_contained", "selector": "#product-photo", "container": "#product-card"},
  {"id": "photo-full", "kind": "image_crop", "selector": "#product-photo", "expected": "full"}
]
```

Use `expected: "allowed"` when cropping is intentional. A card that clips an oversized
image can pass containment and fail the full-image check. Containment measures visible
image content after clipping; it does not require the image element's entire box to fit.
The measurements account for intrinsic image size, border and padding, `object-fit`,
supported `object-position` values, and rectangular ancestor overflow clipping. Normal
page scrolling does not count as cropping. Checks apply at the requested viewport size.

Missing, unloaded, hidden, or unsupported images remain uncertain, even when cropping is
allowed. Transforms, masks, rounded clipping, and absolute, fixed, or sticky positioning
require review. Root/body overflow clipping, non-default `overflow-clip-margin`, and
complex `object-position` expressions also remain unsupported. Measurements are rounded
to 0.01 CSS pixels. These checks do not inspect pixels, detect cropping already present
in a source file, or decide whether an allowed crop removes important content. Artwork
review remains separate.

### Page audit

Add one `audit` check to a step to review the page state after that step. No selector list
is necessary, and the sweep makes no model call:

```json
{"id": "page-review", "kind": "audit"}
```

The sweep examines up to `max_elements` visible elements in `scope`, in document order:

| Rule | Applies to | Fails when |
|---|---|---|
| `unclipped` | Elements with their own text | Same rule as the explicit check |
| `ellipsis` | Text with `text-overflow: ellipsis` and `white-space: nowrap`, in place of `unclipped` | Same rule as the explicit check |
| `contrast` | Elements with their own text, except `:disabled` and `aria-disabled="true"` controls | Ratio is below `min_ratio`, or below `large_text_min_ratio` for text of 24 px or more, or bold text of 18.66 px or more |
| `text_overlap` | Pairs of text elements that are not nested | Line boxes overlap by more than half a line, and no opaque layer covers the lower text |
| `accessible_name` | Links, buttons, form fields, and focusable ARIA widgets | No name from `aria-labelledby`, `aria-label`, a label, text, image `alt`, `title`, or `placeholder` |
| `unobstructed` | Controls | Same rule as the explicit check. A control outside the viewport is uncertain |
| `target_size` | Controls | Smaller than 24 × 24 CSS px, with no WCAG 2.5.8 spacing or inline-link exception |
| `image_alt` | Images | No `alt`, no label, and not marked decorative |
| `image_loaded` | Images | The load is complete but the image has no pixels |
| `document_language`, `document_title`, `horizontal_fit` | The page, when `scope` is `body` or `html` | The `lang` attribute or title is empty, or the document is wider than the viewport |

The `audit` entry in `design.json` reports `counts` per rule, `uncertain_reasons`, and up to
100 `findings`. Failures come first. Each finding has a unique CSS `selector`, so you can
convert it into an explicit check. Passes are counted but not listed.

The audit fails if any rule fails. Otherwise it is uncertain if any element is unsupported,
or if the sweep stops early. `truncated_reason` gives the cause: `element_limit` (more than
`max_elements` visible elements), `overlap_limit` (50 overlapping text pairs), or
`time_budget` (3 seconds). Unsupported cases use the same guards as the explicit checks,
for example ancestor opacity, transforms, clipping, and gradient backgrounds.

Open shadow roots, frames, embedded objects, and text in `display: contents` elements are
not swept. Each one is reported as an uncertain `unswept` item. Screen-reader-only text, a
clipped box of 1 px or less, gets no visual rules.

Contrast confirms the backdrop at the centre of the element. Only ancestors of the text can
paint between the text and the background it measures. Any other layer makes the result
uncertain. If no element paints a background, contrast uses the default white canvas. If
the page can use a dark or forced-colors scheme, that result is uncertain. A canvas result
outside the viewport is also uncertain, because the backdrop cannot be confirmed. Layers
with `pointer-events: none` are not detected. These contrast rules also apply to explicit
`contrast` checks.

The accessible-name rule approximates the browser computation. It ignores hidden and
`aria-hidden` content. A name from CSS generated content stays uncertain. If the scope
has no visible size, for example a `body` that holds only fixed-position content, the audit
is uncertain with `not_visible`. Set `scope` to the visible container. The audit measures one viewport and one page state. To review
other sizes, run the journey again with another `viewport`. To review other states, add
an `audit` to each step. The audit does not inspect pixels, judge visual taste, or check
heading order, keyboard focus order, or motion.

### Visual review with screenshots

A `visual` check sends Jev one screenshot and one criterion. Without `selector`, the image
is the current viewport. With `selector`, the image is a viewport region around that
element, at least 280 × 280 CSS px. The observation gives the element's position in the
image as `screenshot.target_box`. The element must be fully inside the viewport. Otherwise
the check is uncertain with `visual_target_not_in_viewport`.

```json
[
  {"id": "hero-photo", "kind": "visual", "selector": "#hero img", "criterion": "The photo shows a running shoe."},
  {"id": "no-overlap", "kind": "visual", "criterion": "No text overlaps other text."},
  {"id": "no-cutoff", "kind": "visual", "criterion": "No button label is cut off."}
]
```

Ask one simple question in each criterion. A criterion with several claims is more often
uncertain. Each check is its own TypeSafe request, so an image cannot affect another
question. The runner captures PNG, downscales the image so that no side is more than
1568 px, and sends one JPEG. TypeSafe accepts sides from 280 to 1568 px and does not resize
images. Each step folder keeps the image as `visual-NN.jpg` with owner-only permissions.

TypeSafe calls image input experimental and not ready for production. The request uses
the required `TypeSafe-Danger-Zone-Images: true` header. Image tokens are billed as input
tokens. A live check of the example form used about 1,500 input tokens for a 390 × 844
viewport, and about 900 for a 280 × 280 region.

Visual assessments are advisory, like contextual assessments. A visual pass cannot create a
verified overall pass. A visual fail cannot fail the report or override a rule result. Each
one leaves the design status at `needs_review` for a person to confirm.

Rules keep both their passes and failures. Jev does not override deterministic results.
Contextual assessments are advisory and cannot create a verified overall pass. Unsupported
measurements remain uncertain. An uncertain artwork check therefore leaves the overall
design status at `needs_review`, even when every supported check passed.

The top-level `report.json` separates `navigation_status` and `design_status`, keeps all
steps in the denominator, and aggregates provider usage. Step folders retain navigation
traces, assertions, final screenshots, optional `design.json`, and `visual-NN.jpg` images.
Jev receives a screenshot only for a `visual` check. Navigation decisions use text only. Whole-journey action/time budgets
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

Known input values use field labels with whitespace normalized; duplicate normalized labels are rejected.
Input values are preserved unchanged. If a value is missing, an optional text helper can
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
`1231850a0bf1a0c0341fe408ef1668dbbfdfac46` (MIT). The wrapper uses its observation,
action execution, and typed decision helpers without modifying upstream.
