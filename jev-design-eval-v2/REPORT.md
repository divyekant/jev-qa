# Jev QA v2: implementation and live evaluation

**Installed and useful for the tested desktop flows. Mobile navigation remains unreliable.**
The final batch completed all four desktop journeys and stopped all four mobile journeys
at an offscreen control. Seven of fourteen seeded defects were found; seven were unreached.
Every reached measurable check matched its expected result (36/36), but coverage was incomplete.

## Delivered

The reusable [skill](../jev-qa/skill/SKILL.md) runs a verified browser journey through
[jev-qa](../jev-qa/README.md). The installed custom role pins `gpt-5.6-luna` with low
reasoning. Luna launches one command and summarizes evidence. Jev chooses browser actions
and supplies contextual judgments. Browser code measures design requirements and checks UAT
postconditions. No second model takes over a failed journey.

The parent still supplies the test contract: authorized URL, viewport, values, ordered
objectives, postconditions, and design requirements. This is not automatic test-plan creation
or general screenshot critique.

Improvements include one current objective per step, deterministic early completion,
one bounded low-confidence observation retry, read-only offscreen-control context, compact
element facts, authoritative rule results, and explicit unsupported/unperformed checks.
The 0.80 threshold, original page, and expected labels were preserved.

## Latest frozen live run

Evidence: [live-20260917T221120Z/results.json](runs/live-20260917T221120Z/results.json).
Source hashes, task contracts, and expected outcomes were frozen in
[protocol.json](runs/live-20260917T221120Z/protocol.json) before execution.

- Completed journeys: **4/8**; verified steps: **56/88**.
- Supported deterministic design results: **36/64 correct**.
- Contextual judgments: **4/8 matched** the expected answer; these remain advisory.
- Unsupported artwork: **6/8 correctly abstained**. This is not artwork detection accuracy.
- Fixed-denominator total: **46/80**, including unsupported outcomes and unreached checks.
- Missed seeded defects: **7**; defective checks falsely passed: **0**.

| Case | UAT steps | Measured checks | Context matched | Process seconds | Input / output tokens |
|---|---:|---:|---:|---:|---:|
| original-desktop-a | 11/11 | 8/8 | 1/1 | 5.84 | 30,475 / 2,012 |
| original-mobile-b | 3/11 | 0/8 | 0/1 | 2.67 | 13,065 / 851 |
| original-desktop-b | 11/11 | 8/8 | 1/1 | 4.92 | 30,475 / 2,012 |
| original-mobile-a | 3/11 | 0/8 | 0/1 | 2.37 | 13,065 / 851 |
| wide-q4 | 11/11 | 8/8 | 1/1 | 6.02 | 43,139 / 2,962 |
| wide-q9 | 11/11 | 8/8 | 1/1 | 4.99 | 39,316 / 2,698 |
| narrow-q4 | 3/11 | 2/8 | 0/1 | 2.38 | 13,946 / 941 |
| narrow-q9 | 3/11 | 2/8 | 0/1 | 2.94 | 13,946 / 941 |

All model responses identified `jev-1.13.0`; no text-helper calls occurred.
Across eight cases: **69 requests**, **197,427 input tokens**,
**13,268 output tokens**, and **13.910 seconds** summed API latency.
API latency includes transport/provider overhead, not only model computation.
Sequential child-process wall time totals **32.128 seconds**;
median case time is **3.926 seconds**.
Process time includes browser startup, observations, assertions, measurements, and cleanup.
Usage is measured; billed cost was not available.

The benchmark uses two single-page applications, clean and seeded variants, and desktop/mobile
viewports. Each case has eleven UAT steps, eight measurable design checks, one unsupported
artwork check, and one contextual check. The measurable checks include 14 seeded defects
and 50 valid cases. Seeded defects include clipping, low contrast, disabled-control behavior,
misalignment, blocked pointer targets, horizontal overflow, and incorrect ellipsis titles.
The workflows stop at review; they do not send a real booking or reservation.

## Wrapper verification

A real subagent explicitly selected as `gpt-5.6-luna` read the skill, invoked the CLI once,
and returned its saved evidence. The [smoke report](luna-wrapper-smoke/report.json) shows
2/2 UAT steps and 2/2 design checks passed, with two Jev requests, 3,390 input tokens,
215 output tokens, 0.351 seconds API latency, and 2.028 seconds runner time.
Wrapper wall time and wrapper tokens were not instrumented; those figures exclude them.
The eight complex cases above ran directly through the same CLI to isolate runtime behavior.

The global skill and role files are installed. A fresh Codex session is needed to discover
the custom `jev_qa` role. The skill's explicit Luna fallback was exercised in this session;
native custom-role dispatch was not claimed as tested.

## Failures retained and limits

The first v2 batch is preserved at
[live-20260917T220110Z](runs/live-20260917T220110Z/results.json): 4/8 completed journeys,
56/88 verified steps, and 42/80 design outcomes. Mobile navigation stopped at offscreen controls.
Contextual inputs omitted the collector's full text. The adapter fixes were tested before
the later batch. Each batch has one attempt per case; the runner permits one observation
refresh on low confidence. No failed mutation is replayed.

The independently authored second fixture was used to diagnose adapter failures. The later
batch is therefore a regression result, not a blind holdout result or a general accuracy claim.
The earlier original benchmark completed 0/12 design-state checkpoints. Its task granularity
and stopping behavior differ, so its short failure time is not a successful-run speed baseline.

Two further mobile diagnostics tested enriched scroll labels and fuller completed-objective
descriptions. Both stopped at step 4 with no mutation at that step. Their reports are retained:
[scroll-label probe](mobile-scroll-canary/report.json) and
[progress-description probe](mobile-progress-canary/report.json). Those unsuccessful changes
were removed. The shipped runtime hashes match the final eight-case protocol exactly.
The probes consumed 26,430 input and 1,710 output tokens across ten Jev requests.

Across both eight-case batches, both mobile probes, and the Luna smoke test, development used
149 Jev requests, 420,361 input tokens, and 28,206 output tokens. Summed API latency was
33.152 seconds; runner time was 72.707 seconds. These figures exclude earlier historical
experiments, developer/reviewer agents, and the Luna wrapper's own tokens and elapsed time.
See [DEVELOPMENT_USAGE.json](DEVELOPMENT_USAGE.json).

Local validation: 38 tests passed, the real-browser offscreen probe passed, the wheel built,
and independent review found no remaining blocker in the implemented guards and measurements.
Passing code checks does not resolve the observed mobile model limitation.

Rules cover declared HTML requirements. Unsupported effects and missing measurements remain
uncertain. Canvas, artwork meaning, aesthetic quality, and general screenshot comparison are
outside this implementation. Jev never sees screenshots. Overall clean-case reports can remain
`needs_review` because unsupported artwork and advisory contextual checks cannot verify a pass.

## Use

Ask: **“Use $jev-qa with a Luna subagent to run design QA and UAT on this local page against
these expected outcomes.”** Supply the URL and acceptance requirements.

The [guide](../jev-qa/README.md) includes the journey JSON schema and supported checks.
The global command is `jev-qa journey task.json --output work/new-result`.
The credential remains in a private global environment file; no key is committed in the artifact.
