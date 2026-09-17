# Validation — 2026-09-17

## v4 update

The [v4 report](../jev-design-eval-v4/REPORT.md) records 61 passing local tests,
independent Luna review, three unchanged eight-case regression passes, and four fresh-page
passes. All 304 checkpoints and 224 supported checks completed correctly. All 48 seeded
defect instances were detected. The actual existing-Chrome synthetic session probe passed;
a no-model integration test also covers helper crashes, concurrent user tabs, and cookie preservation.
The report retains every failed development attempt and separates Jev, browser, and wrapper time.
Native custom-role discovery still requires a fresh session; the measured wrapper reused a Luna agent.

## v3 update

The [v3 report](../jev-design-eval-v3/REPORT.md) records 56 passing local tests, independent
Luna review, 6/8 completed journeys, 86/88 checkpoints, and a successful local authenticated
session probe in the user's running Chrome. Two final mobile checkpoints remain blocked.
All earlier records below are historical evidence.

## Journey update

The reusable journey runner, installed skill, and Luna wrapper were validated separately.
See the [v2 report](../jev-design-eval-v2/REPORT.md). It records 38 passing tests, a real Luna
wrapper smoke test, complete desktop journeys, and unresolved mobile navigation failures.
The installed role now pins `gpt-5.6-luna`; native role discovery still needs a fresh session.
The earlier results and fingerprints below remain historical evidence.

## Initial runner validation

Final checks: 12 tests passed, Ruff passed, and wheel/source distribution built.
Independent review found no remaining material issue after fixes.
Browser tests exercise normal teardown and interrupted-run teardown with real Chrome.
No owned browser processes remained after the tests.

## Live trials

All browser trials used the local fictional form fixture and the direct TypeSafe API.
They are small development smoke tests, not a quality or speed benchmark.

| Run directory under `runs/` | Outcome | Elapsed milliseconds |
|---|---|---:|
| `empty-form-live-1` | `needs_review` | 13781 |
| `filled-form-live-1` | `pass` | 2441 |
| `broken-form-live-1` | `fail` | 1765 |
| `evidence-review-live-1` | `needs_review` | Not recorded |
| `filled-form-final` | `pass` | 1899 |

The empty-form trial clicked Subscribe and observed the correct validation message. Low
confidence in completion and the semantic judgment correctly prevented a verified pass.
The broken fixture accepted an empty email; its required-error assertion failed.
The evidence-only review identified the violation but retained overall `needs_review`.

The final valid-form run filled Email and clicked Subscribe. Both assertions passed.
It used `jev-1.13.0`: four requests, 6,300 input tokens, and 366 output tokens.
Provider call times were 307, 335, 159, and 261 milliseconds. Total elapsed time was
1,899 milliseconds. These token counts do not establish billed cost.

Earlier browser reports have truncated token fields due to a serialization bug found
and fixed during validation. They remain unchanged as development evidence. The final
report retains numeric usage, verified after reading the saved file.

## Installation

Global launcher and installed `jev_qa` role match the delivered source copies.
The private credential has mode 600. A secret scan found no key in the deliverable.
Native role dispatch remains unverified: Codex CLI 0.146.0 rejected its configured
`gpt-6-astra` model and required a client upgrade. The global runner works independently.

## Final source fingerprints

These identify the code used by `filled-form-final`.

- `jev_qa/__init__.py`: `cc3cd6a42f3a313e7ed621dee14d34fe9d4e2b1fd77fc028d78aecb8f59aa07f`
- `jev_qa/__main__.py`: `1f7b1dd4fa90bc998f3f58295280a246b95a0331594eb57f67beff76a933e50d`
- `jev_qa/browser.py`: `0a53bd62fab2b53e1599b514963efe7c732ed13ded7424de9525ba42a245bb5e`
- `jev_qa/runner.py`: `38f0dcc477e3276539837b03adac3337a23e5ecd43bb01fa3c0f925c3ff09bf1`
