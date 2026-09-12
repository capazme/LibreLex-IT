# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
from librelex_core import protocol as p
from librelex_core.agent.loop import AgentDeps
from librelex_core.agent.registry import ToolRegistry
from librelex_core.agent.state import DocSession
from librelex_core.commands.chat import run_chat
from librelex_core.commands.research import research_prompt, run_research
from librelex_core.config import LimitsConfig
from librelex_core.document import FakeDocument
from librelex_core.mcp.client import LegalToolsClient
from tests.conftest import make_fake_legal_server
from tests.fakes import ScriptedLLM, text_turn, tool_turn


async def _deps(llm, doc, tools, profile):
    registry = ToolRegistry(await tools.tool_specs(), profile)
    return AgentDeps(llm, tools, doc, registry, LimitsConfig(), doc.ask_consent, "fake.local",
                     "m", True)


async def test_chat_adds_context_line_only_with_a_selection():
    server, _ = make_fake_legal_server()
    events = []

    async def emit(m):
        events.append(m)

    async with LegalToolsClient(server) as tools:
        doc = FakeDocument(["x"], selection=(0, 0, 1))
        llm = ScriptedLLM([text_turn("ciao")])
        s = DocSession("d1")
        out = await run_chat(s, "domanda", p.DocContext(title="atto.odt", has_selection=True),
                             await _deps(llm, doc, tools, "chat"), emit, "r1")
        assert out.text == "ciao"
        assert llm.calls[0][0][1]["content"] == "[Documento: atto.odt; selezione presente]\ndomanda"
        llm2 = ScriptedLLM([text_turn("ok")])
        await run_chat(DocSession("d2"), "altra", p.DocContext(),
                       await _deps(llm2, doc, tools, "chat"), emit, "r2")
        assert llm2.calls[0][0][1]["content"] == "altra"


async def test_research_prompt_and_flow_inserts_grounded_text():
    assert "read_selection" in research_prompt(None)
    assert "Domanda: danno da demansionamento" in research_prompt("danno da demansionamento")
    server, calls = make_fake_legal_server()
    doc = FakeDocument(["Premessa."])
    events = []

    async def emit(m):
        events.append(m)

    async with LegalToolsClient(server) as tools:
        # cerca_giurisprudenza is not part of the fake server: the search step of the prompt
        # is played by leggi_sentenza, which is what grounds the reference anyway.
        llm = ScriptedLLM([
            tool_turn(("leggi_sentenza", {"numero": 12345, "anno": 2024})),
            tool_turn(("insert_markdown", {
                "where": "cursor",
                "markdown": "## Precedenti\n\nCass. sez. lav. n. 12345/2024: "
                            "\"Il datore di lavoro risponde...\""})),
            text_turn("Trovata una decisione.")])
        out = await run_research(DocSession("d1"), "demansionamento",
                                 await _deps(llm, doc, tools, "research"), emit, "r1")
    assert out.text == "Trovata una decisione." and out.inserted and out.flagged == []
    assert doc.inserts[0]["undo_label"] == "LibreLex: ricerca giurisprudenziale"
    assert calls["verifica"] == []                # the reference was grounded by leggi_sentenza
