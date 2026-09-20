# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
from librelex_core.agent.textclean import clean_tool_names

NAMES = ["contributo_unificato", "scadenza_processuale", "cite_law", "leggi_allegato"]


def test_prefixes_are_stripped_only_for_known_names():
    text = ("Calcolo con mcp__trade_dress__swamp_contributo_unificato e "
            "mcp__trade_dress__hello_scadenza_processuale; poi mcp__x__cite_law. "
            "Non tocco mcp__trade_dress__swamp_altro_strumento.")
    out = clean_tool_names(text, NAMES)
    assert out == ("Calcolo con contributo_unificato e scadenza_processuale; poi cite_law. "
                   "Non tocco mcp__trade_dress__swamp_altro_strumento.")
    plain = "Uso contributo_unificato e basta."
    assert clean_tool_names(plain, NAMES) is plain
