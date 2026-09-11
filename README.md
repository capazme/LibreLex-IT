# LibreLex-IT

AI copilot for LibreOffice Writer, for Italian legal drafting, grounded on
official sources through [mcp-legal-it](https://github.com/capazme/mcp-legal-it).

Status: M1 complete (verify citations, insert norm from the sidebar; no LLM yet).
Design: `docs/superpowers/specs/2026-09-07-librelex-it-design.md`.

## Install (macOS, LibreOffice 26.2+)

1. Install [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`).
2. From a Terminal: `scripts/dev_install.sh` (builds `dist/LibreLex-IT-<version>.oxt` and runs `unopkg add --force`).
3. Quit and restart LibreOffice. In Writer: View > Sidebar > LibreLex > Copilota legale.
4. First click creates `~/Library/Application Support/LibreLex/config.toml` (0600). Edit `[mcp_legal_it] command`
   if you run mcp-legal-it from a local checkout; LibreOffice must be restarted after changes.

The first action runs `uv run` on the bundled core: network access is needed once to build its environment.
Logs of the core process: `~/Library/Application Support/LibreLex/core-stderr.log` (no document text).

- `core/` — the local Python process (`librelex-core`), see `core/README.md`
- `extension/` — the LibreOffice `.oxt` sources (`uv run pytest` there; headless adapter tests need `soffice`)
- `scripts/` — `build_oxt.py`, `dev_install.sh`
- `spike/` — throwaway probes from Phase 0, kept for reproducibility

License: Apache-2.0 (see `NOTICE` for MPL-2.0 and MIT parts).
