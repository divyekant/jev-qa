# Jev QA v0.3.0

Adds a rule-based page audit to verified browser journeys.

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

The audit makes no model call. It measures one viewport and one page state. It does not inspect pixels or judge visual taste.

The `jev-ultrafast` pin moves from `452c1ad` to `1231850`. That upstream change is documentation only. Jev decisions continue to use the `jev-latest` model alias. TypeSafe serves the current Jev model through that alias, so a Jev model update needs no change in this repository.

Validation: all 73 local tests pass. These include disposable Chrome fixtures for a clean page, a page with eleven seeded defects, and twelve regressions from an independent review. Read-only audits of two public pages found no new false failures after the fixes. The wheel and source distribution build successfully.

No paid model calls were made for this release. Retained v4 results are historical evidence, not a new live evaluation of v0.3.0.
