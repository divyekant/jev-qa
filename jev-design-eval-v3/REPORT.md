# Jev QA v3 validation — 2026-09-17

The changes improved observed coverage, but did not eliminate all mobile blockers. Existing logged-in Chrome support passed a local authenticated-session test in the user's running Chrome.

## Changes delivered

- Keep confirmed action history across journey checkpoints, including whether each action changed the observed page.
- Offer finite `REVEAL_R*` choices for observed offscreen controls. Execute one bounded native scroll, wait for rendering, observe again, then require a separate guarded click.
- Save full action-decision requests, raw answers, and probability distributions in private `decision-NNN.json` files. Mark credential/authentication-field redaction; do not truncate the request through the general report serializer.
- Separate execution, assertion, and product status. Blocked navigation leaves later checks `not_reached`; it does not create a product defect. Earlier confirmed defects remain failures even if later navigation blocks.
- Replace conflicting upstream whole-task/search-submit instructions with scoped current-objective rules for Jev-only decisions. Keep the existing chooser, finite action validation, and 0.80 confidence threshold.
- Add opt-in existing Chrome access through `--browser existing-chrome`. The default remains disposable Chrome. The installed wrapper remains `gpt-5.6-luna`.

## Frozen comparison

Both final comparisons use the same two single-page applications, clean/seeded variants, desktop/mobile viewports, expected results, one attempt per case, and a 0.80 threshold. These are small development samples, not established accuracy rates. The second application is a regression holdout from the previous development round, not a newly unseen benchmark.

| Measure | Prior v2 | Final v3 |
|---|---:|---:|
| Complete journeys | 4/8 | 6/8 |
| Desktop journeys | 4/4 | 4/4 |
| Mobile journeys | 0/4 | 2/4 |
| Verified checkpoints | 56/88 | 86/88 |
| Supported design checks correct, fixed denominator | 36/64 | 58/64 |
| Seeded defects found | 7/14 | 12/14 |
| Incorrect reached supported verdicts | 0 | 0 |
| Contextual checks reached and correct | 4/8 | 6/8 |
| Unsupported artwork correctly left uncertain | 6/8 | 8/8 |
| All expected check outcomes, including abstention | 46/80 | 72/80 |

All 58 reached supported measurements matched their expected result. Six supported checks were unperformed; two of those contain seeded defects. Artwork remains unsupported. Correctly returning `uncertain` for artwork is not successful visual interpretation. The six contextual results are model advice, not deterministic proof.

| Case | Checkpoints | Navigation | Expected check outcomes | Process wall time |
|---|---:|---|---:|---:|
| original-desktop-a | 11/11 | pass | 10/10 | 8.13 s |
| original-mobile-b | 11/11 | pass | 10/10 | 6.61 s |
| original-desktop-b | 11/11 | pass | 10/10 | 7.37 s |
| original-mobile-a | 11/11 | pass | 10/10 | 7.76 s |
| wide-q4 | 11/11 | pass | 10/10 | 7.20 s |
| wide-q9 | 11/11 | pass | 10/10 | 7.59 s |
| narrow-q4 | 10/11 | blocked | 6/10 | 8.74 s |
| narrow-q9 | 10/11 | blocked | 6/10 | 6.39 s |

Clean complete cases still have overall `needs_review` because each includes an unsupported artwork check. Broken cases retain confirmed failures. `narrow-q9` correctly has both `execution_status: blocked` and `product_status: fail`: it found defects before reaching its navigation limit.

## Remaining failure and its evidence

Both narrow library cases reach checkpoint 10/11, then stop before opening the review screen. Jev selects the correct offered `REVEAL_R4` for the review control, but confidence is 0.70–0.74. The required threshold is 0.80. The one allowed refresh does not resolve the uncertainty. No rejected reveal or follow-up click is executed, and four checks per case remain unperformed.

This remaining failure is model decision uncertainty, not a failed scroll execution or evidence that the page is broken. General mobile coverage remains experimental. The current wheel action also has no dedicated nested-scroll-container routing; this benchmark does not establish that capability.

Evidence: [clean blocked decision](../jev-design-eval-v2/runs/live-20260917T225024Z/narrow-q4/step-11/decision-001.json), [seeded blocked decision](../jev-design-eval-v2/runs/live-20260917T225024Z/narrow-q9/step-11/decision-001.json).

## Retained failed attempt

