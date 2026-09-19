# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import pytest

from librelex_core import protocol as p
from librelex_core.agent.loop import CONSENT_DENIED, AgentDeps, TurnOutcome
from librelex_core.agent.prompt import load_recipe
from librelex_core.agent.registry import ToolRegistry
from librelex_core.agent.state import DocSession, DraftState
from librelex_core.commands.draft import (
    PROFILE,
    TOO_MANY_QUESTIONS,
    base_text,
    coerce_args,
    draft_message,
    draft_summary,
    insert_base,
    parse_number,
    placeholders,
    run_draft,
    to_markdown,
)
from librelex_core.commands.templates import TemplateCatalogue
from librelex_core.config import LimitsConfig
from librelex_core.document import FakeDocument
from librelex_core.mcp.client import LegalToolsClient
from tests.conftest import make_fake_legal_server
from tests.fakes import ScriptedLLM, text_turn, tool_turn


async def _deps(llm, doc, tools):
    specs = await tools.tool_specs()
    return AgentDeps(llm, tools, doc, ToolRegistry(specs, PROFILE), LimitsConfig(),
                     doc.ask_consent, "fake.local", "m", True, catalogue=TemplateCatalogue(tools),
                     specs=specs)


def _emit_list():
    events = []

    async def emit(m):
        events.append(m)
    return events, emit


def _hand_built_session(**state) -> DocSession:
    """A session carrying a drafting nobody ran: the message builder needs no server."""
    session = DocSession("d1")
    session.draft = DraftState(
        tipo_atto="decreto_ingiuntivo_ordinario",
        template={"tipo_atto": "decreto_ingiuntivo_ordinario",
                  "descrizione": "Ricorso per decreto ingiuntivo", "categoria": "atti_introduttivi",
                  "campi_obbligatori": ["creditore"],
                  "routing": {"tipo": "resource", "tool": None, "parametri_fissi": {},
                              "resource": "atti://decreto"}},
        fields={"creditore": "Alfa S.r.l."})
    for name, value in state.items():
        setattr(session.draft, name, value)
    return session


def test_draft_message_carries_the_instruction_the_answers_and_the_recipe():
    session = _hand_built_session(answers={"sede": "Milano"}, done=True)
    text = draft_message(session, "continue", "aggiungi la provvisoria esecuzione")
    assert "Istruzione dell'utente: aggiungi la provvisoria esecuzione" in text
    assert "Risposte alle domande precedenti:\n- sede: Milano" in text
    assert "Redazione già completata in un turno precedente" in text
    assert text.rstrip().endswith(load_recipe().rstrip().splitlines()[-1])


def test_draft_message_says_when_the_reference_was_truncated():
    session = _hand_built_session()
    session.reference = {"name": "lungo.odt", "chars": 80000, "text": "x", "troncato": True}
    assert ("Atto di riferimento disponibile: lungo.odt (80000 caratteri, troncato ai primi "
            "60.000 caratteri): leggilo") in draft_message(session, "continue")


def test_pure_helpers():
    assert placeholders("ILL.MO [SEDE] di [SEDE], Avv. [LEGALE], {campo}") == [
        "[SEDE]", "[LEGALE]", "{campo}"]
    assert base_text({"testo": "T", "bozza_ricorso": "B"}) == "T"
    assert base_text({"bozza_ricorso": "B", "riepilogo": {}}) == "B"
    assert base_text({"riepilogo": {"totale": 1}}) is None
    # the other two key names of the real generators (sollecito_pagamento, preventivo_*)
    assert base_text({"testo_lettera": "L"}) == "L"
    assert base_text({"testo_preventivo": "P", "totale": 1}) == "P"
    assert base_text({"testo": "", "bozza_ricorso": "B"}) == "B"
    assert base_text({"testo_zeta": "Z", "testo_alfa": "A"}) == "A"     # first, sorted
    assert to_markdown("A\nB\n\n\nC") == "A\n\nB\n\nC"
    assert [parse_number(v) for v in ("12.000", "12.5", "12.000,50", "1.234.567", "1500",
                                     "12,5")] == [12000.0, 12.5, 12000.5, 1234567.0, 1500.0, 12.5]
    assert [parse_number(v) for v in ("€ 12.000", "12.000 euro", "1.000,50 EUR", " 1500 ")] == [
        12000.0, 12000.0, 1000.5, 1500.0]
    with pytest.raises(ValueError):
        parse_number("non un numero")
    props = {"importo": {"type": "number"}, "provvisoria_esecuzione": {"type": "boolean"},
             "creditore": {"type": "string"}, "tipo_credito": {"type": "string"}}
    assert coerce_args({"importo": "12.000,50", "provvisoria_esecuzione": "sì",
                        "creditore": "Alfa", "extra": "x", "tipo_credito": "cambiale"},
                       {"tipo_credito": "ordinario"}, props) == {
        "importo": 12000.5, "provvisoria_esecuzione": True, "creditore": "Alfa",
        "tipo_credito": "ordinario"}


