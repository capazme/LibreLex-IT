# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import json

from librelex_core.agent.loop import AgentDeps
from librelex_core.agent.registry import ToolRegistry
from librelex_core.agent.state import DocSession
from librelex_core.commands.draft import PROFILE, UNDO_LABEL, draft_prompt, run_draft
from librelex_core.config import LimitsConfig
from librelex_core.document import FakeDocument
from librelex_core.mcp.client import LegalToolsClient
from tests.conftest import make_fake_legal_server
from tests.fakes import ScriptedLLM, text_turn, tool_turn


async def _deps(llm, doc, tools):
    registry = ToolRegistry(await tools.tool_specs(), PROFILE)
    return AgentDeps(llm, tools, doc, registry, LimitsConfig(), doc.ask_consent, "fake.local",
                     "m", True)


def test_draft_prompt_carries_the_message_and_the_procedure():
    text = draft_prompt("decreto ingiuntivo per fattura n. 12/2025 di 12.000 euro")
    assert text.startswith("Redazione guidata da modello.")
    assert "Messaggio dell'utente: decreto ingiuntivo per fattura n. 12/2025 di 12.000 euro" in text
    for needle in ("genera_modello_atto", "read_paragraphs", "insert_markdown",
                   'where="end"', "cite_law", "fermati", "parentesi quadre",
                   "già inserito", "dati già noti"):
        assert needle in text, needle
    assert PROFILE == "draft" and UNDO_LABEL == "LibreLex: redazione da modello"


async def test_first_turn_collects_data_and_stops_without_writing():
    server, calls = make_fake_legal_server()
    doc = FakeDocument(["Fattura n. 12 del 3 marzo 2025, Euro 12.000, Alfa S.r.l."])
    events = []

    async def emit(m):
        events.append(m)

    async with LegalToolsClient(server) as tools:
        llm = ScriptedLLM([
            tool_turn(("genera_modello_atto", {"tipo_atto": "cerca",
                                               "parametri": {"query": "ingiuntivo"}})),
            tool_turn(("genera_modello_atto", {"tipo_atto": "decreto_ingiuntivo_ordinario"}),
                      ("read_paragraphs", {})),
            text_turn("Per procedere mi servono: 1) il debitore; 2) la sede del giudice.")])
        session = DocSession("d1")
        out = await run_draft(session, "decreto ingiuntivo per la fattura del documento",
                              await _deps(llm, doc, tools), emit, "r1")
    assert out.text.startswith("Per procedere mi servono")
    assert out.inserted == [] and doc.inserts == []
    assert calls["modelli"] == [("cerca", {"query": "ingiuntivo"}),
                                ("decreto_ingiuntivo_ordinario", {})]
    user = llm.calls[0][0][1]
    assert user["role"] == "user" and user["content"] == draft_prompt(
        "decreto ingiuntivo per la fattura del documento")
    # the draft profile exposes the generators and the calculators, not the case-law tools
    names = {t["function"]["name"] for t in llm.calls[0][1]}
    assert {"genera_modello_atto", "decreto_ingiuntivo", "contributo_unificato",
            "interessi_mora", "read_paragraphs", "insert_markdown"} <= names
    assert not {"cerca_giurisprudenza", "leggi_sentenza", "replace_selection",
                "add_comment"} & names
    # the template result went to the model as data, with its instructions
    tool_msgs = [m for m in llm.calls[2][0] if m.get("role") == "tool"]
    assert any("<<<DATI: genera_modello_atto>>>" in m["content"]
               and "tool_diretto" in m["content"] for m in tool_msgs)


