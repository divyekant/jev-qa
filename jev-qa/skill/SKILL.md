---
name: jev-qa
description: Run browser user acceptance tests and measured design conformance checks with Jev. Use for authorized local or test pages with explicit expected outcomes. Does not judge artwork or general visual taste.
---

# Jev design QA and UAT

Use `/Users/dk/.local/bin/jev-qa journey task.json --output work/jev-result`.
Read the schema and examples in [the runner guide](/Users/dk/projects/jev-qa/jev-qa/README.md).

The parent prepares the test contract: authorized URL, viewport, fictional values, ordered objectives, deterministic postconditions, and scoped design requirements. Use selectors grounded in the supplied app or test specification. Do not invent expected behavior. If necessary requirements are absent, return `needs_review` with the missing information.

Prefer a single delegated invocation for substantial work. Use the `jev_qa` custom role, configured as **gpt-5.6-luna**, when available. Otherwise spawn a default subagent with `model="gpt-5.6-luna"`, `reasoning_effort="low"`, and `fork_turns="none"`. Supply this skill path, the complete task JSON path, authorized target, output path, and reporting requirements. Do not silently inherit the parent model. If explicit Luna routing is unavailable, run the CLI directly and disclose that no wrapper subagent was used.

The wrapper launches one bounded journey and reads its report. It must not choose browser actions, interpret screenshots, produce substitute design verdicts, or use another browser/model to rescue a failed run. Jev chooses observed actions; browser code verifies postconditions and design measurements. Only explicit contextual criteria invoke Jev assessment. The journey command disables text helpers and fixes the Jev route. Jev selects one target intent from all eligible controls, using observed state and required postconditions. Offscreen selection permits scrolling only; activation needs a fresh observation and decision. Luna wrapper tokens are separate from Jev tokens.

Current measured evidence: v4 completed all eight desktop/mobile cases in three unchanged regression runs, plus four cases on one fresh page. All 304 checkpoints completed; 224/224 supported checks and 48/48 seeded-defect instances matched the frozen truth. This is bounded synthetic evidence, not general reliability. Preserve the requested viewport and report blockers without switching to desktop or lowering confidence. See [the evaluation report](/Users/dk/projects/jev-qa/jev-design-eval-v4/REPORT.md).

Use disposable sessions by default. When the user explicitly requests their logged-in Chrome, add `--browser existing-chrome` to `run` or `journey`. This opens an owned temporary tab in the running Chrome profile; it does not take over an existing tab or copy cookies. Chrome may require the user to allow remote debugging. Do not change permissions or restart Chrome to bypass that step. Owned tab IDs have independent cleanup after a helper crash. If ownership was never recorded or Chrome is unreachable, report cleanup incomplete; never guess tab ownership. Relevant page text is sent to TypeSafe, so keep the contract scoped to the requested application. Real submissions, messages, purchases, deletions, and account changes require authorization in the parent request. Never place API keys or passwords in task JSON. The launcher loads the private credential file.

Use one current objective per step with a real postcondition. Avoid weak assertions that are already true before the required action. Include final business outcomes, not only element visibility. Use exact field labels for input values. Do not encode arbitrary executable JavaScript in tasks. A design defect need not stop later navigation; an unverified navigation step must stop the journey.

Run once unless repeats are requested. The runner permits one observation refresh for a low-confidence decision per step. It must not replay failed or uncertain mutations. Do not lower thresholds or weaken checks to obtain a pass.

Return overall status, reached/total steps, UAT assertions, design failures, unsupported/uncertain checks, report path, model IDs, requests, input/output tokens, and measured wall/API time. Distinguish deterministic findings, Jev advisory judgments, and unperformed checks. Report wrapper model and elapsed time separately when available; never infer wrapper token use from Jev usage. Use `execution_status` and `product_status` to distinguish a blocked runner from a confirmed defect. Unreached checks remain untested. Each action decision has private request/probability evidence for diagnosis. Do not share those files without checking their page content. A model's DONE or confidence is not proof. Canvas/image meaning and aesthetic quality remain unsupported.
