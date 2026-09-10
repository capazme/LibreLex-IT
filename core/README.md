# librelex-core

Local companion process of the LibreLex-IT LibreOffice extension. Speaks JSON-lines
over stdio with the extension, talks MCP to mcp-legal-it, runs the citation pipelines.

    uv sync            # create the environment (dev tools included)
    uv run pytest      # unit tests, no network
    uv run librelex-dev check-mcp   # handshake with the configured mcp-legal-it

## Dev CLI

    uv run librelex-dev check-mcp
    uv run librelex-dev verify path/to/atto.txt     # blank-line separated paragraphs
    uv run librelex-dev insert-norm "art. 2043 c.c."

Configuration: `~/Library/Application Support/LibreLex/config.toml` on macOS
(see the spec, Appendix D); `LIBRELEX_CONFIG` overrides the path.
