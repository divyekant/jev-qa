# Jev-only design QA experiment

Built and tested on 2026-09-17. **The current prototype did not complete autonomous navigation.** A separate assessment of recorded browser measurements scored 23/36. Simple rules scored 28/36. This experiment does not show a benefit from adding Jev to those rules.

## The page and task

[Open the clean page](http://127.0.0.1:8772/?build=k7) · [Open the seeded page](http://127.0.0.1:8772/?build=m4) · [Standalone HTML](index.html)

Fieldwork is a single-page workshop reservation interface. The target flow requires 11 control actions, plus scrolling where needed:

1. Select **Design systems**, search **Responsive interfaces**, and apply filters.
2. Inspect **Responsive interfaces in practice**.
3. Reserve seats. Enter **Avery Example**, **avery@example.com**, **2** seats, and access code **OPEN**.
4. Apply the code, then open **Review reservation**. Stop before confirmation.

The page includes a session list, decorative artwork, overlapping badge, details panel, form, validation state, disabled receipt control, and review panel. Other session rows are filtering distractors; their detail content is not separately implemented or evaluated. No messages, payments, or external changes occur.

The paired builds run at 1280 × 900 and 390 × 844. Reduced motion is enabled for stable measurements. There are nine checks per case, across three checkpoints.

| Check | Clean build | Seeded build |
|---|---|---|
| Full title readable | Pass | Clipped title |
| Availability badge overlaps decorative band only | Pass | Pass |
| Canvas contains approved brand mark | Uncertain | Uncertain |
| Booking status contrast | Pass, measured 12.77 | Fail, measured 1.73 |
| Receipt control genuinely disabled | Pass | Pass |
| Form fields aligned | Pass | Pass |
| Confirmation control receives pointer hits | Pass | Obstructed |
| Page fits viewport horizontally | Pass | Mobile overflow only |
| Secondary reference ellipsis exposes full native title | Pass | Pass |

This creates **seven defect instances, 25 valid presentations, and four deliberately unsupported artwork checks**. The badge, disabled control, and reference truncation test whether valid exceptions cause false alarms.

## What actually ran

The browser preflight used scripted actions, with no model calls. It reached all 12 checkpoints and verified the intended defects and valid exceptions. Independent oracles checked filters, selected session, field values, saved reservation, and absence of confirmation.

The live Jev run then attempted all four cases, once each. It used a fixed 0.80 confidence threshold. **It reached 0/12 checkpoints and produced no live design assessments.** The desktop cases stopped at the first selection. The mobile cases completed three actions each, then stopped before opening details. The saved traces show low operation confidence. These stops are not evidence that the task was completed incorrectly; they are failure to complete it autonomously.

To isolate the assessor, a separate, explicitly post-hoc component run submitted the frozen preflight measurements to Jev. It used the same criteria and threshold, once per checkpoint. It did not retry navigation or lower thresholds.

Only `jev-1.13.0` appeared in model responses. The optional text helper was disabled. Jev received browser text for navigation and structured geometry, computed styles, contrast, and pointer-hit evidence for assessment. It received no screenshots, source code, private event log, answer key, or defect mapping. The navigator could see an opaque build URL; design assessment could not.

## Quality

These scores apply **only to the recorded-evidence component run**. Unreached live checks remain unsuccessful in the end-to-end result.

| Assessor | Correct outcomes | Defects identified | False alarms | Defects incorrectly passed |
|---|---:|---:|---:|---:|
| Jev with 0.80 threshold | 23/36 (63.9%) | 3/7 | 0 | 0 |
| Simple measurement rules | 28/36 (77.8%) | 7/7 | 0 | 0 |
| Rules enforce failures, then Jev | 27/36 (75.0%) | 7/7 | 0 | 0 |

Jev identified both low-contrast instances and mobile overflow. It abstained on both clipped titles and both obstructed buttons. It also abstained on nine valid presentations. All 13 wrong outcomes were low-confidence abstentions. All four unsupported artwork checks correctly remained uncertain.

The combined policy preserves deterministic failures but lets Jev decide other outcomes. It scored below rules alone because it lost valid passes to uncertainty. The simple baseline deliberately leaves contextual badge overlap and reference truncation unresolved; those policies could also be implemented in code. This is not proof that an LLM is needed for them.

## Speed and usage

| Run | Measured wall time | Sum of API request latency | Requests | Input tokens | Output tokens |
|---|---:|---:|---:|---:|---:|
| Failed live navigation, four cases | 6.547 s | 2.540 s | 10 | 27,164 | 1,760 |
| Recorded design assessment, 36 judgments | 2.416 s | 2.269 s | 12 | 50,417 | 1,520 |

Live wall time sums the four child-process durations, including browser setup. Assessment time covers its local loop and requests; browser preparation happened earlier. API latency is client-observed request latency, not isolated model compute. The remaining time was 4.007 s and 0.147 s respectively, covering local work and overhead.

Provider-reported total usage was **77,581 input and 3,280 output tokens** across 22 requests. This excludes parent/reviewer tokens and build work. Billed cost was not obtained. No native Codex subagent dispatch latency was measured here. Do not interpret the failed 6.547-second run as successful task latency or compare it directly with the earlier invoice task.

## Evidence and limits

- [Machine-readable summary](SUMMARY.json)
- [Final preflight validation](runs/preflight-20260917T203424Z/preflight-validation.json)
- [Frozen live protocol and source hashes](runs/live-20260917T203444Z/protocol.json)
- [Failed live results](runs/live-20260917T203444Z/results.json)
- [Component protocol and input hashes](runs/assessment-20260917T203609Z/protocol.json)
- [Component results](runs/assessment-20260917T203609Z/results.json)

Each checkpoint folder retains measurements and screenshots, or submitted evidence and judgments. Live navigation folders retain reports and decision traces. Independent review verified the oracle, routing, evidence hashes, scores, and separation of the two runs. Two focused scoring tests passed.

This is one synthetic page, four cases, and one attempt per case. It tests scoped design contracts, not general aesthetic judgment or pixel similarity. Measurements do not establish canvas contents, image meaning, typography quality, or arbitrary complex background contrast. The hit checks sample nine points rather than every pixel. A native title exposes the reference text under the stated contract; that is not a complete mobile accessibility assessment.

**Conclusion:** the measurement layer worked, and Jev assessed it quickly. Navigation reliability and excess abstention prevented a useful autonomous result. Keep this failed benchmark intact before trying a separately specified improvement.

## Run locally

From this workspace root:

```sh
outputs/jev-qa/.venv/bin/python outputs/jev-design-eval/evaluate.py --serve --port 8772
outputs/jev-qa/.venv/bin/python outputs/jev-design-eval/evaluate.py --preflight
outputs/jev-qa/.venv/bin/python outputs/jev-design-eval/evaluate.py
outputs/jev-qa/.venv/bin/python outputs/jev-design-eval/evaluate.py --review-recorded outputs/jev-design-eval/runs/preflight-20260917T203424Z
outputs/jev-qa/.venv/bin/python -m unittest discover -s outputs/jev-design-eval -p 'test_*.py'
```

The two model commands use the existing private TypeSafe configuration and incur API usage. The page server and preflight do not call models.
