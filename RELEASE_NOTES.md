# Jev QA v0.2.0

Adds explicit checks for image overflow and cropping in verified browser journeys.

- `image_contained` checks whether visible image content stays inside a named ancestor container.
- `image_crop` checks that the full image is visible, or permits cropping with `expected: "allowed"`.
- Measurements account for intrinsic image size, borders, padding, standard `object-fit` values, supported `object-position` values, and rectangular ancestor clipping.
- Fractional dimensions are preserved before report rounding. Normal page scrolling does not count as cropping.
- Missing, unloaded, hidden, or unsupported images remain uncertain. Unsupported cases include transforms, masks, rounded clipping, complex positioning, root/body clipping, and non-default ancestor clip margins.

Checks must be included in the test contract. They do not inspect pixels, judge image content, or detect cropping already present in the source image.

Validation: all 68 local tests pass, including disposable Chrome image fixtures and regressions for extended clip margins, body overflow propagation, stylesheet clipping, and fractional cropping. The wheel and source distribution build successfully. Independent review findings were fixed and covered by regressions.

No paid model calls were made for this release. Retained v4 results are historical evidence, not a new live evaluation of v0.2.0.