async def test_start_inserts_the_base_then_the_model_asks_questions_and_stops():
    server, calls = make_fake_legal_server()
    doc = FakeDocument([""])
    events, emit = _emit_list()
    async with LegalToolsClient(server) as tools:
        llm = ScriptedLLM([tool_turn(("chiedi_dati", {"domande": [
            {"campo": "sede", "domanda": "Sede del tribunale?", "esempio": "Milano"},
            {"campo": "data_fattura", "domanda": "Data della fattura?", "tipo": "data"}]}))])
        session = DocSession("d1")
        deps = await _deps(llm, doc, tools)
        out = await run_draft(session, {"action": "start",
                                        "tipo_atto": "decreto_ingiuntivo_ordinario",
                                        "fields": {"creditore": "Alfa S.r.l.",
                                                   "debitore": "Beta S.p.A.",
                                                   "importo": "12.000"},
                                        "notes": "fattura n. 12 del 3 marzo 2025"},
                              deps, emit, "r1")
    # the base was generated with the fixed parameter and inserted before the model ran
    assert calls["generatori"] == [("decreto_ingiuntivo", "Alfa S.r.l.", "Beta S.p.A.", 12000.0)]
    assert doc.inserts[0]["undo_label"] == "LibreLex: base decreto_ingiuntivo_ordinario"
    assert doc.inserts[0]["bookmark"] == "LibreLex.atto.decreto_ingiuntivo_ordinario"
    assert doc.inserts[0]["author"] == "LibreLex" and doc.inserts[0]["where"] == "end"
    assert doc.inserts[0]["markdown"].startswith("RICORSO PER DECRETO INGIUNTIVO\n\n(Artt. 633")
    draft = session.draft
    assert draft.base["placeholders"] == ["[SEDE]"] and draft.base["tool"] == "decreto_ingiuntivo"
    assert draft.base["result"]["giudice_competente"] == "Tribunale"
    assert draft.partitions[0]["titolo"] == "Base: Ricorso per decreto ingiuntivo — credito ordinario"  # noqa: E501
    # the model saw the state, not a bare message
    user = llm.calls[0][0][1]["content"]
    for needle in ("Redazione guidata: Ricorso per decreto ingiuntivo", "- creditore: Alfa S.r.l.",
                   "Note dell'utente: fattura n. 12", "Base deterministica già nel documento",
                   "[SEDE]", "<<<DATI: modello d'atto>>>", "<<<DATI: risultato di decreto_ingiuntivo>>>",  # noqa: E501
                   "# Ricetta di redazione", "non prevede un generatore"):
        assert (needle in user) != (needle == "non prevede un generatore"), needle
    names = {t["function"]["name"] for t in llm.calls[0][1]}
    assert {"chiedi_dati", "redazione_completata", "leggi_atto_riferimento", "replace_text",
            "decreto_ingiuntivo", "contributo_unificato"} <= names
    # the questions ended the turn and reached the summary
    assert out.ended_by == "questions" and out.text == ""
    summary = draft_summary(session, out)
    assert summary["domande"] == [
        {"campo": "sede", "domanda": "Sede del tribunale?", "esempio": "Milano", "tipo": "testo"},
        {"campo": "data_fattura", "domanda": "Data della fattura?", "esempio": "", "tipo": "data"}]
    assert summary["segnaposto_aperti"] == ["[SEDE]"] and summary["completata"] is False
    assert summary["base_errore"] is None
    assert any(isinstance(e, p.Status) and "base deterministica" in e.text for e in events)


