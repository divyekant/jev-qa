# Jev QA

Jev-only browser user acceptance testing (UAT) and measured design conformance checks, with an optional Luna wrapper.

The retained v4 evaluation passed 28/28 synthetic journeys, 304/304 checkpoints, 224/224 supported design checks, and 48/48 seeded-defect instances. These historical results are bounded tests, including repeated defects, not a general reliability rate or a new evaluation of v0.2.0. Artwork judgment and dedicated nested-container scrolling remain unsupported.

## Start

Requires Python 3.12+, `uv`, and Google Chrome. From this repository:

```sh
uv sync --frozen --project jev-qa
./jev-qa/jev-qa doctor
./jev-qa/jev-qa journey /path/to/task.json --output work/qa-result
```

Store `TYPESAFE_API_KEY` in `~/.config/jev-qa/env` with mode `600`, or supply it through the environment. Never commit credentials. No paid model call is needed for `doctor` or the unit tests.

```sh
cd jev-qa
PYTHONPATH=. uv run --frozen python -m unittest discover -s tests
uv build
```

For an explicitly authorized signed-in browser task, add `--browser existing-chrome`. It uses a new owned tab in the running Chrome profile. Chrome may require the user to allow remote debugging. See the [runner guide](jev-qa/README.md).

## Contents

- [Runner, task schema, and setup](jev-qa/README.md)
- [Workflow and Jev's role](jev-qa/WALKTHROUGH.md)
- [Reusable skill](jev-qa/skill/SKILL.md) and [Luna role](jev-qa/jev-qa.toml)
- [Current v4 evaluation](jev-design-eval-v4/REPORT.md), fixtures, raw results, and failed development attempts
- Earlier design evaluations: [v1](jev-design-eval/REPORT.md), [v2](jev-design-eval-v2/REPORT.md), [v3](jev-design-eval-v3/REPORT.md)
- [Invoice evaluation](jev-invoice-eval/REPORT.md) and [computer-use comparison](computer-use-invoice-eval/COMPARISON.md)

The sibling directory layout is retained so evaluation scripts and relative evidence links keep working. The Python package is in `jev-qa/`.

## Migration and evidence

This project was copied from `/Users/dk/Documents/Codex/2026-09-17/ok-x20/outputs` to `/Users/dk/projects/jev-qa`. Replace the old `outputs` prefix with this repository root to locate a historical file. Original outputs remain an archive; the installed launcher and skill use this project.

[MIGRATION.json](MIGRATION.json) records hashes before relocation-only edits. Historical JSON, reports, screenshots, and source fingerprints retain their original contents and absolute paths. They are evidence of the earlier runs, not newly measured performance after migration. The migration preserved runtime Python source and fixture behavior; subsequent runtime fixes are recorded in Git.

The committed browser evidence comes from fictional local fixtures. New run folders are ignored by default because browser evidence can contain page text and form values. Check content before deliberately adding any new evidence. Virtual environments, caches, build products, credentials, and browser profiles are not source artifacts.

On this machine, `/Users/dk/.local/bin/jev-qa`, the installed skill, and the installed Luna role point to this project. A fresh Codex session may be needed to discover the native `jev_qa` role. The documented explicit Luna wrapper remains the fallback.

Verify the retained v4 evidence without model calls:

```sh
jev-qa/.venv/bin/python scripts/verify_v4.py \
  jev-design-eval-v4/runs/regression-20260917T232922Z \
  jev-design-eval-v4/runs/regression-20260917T233051Z \
  jev-design-eval-v4/runs/regression-20260917T233222Z \
  jev-design-eval-v4/runs/fresh-20260917T233335Z
```

Git does not preserve owner-only file modes. The verifier reports current archive permissions separately from the acceptance result; new runtime evidence still uses owner-only permissions.