async def test_second_turn_generates_computes_and_inserts_section_by_section():
    server, calls = make_fake_legal_server()
    doc = FakeDocument([""])
    events = []

    async def emit(m):
        events.append(m)

    async with LegalToolsClient(server) as tools:
        deps_llm = ScriptedLLM([
            text_turn("Mi serve il nome del debitore.")])
        session = DocSession("d1")
        await run_draft(session, "decreto ingiuntivo, creditore Alfa S.r.l., 12.000 euro",
                        await _deps(deps_llm, doc, tools), emit, "r1")
        llm = ScriptedLLM([
            tool_turn(("decreto_ingiuntivo", {"creditore": "Alfa S.r.l.", "debitore": "Beta S.p.A.",
                                              "importo": 12000.0}),
                      ("contributo_unificato", {"valore_causa": 12000.0,
                                                "tipo_procedimento": "monitorio"})),
            tool_turn(("insert_markdown", {"where": "end", "markdown":
                       "# RICORSO PER DECRETO INGIUNTIVO\n\n(artt. 633 e ss. c.p.c.)\n\n"
                       "**Alfa S.r.l.** contro **Beta S.p.A.**"})),
            tool_turn(("insert_markdown", {"where": "end", "markdown":
                       "## Conclusioni\n\nSi chiede il pagamento di Euro 12.000,00, oltre "
                       "contributo unificato di Euro 129,50 (DPR 115/2002)."})),
            text_turn("Inserite intestazione e conclusioni; resta da indicare la sede.")])
        out = await run_draft(session, "il debitore è Beta S.p.A.",
                              await _deps(llm, doc, tools), emit, "r2")
    assert out.text.endswith("resta da indicare la sede.")
    assert [i["where"] for i in doc.inserts] == ["end", "end"]
    assert all(i["undo_label"] == UNDO_LABEL and i["author"] == "LibreLex" for i in doc.inserts)
    assert len(out.inserted) == 2 and out.flagged == [] and out.unverified == []
    assert calls["generatori"] == [("decreto_ingiuntivo", "Alfa S.r.l.", "Beta S.p.A.", 12000.0)]
    assert calls["calcoli"] == [("contributo_unificato", 12000.0, "monitorio")]
    # the second turn sees the first one: same session, the answer follows the question
    history = llm.calls[0][0]
    assert [m["role"] for m in history[:4]] == ["system", "user", "assistant", "user"]
    assert history[2]["content"] == "Mi serve il nome del debitore."
    assert history[3]["content"] == draft_prompt("il debitore è Beta S.p.A.")
    # whether the references of the markdown count as grounded depends on how the extractor
    # canonicalises "artt. 633 e ss. c.p.c." and "DPR 115/2002"; either way the fake verifies
    # them as "verificata", so nothing is flagged (asserted above), and no assertion is made
    # on calls["verifica"]
    payload = json.loads("".join(m["content"].split("<<<DATI: decreto_ingiuntivo>>>\n")[1]
                                 .split("\n<<<FINE DATI>>>")[0]
                         for m in llm.calls[1][0] if m.get("role") == "tool"
                         and "decreto_ingiuntivo" in m["content"]))
    assert payload["giudice_competente"] == "Tribunale"


async def test_generator_echo_does_not_ground_a_reference_the_model_invented():
    """Finding 1 (final-review fix wave): decreto_ingiuntivo echoes its free-text parameters
    verbatim into "bozza" (spec §6.6 item 1). A reference the model made up and passed as a
    parameter must not come back "already seen": it still has to be verified, and flagged,
    like any reference the model writes on insert."""
    server, calls = make_fake_legal_server(
        verdicts={"Cass. n. 99999/2024": ("inesistente", "nessuna decisione")})
    doc = FakeDocument([""])
    events = []

    async def emit(m):
        events.append(m)

    async with LegalToolsClient(server) as tools:
        llm = ScriptedLLM([
            tool_turn(("decreto_ingiuntivo",
                       {"creditore": "Alfa S.r.l. (cfr. Cass. n. 99999/2024)",
                        "debitore": "Beta S.p.A.", "importo": 12000.0})),
            tool_turn(("insert_markdown", {"where": "end", "markdown":
                       "Come da Cass. n. 99999/2024, si chiede..."})),
            text_turn("Inserito.")])
        session = DocSession("d1")
        out = await run_draft(session, "decreto ingiuntivo",
                              await _deps(llm, doc, tools), emit, "r1")
    assert calls["verifica"] == [["Cass. n. 99999/2024"]]
    assert out.flagged == ["Cass. n. 99999/2024"]
    assert len(doc.comments) == 1
