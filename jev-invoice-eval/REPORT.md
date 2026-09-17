# Jev invoice evaluation

Model: `jev-1.13.0`. One attempt per stage, with no retries or repairs of failed results.
This evaluates the installed browser runner, not native Codex subagent dispatch.

## Task and independent validation

Create exactly one draft invoice for Ada Example (`ada@example.com`), with quantity 3
and unit price $19.95. Save it as Draft and Unpaid, without sending it.

Jev filled four fields and clicked Save draft. A separate server-state check confirmed
one submission, one record, and all seven expected fields, including total 5,985 cents.
All seven browser assertions also passed. The evaluator inspected the saved screenshots.

Next, Jev checked two rendered views of that actual record. View A was correct. View B
had a seeded display defect: $69.85 instead of $59.85. The stored record was unchanged.
The fixture and expected answers were checked before model execution. Task, scoring
criteria, expected labels, and source hashes were frozen in `protocol.json`.

## Results

| Stage | Quality | Model responses | Input tokens | Output tokens | Wall time |
|---|---|---:|---:|---:|---:|
| Create invoice | Correct persisted record; 9/9 independent checks | 6 | 12,008 | 789 | 2.973 s |
| QA correct view | Correct pass; 3/3 model judgments | 1 | 1,084 | 126 | 1.910 s |
| QA defective view | Correct failure; 3/3 model judgments | 1 | 1,077 | 126 | 1.071 s |
| **Total** | **Creation passed; 6/6 QA judgments matched** | **8** | **14,169** | **1,041** | **5.954 s** |

The six QA judgments cover customer identity, quantity/price/total, and Draft/Unpaid status
on each view. Jev identified the wrong total and accepted the five correct conditions.
The deterministic checker independently failed only `#total` on the defective view.
The result therefore does not rely solely on the wrapper's deterministic failure status.

Total usage: **15,210 tokens**. Total measured model-call latency: **2.170 seconds**.
Wall time includes command startup, browser startup, observations, actions, model calls,
and cleanup. It excludes fixture construction, evaluator analysis, and report writing.
Tokens are the provider-reported Jev tokens. Parent Codex orchestration tokens are excluded.
Model-response counts do not establish billing or count any unreported transport attempts.

## What this establishes

The installed runner completed this small browser task and correctly reviewed its output
against supplied expectations. It detected the single seeded defect without rejecting the
correct view. Independent checks verified stored state, screenshots, source hashes, saved
judgments, and token totals.

This is one controlled case, not an estimate of general accuracy or repeatability.
Expected values and QA criteria were supplied. This does not test discovering requirements,
independent arithmetic reasoning, visual layout review, complex websites, or native subagent
dispatch. QA used observed browser text; screenshots were retained as evaluator evidence.
No billed cost is claimed.

## Evidence

- [Frozen protocol and source hashes](protocol.json)
- [Machine-readable results](results.json)
- [Stored invoice](server-state.json)
- [Independent creation checks](creation-oracle.json)
- [Creation report](create/report.json)
- [Correct-view QA report](qa-a/report.json) and [screenshot](qa-a/final.jpg)
- [Defective-view QA report](qa-b/report.json) and [screenshot](qa-b/final.jpg)
- [Runnable evaluation](evaluate.py): copy into a fresh sibling directory before rerunning.

The local fixture server and all browser sessions were closed after the runs.
