# Jev versus computer-use subagent

Both arms created the correct invoice and produced all six expected QA judgments.
The computer-use arm needed browser setup recovery and exceeded its creation time target.

## Same task and independent scoring

Create one fictional draft invoice for Ada Example, `ada@example.com`, quantity 3,
unit price $19.95, total $59.85, Draft and Unpaid. Then review the correct display and
a second display whose total is $69.85. The model receives the expected requirements,
but not the expected pass/fail labels or the seeded-defect implementation.

Both runs used the same fixture source and fresh empty server state. Independent checks
confirmed exactly one submission, one saved record, and all seven expected stored fields.
Both arms accepted the correct view and flagged only the total criterion on the defective view.
No successful action was repeated to improve the score.

The computer-use agent had no inherited conversation. It used the browser computer-use
tool, with no Jev calls, fixture source reads, or direct HTTP actions. Parent inspection
verified its saved record and scored its three judgments for each view against frozen answers.

## Comparison

| Metric | Jev runner | Computer-use subagent |
|---|---:|---:|
| Model | jev-1.13.0 | gpt-6-astra, high reasoning |
| Creation independent checks | 9/9 | 9/9 |
| QA judgments matching expected labels | 6/6 | 6/6 |
| Invoice mutations | 5 | 5 |
| Measured completion time | 5.954 s | 188.089 s |
| Model responses | 8 | 23 |
| Input tokens, including cache hits | 14,169 | 1,745,634 |
| Cached input tokens | Not reported | 1,671,168 |
| Uncached input tokens | Not separately reported | 74,466 |
| Output tokens | 1,041 | 2,999 |
| Total reported tokens | 15,210 | 1,748,633 |

Subagent input tokens count context supplied repeatedly across model responses. About 96%
were cache hits. These totals are not billed cost and are not equivalent new-content volumes.
Output tokens already include reasoning tokens. Parent orchestration tokens are excluded
from both arms. The separate post-eval cleanup check is also excluded.

## Timing interpretation

Jev's 5.954 seconds includes launcher, disposable browser, action/QA work, report generation,
and browser cleanup. Its model calls consumed 2.170 seconds including network time. Remaining
runner/browser work consumed 3.784 seconds. It did not run through a native Codex subagent.

The computer-use result uses actual runtime timestamps from the parent dispatch tool call
to the child's final response. The full 188.089 seconds breaks down as follows:

| Interval | Time |
|---|---:|
| Dispatch and initial Chrome access attempts | 117.936 s |
| In-app browser recovery through final QA observation | 24.443 s |
| Final observation through saved report and final response | 45.710 s |

Chrome returned `Debugger unattached`, and native inspection showed blank page bodies.
The local server remained healthy and no record had been created. Parent authorized a
switch to the in-app browser. Visible in-app tabs were unsupported in the child task;
a hidden tab worked. The original setup time is retained.

The agent made 22 tool calls, totaling 17.701 seconds of tool execution. The remaining
170.388 seconds includes model processing, generation, scheduling, and orchestration;
it is not a direct measurement of model inference latency.

The child's `reportReadyMs` was actually its last browser observation. Its reported QA
durations of 232 and 219 milliseconds measured tool execution only. Neither number is a
complete QA turnaround time. This comparison uses runtime completion evidence instead.

The child reported a creation phase of 111.941 seconds, exceeding the 90-second target.
Jev enforced its 90-second deadline. The computer-use arm completed after recovery, but
did not meet that timing constraint. The child did not close tabs before its final result;
a separate cleanup check found both created tabs were already absent. The local server
was stopped after independent validation.

## Conclusion and limits

On this case, output quality matched. Jev's bounded runner completed much sooner and used
fewer reported tokens. The computer-use run's full elapsed time was about 31.6 times higher,
but browser setup failures explain much of that difference. This is not evidence that its
underlying model is 31.6 times slower.

The 24.443-second recovery-to-observation interval is a diagnostic slice of the same run,
not a separate clean benchmark. Neither arm tests broad QA accuracy, requirement discovery,
visual layout review, or repeatability. These are different orchestration and browser paths.

## Evidence

- [Computer-use runtime metrics and tool timeline](runtime-metrics.json)
- [Computer-use agent report](agent-report.json)
- [Independent saved record](server-state.json)
- [Frozen comparison protocol](protocol.json)
- [Jev evaluation report](../jev-invoice-eval/REPORT.md)

Runtime evidence source: child session `01a0b0e2-b248-76e3-8225-b87843caf20d`.
Dispatch: `2026-09-17T19:40:41.917Z`. Final response: `2026-09-17T19:43:50.006Z`.
