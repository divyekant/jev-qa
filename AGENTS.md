# Jev QA

<!-- APOLLO:START - Do not edit this section manually -->
## Project conventions
- Language: Python. Package manager: uv. Test framework: unittest.
- Use conventional commit messages and concise code.
- Test: `cd jev-qa && PYTHONPATH=. uv run --frozen python -m unittest discover -s tests`.
- Build: `uv build --project jev-qa`.
- Run relevant tests and check staged files for credentials before committing.
- Do not commit or publish without user authorization.
<!-- APOLLO:END -->

## Runtime and evidence boundaries
- Preserve Jev-only decisions, confidence guards, fresh observations, and meaningful postconditions.
- Use Luna for launch/report wrappers. A wrapper must not rescue failed browser actions with another model.
- Keep API keys in the private environment file, never tasks or source.
- Existing-Chrome mode owns new tabs only; never infer ownership from newly appearing user tabs.
- Keep historical evaluation records immutable. Add new results separately.
- A blocked check is untested, not a product defect. Unsupported artwork remains uncertain.
- Live evaluations make paid API calls. Local tests and doctor do not.