async def test_answer_fills_placeholders_inserts_partitions_and_completes():
    server, calls = make_fake_legal_server()
    doc = FakeDocument([""])
    events, emit = _emit_list()
    async with LegalToolsClient(server) as tools:
        session = DocSession("d1")
        llm1 = ScriptedLLM([tool_turn(("chiedi_dati", {"domande": [
            {"campo": "sede", "domanda": "Sede?"}]}))])
        await run_draft(session, {"action": "start", "tipo_atto": "decreto_ingiuntivo_ordinario",
                                  "fields": {"creditore": "Alfa", "debitore": "Beta",
                                             "importo": "12000"}},
                        await _deps(llm1, doc, tools), emit, "r1")
        llm2 = ScriptedLLM([
            tool_turn(("contributo_unificato",
                       {"valore_causa": 12000, "tipo_procedimento": "monitorio"})),
            tool_turn(("replace_text", {"query": "[SEDE]", "replacement": "MILANO"}),
                      ("insert_markdown",
                       {"where": "end",
                        "markdown": "## Premesse in fatto\n\nAlfa ha emesso la fattura."}),
                      ("insert_markdown",
                       {"where": "end",
                        "markdown": "## Conclusioni\n\nEuro 129,50 di contributo unificato "
                                    "(DPR 115/2002)."})),
            tool_turn(("redazione_completata",
                       {"riepilogo": "Calcoli: contributo unificato 129,50.\n"
                                     "Allegati: procura, fattura."})),
        ])
        out = await run_draft(session, {"action": "answer", "answers": {"sede": "Milano"}},
                              await _deps(llm2, doc, tools), emit, "r2")
    user = llm2.calls[0][0][-1]["content"]
    assert "Risposte appena ricevute:\n- sede: Milano" in user
    assert calls["calcoli"] == [("contributo_unificato", 12000.0, "monitorio")]
    paragraphs = [x.text for x in await doc.read_paragraphs()]
    assert any("MILANO" in t for t in paragraphs) and not any("[SEDE]" in t for t in paragraphs)
    draft = session.draft
    assert [pt["titolo"] for pt in draft.partitions] == [
        "Base: Ricorso per decreto ingiuntivo — credito ordinario", "Premesse in fatto",
        "Conclusioni"]
    assert draft.done is True and draft.riepilogo.startswith("Calcoli:")
    summary = draft_summary(session, out)
    assert summary["completata"] is True and summary["segnaposto_aperti"] == []
    assert summary["ended_by"] == "done" and out.replaced == 1
    assert [i["undo_label"] for i in doc.inserts][1:] == [
        "LibreLex: redazione decreto_ingiuntivo_ordinario"] * 3


async def test_reference_act_is_read_with_consent_once_and_never_grounds():
    server, calls = make_fake_legal_server()
    doc = FakeDocument([""], consent_decisions=["once", "once"])
    events, emit = _emit_list()
    async with LegalToolsClient(server) as tools:
        session = DocSession("d1")
        session.consent = "document"          # the document's consent never covers the reference
        session.reference = {"name": "ricorso_rossi.docx", "chars": 40,
                             "text": "RICORSO ... come da Cass. n. 99999/2024 ...",
                             "troncato": False}
        llm = ScriptedLLM([
            tool_turn(("leggi_atto_riferimento", {})),
            tool_turn(("leggi_atto_riferimento", {})),
            tool_turn(("insert_markdown",
                       {"where": "end", "markdown": "## Diritto\n\nCass. n. 99999/2024."})),
            text_turn("fatto")])
        deps = await _deps(llm, doc, tools)
        await run_draft(session, {"action": "start", "tipo_atto": "atto_di_citazione",
                                  "fields": {"attore": "A", "convenuto": "B", "oggetto": "O"}},
                        deps, emit, "r1")
    assert len(doc.consent_requests) == 1                     # once per session
    req = doc.consent_requests[0]
    assert req.scope == "reference" and req.name == "ricorso_rossi.docx" and req.chars == 40
    tool_msgs = [m for m in llm.calls[2][0] if m.get("role") == "tool"]
    assert "<<<DATI: atto di riferimento (ricorso_rossi.docx)>>>" in tool_msgs[0]["content"]
    assert calls["verifica"] == [["Cass. n. 99999/2024"]]    # not grounded by the reference
    assert ("Atto di riferimento disponibile: ricorso_rossi.docx (40 caratteri)"
            in llm.calls[0][0][1]["content"])
    assert doc.inserts == [] or doc.inserts[0]["where"] == "end"   # no base: resource routing
    assert session.draft.base is None and session.draft.base_errore is None
    assert ("Il modello d'atto non prevede un generatore: componi dal modello."
            in llm.calls[0][0][1]["content"])


