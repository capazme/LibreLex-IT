# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Run the fake mcp-legal-it of tests/conftest.py as a stdio MCP server.

Used by the extension's integration tests as the `[mcp_legal_it] command`:
    uv run --project core python core/tests/fake_legal_server.py
Verdicts: "Cass. n. 99999/2024" is inesistente; everything else verificata.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # core/ → import tests.conftest

from tests.conftest import make_fake_legal_server  # noqa: E402

if __name__ == "__main__":
    server, _ = make_fake_legal_server(
        verdicts={"Cass. n. 99999/2024": ("inesistente", "nessuna decisione con questo numero")})
    server.run(transport="stdio", show_banner=False)
