# Contributing to ha-vk

Thanks for considering a contribution.

## Before You Start

- Open an issue before large changes so the scope and approach can be discussed.
- Keep pull requests focused. Small, isolated changes are easier to review and release.
- Update documentation when behavior, setup, or user-facing examples change.
- Add or update tests when a focused test meaningfully reduces regression risk.

## Development Setup

1. Fork the repository and create a feature branch from `main`.
2. Create a Python 3.12 environment.
3. Install the tools you need for running tests and lint checks locally.
4. Make the change, then run the relevant validation before opening a pull request.

## Pull Request Checklist

- The change is described clearly in the pull request.
- Code follows the existing style of the repository.
- Tests were added or updated when appropriate.
- `README.md`, `README.en.md`, `TOKENS.md`, or `TOKENS.en.md` were updated if needed.
- The branch is up to date with `main`.

## Reporting Bugs

When opening a bug report, include:

- the Home Assistant version
- the integration version
- what you expected to happen
- what actually happened
- relevant logs with secrets removed
- a minimal reproduction if possible

## Feature Requests

Feature requests are welcome. Please describe:

- the problem you are trying to solve
- why the current behavior is insufficient
- the expected outcome
- any constraints from VK or Home Assistant that matter

## Security

Do not report security issues in public issues. Follow the process in `SECURITY.md`.