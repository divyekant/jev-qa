# Jev QA v4 validation — 2026-09-17

The frozen candidate met every declared acceptance gate: three eight-case regression runs and four cases on a fresh application. This closes the observed mobile blockers in this test set. It does not establish general QA reliability or aesthetic judgment.

## Delivered changes

- Jev makes one finite target choice across eligible visible controls, observed offscreen controls, WAIT, DONE, and ABSTAIN. Code maps the chosen target to its observed interaction. The separate operation choice no longer competes with reveal choices.
- Jev receives current required postconditions, including their supplied element references. The request distinguishes outcomes after an action from prerequisites for activating a control.
- The confidence threshold remains 0.80. Visible distractors remain available. An offscreen choice only scrolls; activation requires a fresh observation, a new Jev decision, and the existing freshness/occlusion guards.
- An independent Chrome connection closes explicitly recorded owned tabs after a Browser Harness crash. Cleanup preserves preexisting tabs, concurrently opened user tabs, cookies, and the external Chrome process.
- Incomplete cleanup remains visible beside the original error, even after error redaction. The installed skill describes the new evidence, behavior, and remaining limits. The wrapper stays pinned to Luna.

Jev remains the only action/contextual decision model. Python performs assertions and geometry/style checks. No second model or scripted sequence rescues a failed live journey. The legacy non-Jev chooser is unchanged.

## Frozen acceptance results

The [acceptance contract](acceptance.json) was saved before paid v4 testing. Runtime sources were frozen again after development corrections. All three final regression runs and the fresh run used identical runtime hashes. Fixtures, truth, viewports, budgets, and the threshold were unchanged.

| Run | Complete journeys | Checkpoints | Supported checks correct | Seeded defects found | Sum of case process time |
|---|---:|---:|---:|---:|---:|
| regression-1 | 8/8 | 88/88 | 64/64 | 14/14 | 75.111 s |
| regression-2 | 8/8 | 88/88 | 64/64 | 14/14 | 60.962 s |
| regression-3 | 8/8 | 88/88 | 64/64 | 14/14 | 53.371 s |
| fresh | 4/4 | 40/40 | 32/32 | 6/6 | 20.424 s |

Combined: **28/28 journeys, 304/304 checkpoints, 224/224 supported checks, and 48/48 seeded-defect instances**. There were no false passes or false failures among supported checks. The 48 instances include repeated testing of the same regression defects; they are not 48 unique bugs.

The final runs also matched all 28 contextual expected outcomes and left all 28 artwork checks uncertain. Contextual judgments remain advice. Correct artwork abstention is not visual understanding. Clean cases therefore retain overall `needs_review`; seeded cases report confirmed defects. Complete navigation does not mean the product has no defects.

The regression set uses the original workshop and library pages at desktop and narrow viewports, with clean and seeded variants. The fresh [Borrow Studio page](fresh/index.html) has ten objectives: category, search, results, details, duration, collection window, name, contact, care agreement, and a local draft review. Its narrow view needs separate reveals for the equipment control and care agreement. Its seeded variant contains clipped text, low contrast, and misalignment.

The fresh page and truth were frozen before paid v4 calls. An independent no-model preflight verified 36/36 noncontextual expected outcomes. That scripted oracle was never available to the live Jev loop. Only the explanatory README was corrected after a preflight geometry measurement, before paid testing; page code, tasks, and truth did not change.

## Tokens and speed

All final calls reported `jev-1.13.0`. No text helper calls occurred. API time below is client-observed request wall time, not server compute time. Case process time includes startup, browser work, screenshots, evidence, and cleanup.

| Run | Jev calls | Input tokens | Output tokens | Sum of API time | Median case process time |
|---|---:|---:|---:|---:|---:|
| regression-1 | 102 | 222,279 | 13,771 | 20.534 s | 8.060 s |
| regression-2 | 102 | 222,279 | 13,771 | 20.168 s | 7.612 s |
| regression-3 | 102 | 222,279 | 13,771 | 21.078 s | 6.559 s |
| fresh | 48 | 96,362 | 6,060 | 8.177 s | 5.173 s |

The 28 final cases used **354 requests, 763,199 input tokens, and 47,373 output tokens**. They took 69.957 seconds of summed API time and 209.868 seconds of summed case process time.

Each final eight-case regression used 222,279 input and 13,771 output tokens. The prior v3 sample used 318,221 input and 20,891 output tokens while completing only 6/8 journeys. The new sample uses about 30.1% fewer input tokens and 34.1% fewer output tokens. This is a development comparison with different completed work, not an isolated causal benchmark.

Regression batch process time varied from 53.371 to 75.111 seconds. The prior v3 sample took 59.791 seconds. There is no consistent demonstrated wall-time speedup. The pooled median across the 24 final regression cases was 7.228 seconds; fresh cases had a 5.173-second median.

Across every paid v4 development attempt, final run, and actual-Chrome probe: **532 requests, 1,163,847 input tokens, and 73,542 output tokens**. These provider-reported token counts are not billed spend. Implementation/review agent usage is separate and unavailable here.

## Jev time versus Luna wrapper time