The first v3 development batch completed only 3/8 journeys and scored 42/80. Its saved requests showed a conflict: verified prior filter actions were present, but upstream instructions still demanded an immediate click on a populated search form. On the original mobile case, the first operation distribution split between CLICK (0.51) and REVEAL_R1 (0.40).

The final correction changed the general Jev-only decision instructions. It did not change fixtures, expected results, viewport, confidence, or action limits. The final rerun improved coverage. This combined experiment does not isolate the causal contribution of each individual change.

The first batch remains [fully preserved](../jev-design-eval-v2/runs/live-20260917T224548Z/results.json), alongside its [summary](initial-summary.json). The earlier v2 attempts also remain unchanged.

## Tokens and speed

| Measure | Prior v2 final | Final v3 |
|---|---:|---:|
| Jev requests | 69 | 100 |
| Input tokens | 197,427 | 318,221 |
| Output tokens | 13,268 | 20,891 |
| Sum of model request wall time | 13.910 s | 20.171 s |
| Sum of child-process wall time | 32.128 s | 59.791 s |

Final v3 median process time was 7.482 seconds per case. The runner itself reported 58.496 seconds total. The additional completed steps and retained history increase work and tokens. Do not read these totals as a controlled latency regression or speedup: the samples complete different amounts of work, and the final v3 first case overlapped the local test suite.

All recorded model calls used `jev-1.13.0`; no text helper or frontier browser rescue ran. The final batch contains 94 action decisions and six contextual assessments. Four accepted REVEAL actions were followed by fresh observations and later normal actions.

Across this turn's first batch, final batch, and Chrome probe: 163 Jev requests, 501,851 input tokens, and 33,227 output tokens. These are provider-reported token counts, not billed cost. A Luna wrapper was not used to launch these benchmark runs, so wrapper time and tokens are not measured. Implementation/review agents were Luna; their usage is separate and is not included here.

## Existing logged-in Chrome

The new mode uses Chrome's debugging protocol through the existing Browser Harness dependency. It does not use Playwright. It discovers the macOS default Chrome endpoint, validates a loopback browser WebSocket, opens an owned temporary test tab, and preserves existing tabs and the external Chrome process. It does not export cookies or copy profiles.

A no-model browser integration test independently seeded an HttpOnly cookie in an externally owned disposable Chrome. The task tab reused it, then cleanup left exactly the preexisting page targets and the external process alive. Constructor-failure and normal/timeout cleanup also have tests. If the private daemon crashes before cleanup, an owned temporary tab can remain; preexisting tabs are not selected or closed by that fallback.

The [actual current-Chrome probe](existing-chrome-probe.json) used only a fictional local HttpOnly session. A second owned tab loaded the authenticated page and Jev clicked its verification button. Result: 1/1 checkpoint passed, one request, 1,181 input tokens, 69 output tokens, 243 ms model request time, and 532 ms journey time. That journey time excludes the probe's connection/setup and teardown. The probe ran before the final decision-rule correction; browser integration code is unchanged.

The probe retained all preexisting targets, closed its child tab, requested deletion of its short-lived synthetic cookie, and closed its connection. No private account page was opened. The integration test separately verifies cleanup of both runner-owned tabs.

New tabs can share eligible cookies and local storage. They do not inherit another tab's unsaved form or tab-specific session storage. Arbitrary existing-tab takeover, other profile selection, remote endpoints, and cross-origin authentication flows are outside this option. Chrome may require the user to allow the connection; the runner does not bypass that permission. See [Chrome's official connection guidance](https://developer.chrome.com/docs/devtools/agents/get-started/configuration).

## Verification

- 56 local tests passed in the parent's final full-suite run.
- Independent Luna review found no material runtime issue; its 38 focused tests passed.
- Real no-model REVEAL probe confirmed one bounded native wheel event, no activation, and a subsequent normal click target.
- All final frozen runtime/fixture source hashes matched the delivered code after evaluation.
- All 94 saved action decisions retained complete requests and answers, correct model IDs, and owner-only file permissions. History and the corrected rules reached the actual API request.
- Installed skill link and both Luna role files were verified. Skill validation, compileall, global launcher doctor, and wheel/source-distribution builds passed.
- A final source/evidence scan found no configured API key in the inspected deliverables.

[Final summary](final-summary.json) · [Final raw results](../jev-design-eval-v2/runs/live-20260917T225024Z/results.json) · [Protocol and source fingerprints](../jev-design-eval-v2/runs/live-20260917T225024Z/protocol.json) · [Verification facts](verification.json) · [Workflow walkthrough](../jev-qa/WALKTHROUGH.md)
