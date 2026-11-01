# Jev QA v0.3.0

Adds a rule-based page audit and advisory Jev screenshot review to verified browser journeys.

## Jev screenshot review

- A `visual` check sends Jev one screenshot of the viewport, or of the region around an element, with one criterion.
- The request uses TypeSafe's `assets` map and the required `TypeSafe-Danger-Zone-Images: true` header. Each image goes in its own request and question.
- Images are captured as PNG, downscaled to at most 1568 px on each side, and sent as JPEG. Element regions are at least 280 × 280 CSS px, the TypeSafe minimum.
- Visual judgments are advisory. They cannot pass or fail a report, and they cannot override a rule result.
- Each step folder keeps the sent image as `visual-NN.jpg`.
- TypeSafe calls image input experimental. Navigation decisions still use text only.

## Page audit

- An `audit` design check examines each visible element in a page or component. No selector list is necessary.
- Existing rules apply to each element: text clipping, text contrast, and pointer obstruction.
- New rules check text overlap, accessible names, WCAG 2.5.8 target size, image `alt` text, broken images, page language, page title, and horizontal fit.
- Large text uses a separate contrast minimum, 3.0 by default. Disabled controls are exempt from contrast.
- Each finding has a unique CSS selector, so it can become an explicit check.
- Unsupported elements and a truncated sweep make the audit uncertain, never a pass.
- Contrast checks, explicit and audit, now measure text with no painted background against the default white canvas. If the page can use a dark or forced-colors scheme, the result stays uncertain. Before this change, text with no painted background was always uncertain.
- Contrast checks, explicit and audit, now confirm the backdrop at the element centre. If another layer paints between the text and its ancestor background, the result is uncertain. Before this change, such text could pass incorrectly.
- Shadow roots, frames, and `display: contents` text are reported as uncertain. They are never passed silently.
- The sweep stops after 3 seconds or 50 overlapping text pairs, and it reports the reason.

The audit makes no model call. It measures one viewport and one page state. Add `visual` checks to judge appearance.

The `jev-ultrafast` pin moves from `452c1ad` to `1231850`. That upstream change is documentation only. Jev decisions continue to use the `jev-latest` model alias. TypeSafe serves the current Jev model through that alias, so a Jev model update needs no change in this repository.

Validation: all 79 local tests pass. A live smoke test of the example form sent two images to `jev-1.13.0`. TypeSafe accepted both requests: one element check passed at 0.92 confidence, and one compound page check was uncertain. These include disposable Chrome fixtures for a clean page, a page with eleven seeded defects, and twelve regressions from an independent review. Read-only audits of two public pages found no new false failures after the fixes. The wheel and source distribution build successfully.

Apart from that smoke test, no paid model calls were made for this release. Retained v4 results are historical evidence, not a new live evaluation of v0.3.0.