async def test_reference_denied_and_missing():
    server, _ = make_fake_legal_server()
    doc = FakeDocument([""], consent_decisions=["deny"])
    events, emit = _emit_list()
    async with LegalToolsClient(server) as tools:
        session = DocSession("d1")
        llm = ScriptedLLM([tool_turn(("leggi_atto_riferimento", {})), text_turn("senza")])
        await run_draft(session, {"action": "start", "tipo_atto": "atto_di_citazione",
                                  "fields": {"attore": "A"}}, await _deps(llm, doc, tools),
                        emit, "r1")
        msg = [m for m in llm.calls[1][0] if m.get("role") == "tool"][0]["content"]
        assert msg == "ERRORE: nessun atto di riferimento caricato"
        session.reference = {"name": "x.odt", "chars": 3, "text": "abc", "troncato": False}
        llm2 = ScriptedLLM([tool_turn(("leggi_atto_riferimento", {})), text_turn("senza")])
        await run_draft(session, {"action": "continue", "message": "vai"},
                        await _deps(llm2, doc, tools), emit, "r2")
        msg = [m for m in llm2.calls[1][0] if m.get("role") == "tool"][-1]["content"]
        assert msg.startswith("ERRORE: invio del testo")


async def test_bad_actions_raise_value_error():
    server, _ = make_fake_legal_server()
    events, emit = _emit_list()
    async with LegalToolsClient(server) as tools:
        deps = await _deps(ScriptedLLM([]), FakeDocument([""]), tools)
        with pytest.raises(ValueError, match="tipo_atto"):
            await run_draft(DocSession("d"), {"action": "start"}, deps, emit, "r")
        with pytest.raises(ValueError, match="nessuna redazione"):
            await run_draft(DocSession("d"), {"action": "answer", "answers": {}}, deps, emit, "r")
        started = _hand_built_session(answers={"sede": "Milano"})
        with pytest.raises(ValueError, match="risposte mancanti"):
            await run_draft(started, {"action": "answer"}, deps, emit, "r")
        with pytest.raises(ValueError, match="risposte mancanti"):
            await run_draft(started, {"action": "answer", "answers": "sede: Milano"}, deps,
                            emit, "r")
        assert started.draft.answers == {"sede": "Milano"}   # no state change
        deps.catalogue = None
        with pytest.raises(ValueError, match="catalogo"):
            await run_draft(DocSession("d"), {"action": "start", "tipo_atto": "x"}, deps, emit, "r")