The third regression was launched by a warm, reused `luna_dev` agent running `gpt-5.6-luna` with max reasoning. It launched one fixed batch and reported the saved output. It made no browser decisions and did not change code or verdicts.

| Layer in that same wrapped batch | Measured time |
|---|---:|
| Jev API calls | 21.078 s |
| Whole evaluator command, including Jev | 53.767 s |
| Non-API time inside that command | 32.689 s |
| Dispatch to command start | 20.121 s |
| Command end to parent-observed completion | 18.413 s |
| Dispatch to parent-observed completion | 92.302 s |

The extra 38.5 seconds includes agent launch/reporting, delivery, and observation delay. It is not a pure model-inference measurement. Wrapper tokens were unavailable and are recorded as `null`. This is not a cold-start test of the installed low-reasoning `jev_qa` role. That role remains configured; native discovery still requires a fresh session. See [wrapper timing](wrapper-timing.json).

## Failed development attempts, retained

| Attempt | Complete journeys | Checkpoints | All expected check outcomes |
|---|---:|---:|---:|
| [canary-1](canary-1-summary.json) | 0/2 | 4/22 | 0/20 |
| [canary-2](canary-2-summary.json) | 1/2 | 13/22 | 10/20 |
| [development-1](development-1-summary.json) | 4/8 | 57/88 | 43/80 |
| [development-2](development-2-summary.json) | 4/8 | 57/88 | 43/80 |

1. The first target-first canary omitted current assertion evidence. Jev chose the correct search control but gave DONE enough probability to block at 0.75–0.78.
2. Adding assertion results completed one narrow library journey. The other still blocked at search. Rules were clarified to distinguish prior input entry from submission.
3. Two full development batches completed the four library cases but blocked original-page actions. The reduced assertion payload said `visible=false` and `text_target_not_visible` without identifying the expected result panel. That was ambiguous evidence about outcomes versus action prerequisites.
4. The final schema retained supplied selectors and explicitly labeled required postconditions. All three subsequent unchanged regression runs passed. This supports the correction on this set, but does not isolate every change's causal effect.

No failed record was removed. The fresh paid evaluation ran only after this final correction. No threshold, fixture, expected outcome, or forced action was changed to obtain passes.

## Chrome session and crash cleanup

The [actual current-Chrome probe](existing-chrome-probe.json) used a fictional local HttpOnly cookie and a new owned tab. It completed 1/1 checkpoint with one Jev call: 1,052 input tokens, 49 output tokens, 315 ms API time, and 556 ms journey time. Journey time excludes probe connection/setup and teardown. The probe preserved preexisting targets, closed its child tab, requested synthetic-cookie deletion, and closed its connection. It opened no private account page.

A separate real-browser integration test used externally owned disposable Chrome. It killed the private daemon, then verified both recorded owned tabs were gone while the sentinel tab, a concurrently opened user tab, cookie, and external process remained. The parent full suite includes this test. The implementation worker also repeated the crash test five times successfully.

Two limits remain explicit: Chrome may become unreachable, or the daemon may fail before reporting its tab ID. Cleanup then reports incomplete; it never guesses ownership from newly appearing tabs. Normal session reuse means eligible cookies/local storage in a new tab, not another tab's unsaved form or sessionStorage.

## Verification and limits

- 61 local tests passed in the final parent run; wheel/source builds, compileall, skill validation, and global doctor passed.
- Independent Luna reviews found no material remaining runtime/schema or browser/CLI cleanup issue.
- All final runtime/fixture hashes matched. All 326 saved action decisions retained raw requests/responses and owner-only permissions. All 22 accepted reveals were followed by a fresh observation before the next decision.
- Executed decisions met 0.80. Invalid references and low-confidence actions have no-mutation tests. Failed assertions still prevent a verified pass.
- The installed skill and Luna role matched their source. Credential mode was 600; the inspected source/evidence contained no configured API key. No owned browser processes remained, and the original local preview remained available.

Artwork, aesthetic taste, canvas meaning, frames/shadow DOM, uploads, popup workflows, and dedicated nested-container scrolling remain unsupported. Contextual assessments remain advisory. An arbitrary existing tab, other Chrome profiles, and cross-origin login flows are outside the existing-Chrome option. No workflow integration was added in this version.

## Evidence

- regression-1: [summary](regression-1-summary.json), [raw results](runs/regression-20260917T232922Z/results.json), [frozen protocol](runs/regression-20260917T232922Z/protocol.json)
- regression-2: [summary](regression-2-summary.json), [raw results](runs/regression-20260917T233051Z/results.json), [frozen protocol](runs/regression-20260917T233051Z/protocol.json)
- regression-3: [summary](regression-3-summary.json), [raw results](runs/regression-20260917T233222Z/results.json), [frozen protocol](runs/regression-20260917T233222Z/protocol.json)
- fresh: [summary](fresh-summary.json), [raw results](runs/fresh-20260917T233335Z/results.json), [frozen protocol](runs/fresh-20260917T233335Z/protocol.json)
- [Verification facts](verification.json)
- [Walkthrough](../jev-qa/WALKTHROUGH.md) and [runner guide](../jev-qa/README.md)
- [Installed skill source](../jev-qa/skill/SKILL.md)
