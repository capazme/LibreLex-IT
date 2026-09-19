# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import json
from pathlib import Path

import pytest

from librelex_core.agent.internal_tools import INTERNAL_TOOLS, run_internal_tool
from librelex_core.agent.profiles import (
    CALCULATORS,
    CASE_LAW,
    GENERATORS,
    GROUNDING_SOURCES,
    NORM_SOURCES,
    PROFILES,
)
from librelex_core.agent.registry import (
    DOCUMENT_TOOLS,
    ToolRegistry,
    compact_schema,
    concise,
    load_overrides,
)
from librelex_core.mcp.client import ALLOWLIST, ToolSpec

_FIXTURES = Path(__file__).parent / "fixtures"


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
    assert GENERATORS == ("decreto_ingiuntivo", "atto_di_precetto", "sollecito_pagamento",
                          "procura_alle_liti", "relata_notifica_pec", "attestazione_conformita",
                          "sfratto_morosita", "nota_precisazione_credito", "dichiarazione_553_cpc")
    assert len(CALCULATORS) == 8
    assert PROFILES["draft"].legal == (
        "genera_modello_atto", "lista_categorie_atti", "cite_law", "fetch_act_index",
        "verifica_citazioni") + GENERATORS + CALCULATORS
    assert set(PROFILES["draft"].legal) <= ALLOWLIST
    assert PROFILES["draft"].document == ("read_paragraphs", "insert_markdown")
    assert PROFILES["review"].document == ("read_selection", "replace_selection", "add_comment")


def test_grounding_sources_are_exactly_the_source_reading_tools():
    """Finding 1 (final-review fix wave): grounding may only come from tools that read a
    source, not from tools that echo the model's own parameters (spec §6.6 item 1)."""
    assert NORM_SOURCES == ("cite_law", "fetch_act_index", "fetch_full_act", "cerca_brocardi")
    assert GROUNDING_SOURCES == frozenset(NORM_SOURCES + CASE_LAW)
    assert len(GROUNDING_SOURCES) == 15
    assert GROUNDING_SOURCES <= ALLOWLIST


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


def test_compact_schema_keeps_core_keys_and_drops_the_rest():
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "Input",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "q": {"type": "string", "title": "Q", "description": "Testo.", "examples": ["a"]},
            "ambito": {"type": "string", "title": "Ambito", "default": "tutti",
                       "enum": ["civile", "penale", "tutti"]},
        },
        "required": ["q"],
        "examples": [{"q": "x"}],
    }
    out = compact_schema(schema)
    assert out == {
        "type": "object",
        "properties": {"q": {"type": "string", "description": "Testo."},
                       # enum and default are what the model needs to call the tool: kept
                       "ambito": {"type": "string", "enum": ["civile", "penale", "tutti"],
                                  "default": "tutti"}},
        "required": ["q"],
    }
    assert out["properties"]["ambito"]["enum"] == ["civile", "penale", "tutti"]


def test_compact_schema_truncates_descriptions_at_a_word_boundary():
    schema = {"type": "string", "description": "Valori disponibili: alfa beta gamma delta epsilon"}
    out = compact_schema(schema, max_desc=20)
    assert out["description"] == "Valori disponibili:…"
    assert len(out["description"]) <= 21


def test_compact_schema_leaves_short_descriptions_untouched():
    out = compact_schema({"type": "string", "description": "Breve."}, max_desc=120)
    assert out["description"] == "Breve."


def test_compact_schema_recurses_and_deep_copies():
    schema = {
        "type": "object",
        "properties": {
            "tags": {
                "type": "array",
                "title": "Tags",
                "items": {"type": "string", "title": "Tag", "description": "x" * 200},
            },
        },
    }
    out = compact_schema(schema, max_desc=50)
    assert "title" not in out["properties"]["tags"]
    item = out["properties"]["tags"]["items"]
    assert "title" not in item
    assert len(item["description"]) <= 51
    out["properties"]["tags"]["items"]["description"] = "mutated"
    assert schema["properties"]["tags"]["items"]["description"] == "x" * 200


def test_registry_compacts_legal_tool_parameter_schemas():
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "sede": {"type": "string", "title": "Sede", "description": "y" * 500},
        },
        "additionalProperties": False,
    }
    specs = [ToolSpec("cerca_giurisprudenza_amministrativa", "desc", schema)]
    reg = ToolRegistry(specs, "research")
    tool = next(t for t in reg.tools
                if t["function"]["name"] == "cerca_giurisprudenza_amministrativa")
    params = tool["function"]["parameters"]
    assert "$schema" not in params and "additionalProperties" not in params
    assert "title" not in params["properties"]["sede"]
    assert len(params["properties"]["sede"]["description"]) <= 121


def test_research_profile_tools_array_stays_under_30k_chars():
    data = json.loads((_FIXTURES / "tool_specs_sample.json").read_text(encoding="utf-8"))
    raw_sede = next(t for t in data
                     if t["name"] == "cerca_giurisprudenza_amministrativa")
    assert len(raw_sede["input_schema"]["properties"]["sede"]["description"]) >= 1000

    specs = [ToolSpec(t["name"], t["description"], t["input_schema"]) for t in data]
    reg = ToolRegistry(specs, "research")
    encoded = json.dumps(reg.tools, ensure_ascii=False)
    assert len(encoded) < 30_000

    sede = next(t for t in reg.tools
                if t["function"]["name"] == "cerca_giurisprudenza_amministrativa"
                )["function"]["parameters"]["properties"]["sede"]
    assert sede["description"].endswith("…")
    assert len(sede["description"]) <= 121
    assert set(reg.names) == set(PROFILES["research"].legal) | set(PROFILES["research"].document) \
        | {t["function"]["name"] for t in INTERNAL_TOOLS}


def test_internal_tools():
    assert [t["function"]["name"] for t in INTERNAL_TOOLS] == ["data_odierna", "estrai_citazioni"]
    out = json.loads(run_internal_tool(
        "estrai_citazioni", {"testo": "Vedi art. 2043 c.c. e Cass. n. 1/2024."}))
    assert [c["citazione"] for c in out] == ["art. 2043 c.c.", "Cass. n. 1/2024"]
    assert len(run_internal_tool("data_odierna", {})) == 10
    with pytest.raises(KeyError):
        run_internal_tool("nope", {})
