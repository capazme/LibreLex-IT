<!-- One logical change per PR. Title in Conventional Commits form: feat(core): ..., fix(extension): ... -->

## What

<!-- The change in two or three sentences. Link the issue or the spec section it implements. -->

Closes #

## Why

<!-- The problem it solves or the behaviour it changes. If it departs from the design spec, say why. -->

## How it was tested

<!-- Unit tests added or changed; whether the headless tests ran (`uv run pytest -m headless`);
     manual check in Writer if the sidebar or the document actions are involved. -->

## Checklist

- [ ] `uv run ruff check .` and `uv run pytest -q` pass in the project(s) I touched
- [ ] The extension stays stdlib-only; dependencies went in the core, if any
- [ ] No document text or secret reaches the logs, and nothing new is sent without the consent step
- [ ] `CHANGELOG.md` has a line under *Unreleased* if the change is user-visible
- [ ] No real client data anywhere in the diff, the fixtures or this description
