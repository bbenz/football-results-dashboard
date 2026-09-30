# Contributing

Thanks for improving this demo. Contributions that make it easier to learn from, more correct, or easier to extend are welcome: fixes, clearer docs, tests, and new questions that follow the existing pattern.

## Ground rules

1. **No data in the repository, ever.** Not the Kaggle files, not extracts, samples, test snapshots, or notebook outputs. Tests use the small synthetic fixtures in `demo/tests/fixtures/synthetic/`, with fictional team names. Run `demo install-hook` once, so a git hook refuses any commit that would add data; CI runs the same check.
2. **Deterministic code owns every number.** A new insight is a typed, read-only tool with tests, not something the model computes. See [docs/HACKATHON-GUIDE.md](docs/HACKATHON-GUIDE.md#add-a-question-and-its-tool).
3. **No secrets.** The app uses Microsoft Entra ID everywhere and has no API keys. Settings go in `.env`, which git ignores; add every new setting to `.env.example` with a description.
4. **Same images everywhere.** Platform differences belong in the deployment definitions under `demo/infra/` and `demo/k8s/`, not in the code.

## Set up and check your change

Follow [docs/SETUP.md](docs/SETUP.md), then run:

```text
demo test
```

This runs the no-data guard, `ruff`, `mypy`, and `pytest`, and must pass before you open a pull request. If you change the operator scripts, change both `demo/scripts/*.ps1` and `demo/scripts/*.sh`: a test checks that the two offer the same commands.

## Pull requests

- Keep each pull request to one change, and explain why it's needed.
- Update the docs in the same pull request as the change that makes them true.
- If you change a method or its parameters, update [docs/METHODS.md](docs/METHODS.md) and the tool's method version.
- Describe how you tested the change. For Azure changes, say which commands you ran and on which platform.

## Reporting problems

Open an issue with what you ran, what you expected, and what happened. For security problems, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

By contributing, you agree that your contribution is licensed under the [MIT License](LICENSE), and you agree to follow the [code of conduct](CODE_OF_CONDUCT.md).