async def test_a_generator_that_returns_only_data_still_reaches_the_model():
    """No text key in the result: nothing is inserted, but the deterministic data is kept and
    travels to the model in its own DATI block (final review, finding 2)."""
    server, _ = make_fake_legal_server()
    doc = FakeDocument([""])
    events, emit = _emit_list()
    session = _hand_built_session()
    session.draft.template["routing"] = {"tipo": "tool_diretto", "tool": "contributo_unificato",
                                         "parametri_fissi": {}, "resource": None}
    session.draft.fields = {"valore_causa": "12.000"}
    async with LegalToolsClient(server) as tools:
        await insert_base(session, await _deps(ScriptedLLM([]), doc, tools), emit, "r1")
    base = session.draft.base
    assert base["inserted"] is False and base["from_id"] is None and base["to_id"] is None
    assert base["placeholders"] == [] and base["tool"] == "contributo_unificato"
    assert base["result"]["contributo_unificato"] == 129.5
    assert doc.inserts == [] and session.draft.base_errore is None
    message = draft_message(session, "continue")
    assert ("Nessun testo base inserito: il generatore ha restituito solo dati (vedi sotto)."
            in message)
    assert "<<<DATI: risultato di contributo_unificato>>>" in message
    summary = draft_summary(session, TurnOutcome())
    assert summary["segnaposto_aperti"] == [] and summary["base_errore"] is None


async def test_the_letter_and_the_preventivo_texts_become_the_base():
    """`testo_lettera` (sollecito_pagamento) and `testo_preventivo` (preventivo_*) are act
    texts like `testo` and `bozza*` (final review, finding 2)."""
    server, _ = make_fake_legal_server()
    doc = FakeDocument([""])
    events, emit = _emit_list()
    async with LegalToolsClient(server) as tools:
        session = DocSession("d1")
        llm = ScriptedLLM([text_turn("ok")])
        await run_draft(session, {"action": "start", "tipo_atto": "sollecito_ordinario",
                                  "fields": {"creditore": "Alfa", "debitore": "Beta",
                                             "importo": "1.000", "data_scadenza": "2025-03-03",
                                             "data_sollecito": "2025-09-19"}},
                        await _deps(llm, doc, tools), emit, "r1")
        assert doc.inserts[0]["markdown"].startswith("SOLLECITO DI PAGAMENTO")
        base = session.draft.base
        assert base["tool"] == "sollecito_pagamento" and base["inserted"] is True
        assert base["placeholders"] == ["[LUOGO]", "[DATA]"] and base["result"] == {
            "interessi": 12.0}
        doc2 = FakeDocument([""])
        session2 = DocSession("d2")
        llm2 = ScriptedLLM([text_turn("ok")])
        await run_draft(session2, {"action": "start", "tipo_atto": "preventivo_causa",
                                   "fields": {"valore_causa": "12.000"}},
                        await _deps(llm2, doc2, tools), emit, "r2")
    assert doc2.inserts[0]["markdown"].startswith("PREVENTIVO PER CAUSA CIVILE")
    assert session2.draft.base["result"] == {"totale": 1234.5}
    assert "<<<DATI: risultato di preventivo_civile>>>" in llm2.calls[0][0][1]["content"]


async def test_a_failed_base_is_reported_to_the_panel_and_to_the_model():
    """A generator that refuses its arguments leaves no base: the panel gets `base_errore`
    and the model is told to compose from the template (final review, finding 3)."""
    server, _ = make_fake_legal_server()
    doc = FakeDocument([""])
    events, emit = _emit_list()
    async with LegalToolsClient(server) as tools:
        session = DocSession("d1")
        llm = ScriptedLLM([text_turn("Compongo dal modello.")])
        out = await run_draft(session, {"action": "start", "tipo_atto": "sollecito_ordinario",
                                        "fields": {"creditore": "Alfa", "debitore": "Beta",
                                                   "importo": "1.000",
                                                   "data_scadenza": "3 marzo 2025",
                                                   "data_sollecito": "2025-09-19"}},
                              await _deps(llm, doc, tools), emit, "r1")
    draft = session.draft
    assert draft.base is None and draft.base_errore
    assert doc.inserts == []
    user = llm.calls[0][0][1]["content"]
    assert "Generazione della base fallita (" in user
    assert "componi dal modello seguendo la struttura indicata." in user
    assert "non prevede un generatore" not in user
    assert any(isinstance(e, p.Status) and e.text.startswith("Base non disponibile")
               for e in events)
    assert draft_summary(session, out)["base_errore"] == draft.base_errore


