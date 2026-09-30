# Contributing to LibreLex-IT

Thanks for helping. This page tells you how to set the project up, what the conventions are
and what a good pull request looks like. Questions that are not bugs go to
[Discussions](https://github.com/capazme/LibreLex-IT/discussions).

## What is welcome

- Bug reports with the steps to reproduce (see the issue template).
- Fixes and features that follow an issue or a design doc in `docs/superpowers/specs/`.
  For anything larger than a small fix, open an issue first so we agree on the approach.
- Citation patterns the extractor misses, act templates, calculator wiring: most of the legal
  content lives in [mcp-legal-it](https://github.com/capazme/mcp-legal-it), so check which of
  the two repositories the change belongs to.
- Testing on Linux and Windows. The code paths exist, the installs are untested.
- Documentation. The docs are in English; the user interface is in Italian.

**Never put real client documents or personal data in an issue, a test fixture, a log
excerpt or a pull request.** Use invented facts and names. This is a GDPR matter, not a
style preference.

## Development setup

You need [uv](https://docs.astral.sh/uv/) and, for the headless tests, LibreOffice 26.2 or
later. The repository has two Python projects that are tested separately:

```bash
git clone https://github.com/capazme/LibreLex-IT.git && cd LibreLex-IT

# core: the local process (citation pipelines, agent loop, stdio protocol)
cd core
uv sync                       # environment with the dev tools
uv run ruff check .
uv run pytest -q              # 190+ unit tests, no network
uv run librelex-dev --help    # the pipelines from the command line, without LibreOffice
cd ..

# extension: the LibreOffice side (stdlib only; LibreOffice's Python has no pip)
cd extension
uv sync
uv run ruff check .
uv run pytest -q -m "not headless"   # pure-Python tests
uv run pytest -q -m headless         # runs macros inside `soffice --headless`; skipped when absent
cd ..

# the .oxt, then a headless LibreOffice registers it (LibreOffice must be closed)
python3 scripts/build_oxt.py --out dist
scripts/dev_install.sh        # --remove uninstalls, --profile DIR targets a private profile
```

Tests marked `live` in the core hit a real mcp-legal-it or government sources and are
deselected by default. `core/README.md` documents the dev CLI.

## Conventions

- **Python 3.12+**, `ruff` with the rules in each `pyproject.toml` (`E, F, I, UP, B`, line
  length 100). CI runs ruff and pytest on both projects; a PR with a red check does not
  merge.
- **The extension stays stdlib-only.** It runs inside LibreOffice's bundled Python. Anything
  that needs a dependency goes in the core and is reached over the stdio protocol.
- **Code, comments, commit messages and docs in English; UI strings in Italian.**
- **Tests come with the change.** Write the failing test first when you can; pure logic is
  unit-tested, UNO calls are covered by the headless probes in `extension/tests/headless/`.
- **Do not send document text anywhere new without going through the consent channel**,
  and do not log it. `core-stderr.log` must stay free of document content and API keys.
- Files derived from LibreThinker keep their MPL-2.0 header (see `NOTICE`). New files carry
  the Apache-2.0 header used across the repository.

### Commits and branches

[Conventional Commits](https://www.conventionalcommits.org/) with the scopes in use:
`core`, `extension`, `scripts`, `build`, `ci`, `docs`, `spec`, `plan`.

```
feat(core): verify bare articles chained to an act written in the same insertion
fix(extension): keep turn notes, usage line and pending consent visible
docs(spec): guided drafting: catalogue resources use the legal:// scheme
```

Branches: `feature/<topic>`, `fix/<topic>`, `refactor/<topic>`, `chore/<topic>`.

### Pull requests

1. One logical change per PR, described in the template: what, why, how it was tested.
2. Add a line under `## [Unreleased]` in `CHANGELOG.md` when the change is user-visible.
3. Do not bump versions in a feature PR: the version lives in `extension/description.xml`,
   `extension/librelex_ext/__init__.py` (must match, `build_oxt.py` checks) and
   `core/pyproject.toml`, and changes in a release PR.
4. CI must be green. The `headless` job is best effort and does not block.

## Design docs

`docs/superpowers/specs/` holds the design specifications and `docs/superpowers/plans/` the
implementation plans that were followed. The spec is the source of truth for scope: when a
change departs from it, update the spec in the same PR or explain why in the description.

## Releasing (maintainers)

1. Bump the three version strings above and move the `Unreleased` entries of `CHANGELOG.md`
   under the new version with today's date.
2. Merge to `main`, then tag: `git tag -a v0.6.0 -m "v0.6.0" && git push origin v0.6.0`.
3. The `release` workflow checks that the tag matches the extension version, runs the tests,
   builds the `.oxt` and publishes a GitHub Release with the `.oxt`, its `.sha256` and the
   changelog section as notes.

## License

By contributing you agree that your contribution is licensed under the Apache License 2.0,
like the rest of the project. No CLA is needed.
