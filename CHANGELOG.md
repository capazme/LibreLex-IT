# Changelog

All notable changes to LibreLex-IT are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) while in alpha (`0.x`: minor bumps may break).

The version is the extension's (`extension/description.xml`); the core's own version is
noted per release.

## [Unreleased]

### Added

- Community files: contributing guide, code of conduct, security policy, issue and pull
  request templates, Dependabot, a `release` workflow that publishes the `.oxt` on a tag.

## [0.5.0] - 2026-09-19

Core 0.3.0. Milestone M3: template-guided drafting.

### Added

- **Redigi da modello** button and the `draft` command: the model looks the act template up
  in mcp-legal-it, reads the document with consent, asks in Risposte for the data it still
  needs, then inserts the act section by section as redlines, leaving `[...]` where nobody
  supplied a value; "continua" resumes a drafting cut by the iteration limit.
- Nine court-act generators of mcp-legal-it in the drafting allowlist, so amounts (interests,
  revaluation, contributo unificato, fees) come from the calculators, not from the model.
- Grounding sources: only source-reading tools count as grounding for a reference written
  into the document; anything else is verified before insertion.
- `librelex-dev draft` in the dev CLI.

### Fixed

- The `.oxt` ships every file of the core package, not only `*.py`: the tool description
  overrides in `agent/tool_overrides.toml` were missing from the installed core.
- A draft resumes from the first missing partition instead of restarting.

## [0.4.0] - 2026-09-12

Core 0.2.1. Milestone M2: chat and research. (0.3.0 was an internal step, never released.)

### Added

- Three native sidebar panels sharing one session: **Azioni** (buttons, progress, status),
  **Citazioni** (references with verdicts) and **Risposte** (answers).
- **Invia**: chat turns with streamed answers; the model can consult the sources, read the
  document with consent and write into it as a redline. *Annulla* stops a running turn and
  keeps the partial text.
- **Ricerca**: the same turn restricted to case-law search.
- In-panel consent block: what is sent, to whom, whether the routing is zero-data-retention;
  per document, once, or refuse.
- Usage line after every turn (turn and session tokens, cost when the provider reports it).
- Core: streaming LLM client over the OpenAI SDK with the `openrouter`, `cliproxyapi`,
  `ollama` and `custom` presets and `zero_data_retention`; tool registry with profiles and
  concise descriptions; agent loop with consent routing, limits, cancellation and grounding
  on write; document sessions with history compaction and a session token ceiling;
  `librelex-dev chat`.

### Fixed

- Consent choices laid out on two rows so the labels fit; turn notes, usage line and pending
  consent stay visible; a cancelled turn still reports its usage.
- Dangling tool calls are closed and unverified references signalled.
- Bare articles chained to an act written in the same insertion are verified.

## [0.2.0] - 2026-09-11

### Added

- **Elenca citazioni**: the references of the document without consulting any source;
  clicking an entry jumps to its first occurrence and shows its text.
- **Mostra testo**: the current text of a norm, a Cassazione judgment or a Corte
  costituzionale decision in the panel.
- Citation list with verdict markers (✓ ✗ ? ·) and a text cache; sectioned responsive
  panel with progress bar, tooltips and a clear button.
- Core: `list_citations` and `show_text` commands; mcp-legal-it is accepted by its JSON
  contract (`formato` parameter) instead of a version number.

### Fixed

- The extension is registered in-process through a headless LibreOffice macro: `unopkg add`
  hangs on some macOS installs (`NoConnectException`).
- Cached citation text is shown while the core is busy; wider deck minimum.

## [0.1.0] - 2026-09-11

First release. Milestone M1: citations.

### Added

- Sidebar panel with **Verifica citazioni**, **Verifica selezione** and **Inserisci norma**,
  problem-list navigation and per-document sessions.
- Tracked Markdown insertion under the `librelex` author with undo context and bookmark;
  Writer comments anchored to the verified text, orphan removal, removal by author.
- Stdio bridge to `librelex-core` with reader thread and exit detection.
- Core: legal tools client over fastmcp with version check; norm and judgment citation
  extractors (Cassazione, Corte costituzionale, Consiglio di Stato, TAR, CGUE) with canonical
  forms; citation verifier with batching, bounded concurrency and one retry;
  `verify_citations` and `insert_norm` commands with provenance; stdio server with
  handshake, per-document requests and cancellation; `librelex-dev` CLI.
- `scripts/build_oxt.py`, `scripts/dev_install.sh`, headless end-to-end test, CI.

[Unreleased]: https://github.com/capazme/LibreLex-IT/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/capazme/LibreLex-IT/releases/tag/v0.5.0
[0.4.0]: https://github.com/capazme/LibreLex-IT/commit/5649cc0
[0.2.0]: https://github.com/capazme/LibreLex-IT/commit/682b47a
[0.1.0]: https://github.com/capazme/LibreLex-IT/commit/c965bc1