async def test_a_denied_reference_is_not_asked_again():
    """A refusal is a decision about the file, not about one tool call (final review,
    finding 6)."""
    server, _ = make_fake_legal_server()
    doc = FakeDocument([""], consent_decisions=["deny"])
    events, emit = _emit_list()
    async with LegalToolsClient(server) as tools:
        session = DocSession("d1")
        session.reference = {"name": "x.odt", "chars": 3, "text": "abc", "troncato": False}
        llm = ScriptedLLM([tool_turn(("leggi_atto_riferimento", {}),
                                     ("leggi_atto_riferimento", {})), text_turn("senza")])
        await run_draft(session, {"action": "start", "tipo_atto": "atto_di_citazione",
                                  "fields": {"attore": "A"}}, await _deps(llm, doc, tools),
                        emit, "r1")
        assert len(doc.consent_requests) == 1 and session.reference_denied is True
        assert [m["content"] for m in llm.calls[1][0] if m.get("role") == "tool"] == [
            CONSENT_DENIED, CONSENT_DENIED]
        llm2 = ScriptedLLM([tool_turn(("leggi_atto_riferimento", {})), text_turn("ancora")])
        await run_draft(session, {"action": "continue", "message": "vai"},
                        await _deps(llm2, doc, tools), emit, "r2")
    assert len(doc.consent_requests) == 1                      # never asked twice
    assert [m["content"] for m in llm2.calls[1][0]
            if m.get("role") == "tool"][-1] == CONSENT_DENIED


async def test_more_than_eight_questions_are_cut_and_the_model_is_told():
    server, _ = make_fake_legal_server()
    events, emit = _emit_list()
    async with LegalToolsClient(server) as tools:
        session = DocSession("d1")
        llm = ScriptedLLM([tool_turn(("chiedi_dati", {"domande": [
            {"campo": f"c{i}", "domanda": f"Domanda {i}?"} for i in range(10)]}))])
        out = await run_draft(session, {"action": "start", "tipo_atto": "atto_di_citazione",
                                        "fields": {"attore": "A"}},
                              await _deps(llm, FakeDocument([""]), tools), emit, "r1")
    assert [q["campo"] for q in session.draft.questions] == [f"c{i}" for i in range(8)]
    assert draft_summary(session, out)["domande"] == session.draft.questions
    assert session.turns[-1].messages[-1]["content"].endswith(TOO_MANY_QUESTIONS)


async def test_answers_to_unknown_fields_are_kept_and_a_second_start_starts_over():
    server, _ = make_fake_legal_server()
    doc = FakeDocument([""])
    events, emit = _emit_list()
    async with LegalToolsClient(server) as tools:
        session = DocSession("d1")
        session.reference = {"name": "x.odt", "chars": 3, "text": "abc", "troncato": False}
        llm = ScriptedLLM([tool_turn(("chiedi_dati", {"domande": [
            {"campo": "sede", "domanda": "Sede?"}]}))])
        await run_draft(session, {"action": "start", "tipo_atto": "decreto_ingiuntivo_ordinario",
                                  "fields": {"creditore": "Alfa", "debitore": "Beta",
                                             "importo": "12000"}},
                        await _deps(llm, doc, tools), emit, "r1")
        llm2 = ScriptedLLM([text_turn("grazie")])
        await run_draft(session, {"action": "answer",
                                  "answers": {"sede": "Milano", "campo_inventato": "valore"}},
                        await _deps(llm2, doc, tools), emit, "r2")
        assert session.draft.answers == {"sede": "Milano", "campo_inventato": "valore"}
        assert "- campo_inventato: valore" in llm2.calls[0][0][-1]["content"]
        llm3 = ScriptedLLM([text_turn("riparto")])
        await run_draft(session, {"action": "start", "tipo_atto": "atto_di_citazione",
                                  "fields": {"attore": "A", "convenuto": "B", "oggetto": "O"}},
                        await _deps(llm3, doc, tools), emit, "r3")
    draft = session.draft
    assert draft.tipo_atto == "atto_di_citazione" and draft.answers == {}
    assert draft.partitions == [] and draft.base is None and draft.questions == []
    assert session.reference is not None                        # the reference act survives
    assert "Atto di riferimento disponibile: x.odt" in llm3.calls[0][0][-1]["content"]
