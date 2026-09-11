# LibreLex-IT

AI copilot for LibreOffice Writer, for Italian legal drafting, grounded on
official sources through [mcp-legal-it](https://github.com/capazme/mcp-legal-it).

Status: M1 in progress (core pipelines: verify citations, insert norm).
Design: `docs/superpowers/specs/2026-09-07-librelex-it-design.md`.

- `core/` — the local Python process (`librelex-core`), see `core/README.md`
- `extension/` — the LibreOffice `.oxt` (next milestone)
- `spike/` — throwaway probes from Phase 0, kept for reproducibility

License: Apache-2.0 (see `NOTICE` for MPL-2.0 and MIT parts).
