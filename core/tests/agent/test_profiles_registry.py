# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import json

import pytest

from librelex_core.agent.internal_tools import INTERNAL_TOOLS, run_internal_tool
from librelex_core.agent.profiles import CALCULATORS, PROFILES
from librelex_core.agent.registry import DOCUMENT_TOOLS, ToolRegistry, concise, load_overrides
from librelex_core.mcp.client import ALLOWLIST, ToolSpec


def test_profiles_match_spec_6_3():
    assert set(PROFILES) == {"chat", "research", "draft", "review"}
    assert set(PROFILES["chat"].legal) == ALLOWLIST
    assert set(PROFILES["chat"].document) == set(DOCUMENT_TOOLS) - {"remove_comments"}
    assert set(PROFILES["research"].legal) == {
        "cerca_giurisprudenza", "cerca_giurisprudenza_unificata", "leggi_sentenza",
        "giurisprudenza_su_norma", "orientamento_su_norma", "cerca_giurisprudenza_amministrativa",
        "leggi_provvedimento_amm", "cerca_giurisprudenza_cgue", "leggi_sentenza_cgue",
        "cerca_pronuncia_costituzionale", "leggi_pronuncia_costituzionale", "cite_law"}
    assert PROFILES["research"].document == (
        "read_selection", "read_paragraphs", "insert_markdown")
    assert len(CALCULATORS) == 8 and set(CALCULATORS) <= set(PROFILES["draft"].legal) <= ALLOWLIST
    assert PROFILES["review"].document == ("read_selection", "replace_selection", "add_comment")


def test_overrides_cover_the_allowlist_and_are_concise():
    ov = load_overrides()
    assert set(ov) == ALLOWLIST
    assert all(0 < len(v) <= 300 for v in ov.values())
    long = ToolSpec(
        "cerca_giurisprudenza", "Primo paragrafo.\n\nSecondo paragrafo lunghissimo " * 50, {})
    assert concise(long, {}) == "Primo paragrafo."
    assert concise(long, ov) == ov["cerca_giurisprudenza"]
    assert len(concise(ToolSpec("x", "y" * 1000, {}), {})) == 300


def test_registry_orders_groups_and_is_byte_stable():
    names_in = ("leggi_sentenza", "cite_law", "cerca_giurisprudenza", "contributo_unificato")
    specs = [ToolSpec(n, f"desc {n}", {"type": "object", "properties": {"q": {"type": "string"}}})
             for n in names_in]
    reg = ToolRegistry(specs, "research")
    names = [t["function"]["name"] for t in reg.tools]
    assert names == ["cerca_giurisprudenza", "cite_law", "leggi_sentenza",
                     "insert_markdown", "read_paragraphs", "read_selection",
                     "data_odierna", "estrai_citazioni"]
    assert reg.kind("cite_law") == "legal" and reg.kind("insert_markdown") == "document"
    assert reg.kind("data_odierna") == "internal"
    with pytest.raises(KeyError):
        reg.kind("contributo_unificato")           # not in the research profile
    reversed_reg = ToolRegistry(list(reversed(specs)), "research")
    assert json.dumps(reg.tools, sort_keys=True) == json.dumps(reversed_reg.tools, sort_keys=True)
    legal = next(t for t in reg.tools if t["function"]["name"] == "cite_law")
    assert legal["function"]["parameters"] == specs[1].input_schema
    assert legal["function"]["description"] == load_overrides()["cite_law"]


def test_document_tools_mirror_the_actions():
    assert set(DOCUMENT_TOOLS) == {"get_document_info", "read_selection", "read_paragraphs",
                                   "find_text", "insert_markdown", "replace_selection",
                                   "add_comment", "remove_comments", "goto"}
    ins = DOCUMENT_TOOLS["insert_markdown"]["function"]["parameters"]
    assert set(ins["required"]) == {"where", "markdown"}
    assert ins["properties"]["where"]["type"] == "string"
    rp = DOCUMENT_TOOLS["read_paragraphs"]["function"]["parameters"]["properties"]
    assert set(rp) == {"from_", "to"}


def test_internal_tools():
    assert [t["function"]["name"] for t in INTERNAL_TOOLS] == ["data_odierna", "estrai_citazioni"]
    out = json.loads(run_internal_tool(
        "estrai_citazioni", {"testo": "Vedi art. 2043 c.c. e Cass. n. 1/2024."}))
    assert [c["citazione"] for c in out] == ["art. 2043 c.c.", "Cass. n. 1/2024"]
    assert len(run_internal_tool("data_odierna", {})) == 10
    with pytest.raises(KeyError):
        run_internal_tool("nope", {})
