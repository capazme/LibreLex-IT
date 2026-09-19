# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""The Redazione panel's pure helpers, exercised inside LibreOffice: importing
`librelex_ext.panel` pulls in the UNO types (drop target included), so this can only run
under soffice, and the probe doubles as proof that the module still imports there."""
import pytest

from tests.headless.conftest import run_probe

pytestmark = pytest.mark.headless


def test_panel_helpers_import_inside_libreoffice_and_behave(soffice):
    out = run_probe(soffice, "panel_helpers", '''
    from librelex_ext.panel import collect_fields, first_file_uri

    def probe(ctx, out):
        out["fields"] = collect_fields(["creditore", "importo", "note"], [" Alfa ", "", "12.000"])
        out["uri_bytes"] = first_file_uri(b"file:///Users/x/ricorso%20rossi.docx\\r\\nfile:///y.odt\\r\\n")
        out["uri_str"] = first_file_uri("https://example.org/x.docx\\n")
        out["uri_none"] = first_file_uri(None)
    ''')
    assert out["fields"] == {"creditore": "Alfa", "note": "12.000"}
    assert out["uri_bytes"] == "file:///Users/x/ricorso%20rossi.docx"
    assert out["uri_str"] is None and out["uri_none"] is None
