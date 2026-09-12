# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import asyncio
import json

import pytest

from librelex_core import protocol as p
from librelex_core.agent.loop import run_turn
from librelex_core.agent.registry import ToolRegistry
from librelex_core.agent.state import INTERRUPTED_TOOL_RESULT, DocSession
from librelex_core.config import LimitsConfig
from librelex_core.document import DocumentError, FakeDocument
from librelex_core.mcp.client import LegalToolsClient
from tests.conftest import make_fake_legal_server
from tests.fakes import ScriptedLLM, text_turn, tool_turn


def _assert_well_formed(messages):
    """OpenAI contract: every assistant ``tool_calls`` is answered, in order, by its
    ``tool`` messages, and no ``tool`` message stands alone."""
    i = 0
    while i < len(messages):
        msg = messages[i]
        i += 1
        assert msg["role"] != "tool", f"tool message without its assistant: {msg}"
        if msg["role"] != "assistant" or not msg.get("tool_calls"):
            continue
        answers = []
        while i < len(messages) and messages[i]["role"] == "tool":
            answers.append(messages[i]["tool_call_id"])
            i += 1
        assert answers == [c["id"] for c in msg["tool_calls"]]


async def _run(llm, doc, tools, turns_profile="chat", limits=None, consent=None, session=None):
    events = []

    async def emit(m):
        events.append(m)

    specs = await tools.tool_specs() if tools else []
    registry = ToolRegistry(specs, turns_profile)
    session = session or DocSession("d1")
    consent = consent or doc.ask_consent
    outcome = await run_turn(session, "domanda", turns_profile, llm, tools, doc, registry, emit,
                             "r1", limits or LimitsConfig(), consent, "fake.local", "fake-model",
                             True, "LibreLex: chat")
    return outcome, events, session


async def test_plain_answer_streams_deltas():
    server, _ = make_fake_legal_server()
    async with LegalToolsClient(server) as tools:
        llm = ScriptedLLM([text_turn("Risposta breve.")])
        outcome, events, session = await _run(llm, FakeDocument(["x"]), tools)
    assert outcome.text == "Risposta breve." and outcome.stopped is None and outcome.tool_calls == 0
    assert "".join(e.text for e in events if isinstance(e, p.Delta)) == "Risposta breve."
    assert [m["role"] for m in session.messages_for_model("S")] == ["system", "user", "assistant"]
    assert llm.calls[0][0][0]["role"] == "system" and llm.calls[0][1][0]["type"] == "function"


async def test_legal_and_internal_tools_then_answer_with_grounding():
    server, calls = make_fake_legal_server()
    async with LegalToolsClient(server) as tools:
        llm = ScriptedLLM([tool_turn(("cite_law", {"reference": "art. 2043 c.c."}),
                                     ("data_odierna", {})),
                           text_turn("Ecco.")])
        outcome, events, session = await _run(llm, FakeDocument(["x"]), tools)
    assert calls["cite"] == ["art. 2043 c.c."] and outcome.tool_calls == 2
    msgs = session.messages_for_model("S")
    tool_msgs = [m for m in msgs if m["role"] == "tool"]
    assert tool_msgs[0]["content"].startswith("<<<DATI: cite_law>>>")
    assert len(tool_msgs[1]["content"]) == 10
    assert any(isinstance(e, p.Status) and "cite_law" in e.text for e in events)
    assert outcome.usage.input_tokens == 30 and outcome.usage.output_tokens == 13


async def test_document_read_asks_consent_once_and_deny_is_reported_to_the_model():
    server, _ = make_fake_legal_server()
    doc = FakeDocument(["Primo paragrafo", "Secondo"], consent_decisions=["deny", "once", "once"])
    async with LegalToolsClient(server) as tools:
        llm = ScriptedLLM([tool_turn(("read_paragraphs", {})),
                           tool_turn(("read_paragraphs", {"from_": 0, "to": 1})),
                           tool_turn(("read_selection", {})), text_turn("ok")])
        outcome, events, session = await _run(llm, doc, tools)
    tool_msgs = [m["content"] for m in session.messages_for_model("S") if m["role"] == "tool"]
    assert tool_msgs[0].startswith("ERRORE: invio del testo del documento non autorizzato")
    assert tool_msgs[1].startswith("<<<DATI: read_paragraphs>>>")
    assert "Primo paragrafo" in tool_msgs[1]
    # 'once' covered the third call in the same turn
    assert len(doc.consent_requests) == 2
    assert doc.consent_requests[1].scope == "paragraphs" and doc.consent_requests[1].chars > 0
    assert session.consent == "none"
    doc2 = FakeDocument(["x"], consent_decisions=["document"])
    async with LegalToolsClient(server) as tools:
        llm = ScriptedLLM([tool_turn(("read_paragraphs", {})), text_turn("ok")])
        _, _, session2 = await _run(llm, doc2, tools)
    assert session2.consent == "document"


async def test_insert_markdown_verifies_unseen_references_and_comments_problems():
    server, calls = make_fake_legal_server(verdicts={"Cass. n. 99999/2024": ("inesistente", "no")})
    doc = FakeDocument(["Premessa."])
    async with LegalToolsClient(server) as tools:
        llm = ScriptedLLM([
            tool_turn(("cite_law", {"reference": "art. 2043 c.c."})),
            tool_turn(("insert_markdown",
                       {"where": "cursor",
                        "markdown": "Come da art. 2043 c.c. e Cass. n. 99999/2024."})),
            text_turn("Inserito.")])
        outcome, events, session = await _run(llm, doc, tools, "research")
    assert calls["verifica"] == [["Cass. n. 99999/2024"]]   # art. 2043 was grounded by cite_law
    assert doc.inserts[0]["author"] == "LibreLex"
    assert doc.inserts[0]["undo_label"] == "LibreLex: chat"
    assert outcome.inserted == [{"from_id": "p:1", "to_id": "p:1"}]
    assert outcome.flagged == ["Cass. n. 99999/2024"]
    assert len(doc.comments) == 1 and doc.comments[0]["paragraph_id"] == "p:1"
    tool_msgs = [m["content"] for m in session.messages_for_model("S") if m["role"] == "tool"]
    assert "Inserito nei paragrafi p:1-p:1" in tool_msgs[1]
    assert "Cass. n. 99999/2024" in tool_msgs[1]
    assert any(isinstance(e, p.Status) and "Verifico 1 riferimenti" in e.text for e in events)


async def test_an_invented_article_sharing_the_act_of_a_real_one_is_still_verified():
    """Spec §6.6 end to end: "artt. 2043 e 999999 c.c." must not slip 999999 through."""
    server, calls = make_fake_legal_server(verdicts={"art. 999999 c.c.": ("inesistente", "no")})
    doc = FakeDocument(["Premessa."])
    async with LegalToolsClient(server) as tools:
        llm = ScriptedLLM([
            tool_turn(("cite_law", {"reference": "art. 2043 c.c."})),
            tool_turn(("insert_markdown",
                       {"where": "cursor",
                        "markdown": "Ai sensi degli artt. 2043 e 999999 c.c. risarcisce."})),
            text_turn("Inserito.")])
        outcome, events, session = await _run(llm, doc, tools, "research")
    assert calls["verifica"] == [["art. 999999 c.c."]]
    assert outcome.flagged == ["art. 999999 c.c."]
    assert len(doc.comments) == 1 and doc.comments[0]["paragraph_id"] == "p:1"


async def test_a_comment_that_cannot_be_added_still_records_the_insertion():
    server, _ = make_fake_legal_server(verdicts={"Cass. n. 99999/2024": ("inesistente", "no")})

    class NoComments(FakeDocument):
        async def add_comment(self, *args, **kwargs):
            raise DocumentError("ancoraggio non riuscito")

    doc = NoComments(["Premessa."])
    async with LegalToolsClient(server) as tools:
        llm = ScriptedLLM([
            tool_turn(("insert_markdown",
                       {"where": "cursor", "markdown": "Vedi Cass. n. 99999/2024."})),
            text_turn("ok")])
        outcome, _, session = await _run(llm, doc, tools, "research")
    assert outcome.inserted == [{"from_id": "p:1", "to_id": "p:1"}] and outcome.flagged == []
    tool_msgs = [m["content"] for m in session.messages_for_model("S") if m["role"] == "tool"]
    assert tool_msgs[0].startswith("Inserito nei paragrafi p:1-p:1.")
    assert "commenti di verifica non applicati" in tool_msgs[0]


async def test_tool_errors_unknown_tools_and_bad_json_go_back_to_the_model():
    server, _ = make_fake_legal_server(articles={})
    async with LegalToolsClient(server) as tools:
        llm = ScriptedLLM([tool_turn(("cite_law", {"reference": "art. 1 c.c."}),
                                     ("contributo_unificato", {}),
                                     ("remove_comments", {"author": "x"})), text_turn("capito")])
        llm.turns[0].tool_calls[0].arguments = "{not json"
        outcome, events, session = await _run(llm, FakeDocument(["x"]), tools, "research")
    tool_msgs = [m["content"] for m in session.messages_for_model("S") if m["role"] == "tool"]
    assert tool_msgs[0].startswith("ERRORE: argomenti non validi")
    assert tool_msgs[1].startswith("ERRORE: strumento non disponibile")
    assert tool_msgs[2].startswith("ERRORE: strumento non disponibile")


async def test_iteration_limit_timeout_and_cancellation():
    server, _ = make_fake_legal_server()
    async with LegalToolsClient(server) as tools:
        llm = ScriptedLLM([tool_turn(("data_odierna", {}))] * 3)
        outcome, events, session = await _run(llm, FakeDocument(["x"]), tools,
                                              limits=LimitsConfig(max_iterations=2))
        assert outcome.stopped == "iterations" and outcome.tool_calls == 2

        class Slow(ScriptedLLM):
            async def stream(self, messages, tools, on_delta):
                await on_delta("inizio ")
                await asyncio.sleep(0.2)
                return await super().stream(messages, tools, on_delta)

        outcome, events, session = await _run(Slow([text_turn("tardi")]), FakeDocument(["x"]),
                                              tools, limits=LimitsConfig(turn_timeout_s=0.05))
        assert outcome.stopped == "timeout" and "inizio" in outcome.text
        task = asyncio.create_task(_run(Slow([text_turn("x")]), FakeDocument(["x"]), tools))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_previous_turn_tool_results_are_compacted():
    server, _ = make_fake_legal_server()
    session = DocSession("d1")
    async with LegalToolsClient(server) as tools:
        llm = ScriptedLLM([tool_turn(("cite_law", {"reference": "art. 2043 c.c."})),
                           text_turn("uno"), text_turn("due")])
        await _run(llm, FakeDocument(["x"]), tools, session=session)
        await _run(llm, FakeDocument(["x"]), tools, session=session)
    msgs = session.messages_for_model("S")
    tool_contents = [m["content"] for m in msgs if m["role"] == "tool"]
    assert tool_contents[0].startswith("[risultato di cite_law omesso")
    assert json.dumps(msgs)  # serialisable


class SlowDocument(FakeDocument):
    """A document whose read never comes back in time (a slow bridge, a slow user)."""

    async def read_paragraphs(self, from_=None, to=None):
        await asyncio.sleep(0.5)
        return await super().read_paragraphs(from_, to)


async def test_a_turn_stopped_while_a_tool_runs_leaves_a_usable_history():
    """Timeout or cancellation must not leave dangling tool_calls: the next turn on the
    same session would be rejected by the provider with HTTP 400 (review finding 1)."""
    server, _ = make_fake_legal_server()
    session = DocSession("d1")
    async with LegalToolsClient(server) as tools:
        llm = ScriptedLLM([tool_turn(("read_paragraphs", {})), text_turn("dopo")])
        outcome, _, _ = await _run(llm, SlowDocument(["Primo"]), tools,
                                   limits=LimitsConfig(turn_timeout_s=0.05), session=session)
        assert outcome.stopped == "timeout"
        interrupted = session.turns[0].messages[-1]
        assert interrupted == {"role": "tool", "tool_call_id": "call_0",
                               "content": INTERRUPTED_TOOL_RESULT}
        _assert_well_formed(session.messages_for_model("S"))
        # the next turn goes through, and what reaches the provider is well-formed
        outcome, _, _ = await _run(llm, FakeDocument(["Primo"]), tools, session=session)
        assert outcome.text == "dopo"
        sent = llm.calls[-1][0]
        _assert_well_formed(sent)
        assert [m["role"] for m in sent] == ["system", "user", "assistant", "tool", "user"]
        assert "read_paragraphs" in sent[3]["content"]   # compacted, the tool name survives

        # same story when the user presses "Annulla" during the tool
        session2 = DocSession("d2")
        llm2 = ScriptedLLM([tool_turn(("read_paragraphs", {})), text_turn("poi")])
        task = asyncio.create_task(_run(llm2, SlowDocument(["Primo"]), tools, session=session2))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        _assert_well_formed(session2.messages_for_model("S"))
        outcome, _, _ = await _run(llm2, FakeDocument(["Primo"]), tools, session=session2)
        assert outcome.text == "poi"
        _assert_well_formed(llm2.calls[-1][0])


async def test_unverified_references_are_signalled_to_the_model_and_to_the_panel():
    """When the source cannot verify, the insertion says so (spec §6.6, review finding 2)."""
    server, _ = make_fake_legal_server(
        verdicts={"Cass. n. 99999/2024": ("non verificata", "Italgiure non raggiungibile")})
    doc = FakeDocument(["Premessa."])
    async with LegalToolsClient(server) as tools:
        llm = ScriptedLLM([
            tool_turn(("insert_markdown",
                       {"where": "cursor", "markdown": "Vedi Cass. n. 99999/2024."})),
            text_turn("Inserito.")])
        outcome, events, session = await _run(llm, doc, tools, "research")
    expected = ("1 riferimento non verificato (fonte non disponibile): Cass. n. 99999/2024.")
    assert outcome.unverified == ["Cass. n. 99999/2024"] and outcome.flagged == []
    assert doc.comments == []
    tool_msgs = [m["content"] for m in session.messages_for_model("S") if m["role"] == "tool"]
    assert tool_msgs[0] == f"Inserito nei paragrafi p:1-p:1. {expected}"
    assert any(isinstance(e, p.Status) and e.text == expected for e in events)

    # mcp-legal-it unreachable: same signal, no verification call at all
    doc2 = FakeDocument(["Premessa."])
    llm2 = ScriptedLLM([
        tool_turn(("insert_markdown",
                   {"where": "cursor",
                    "markdown": "Vedi art. 2043 c.c. e Cass. n. 99999/2024."})),
        text_turn("Inserito.")])
    outcome2, events2, _ = await _run(llm2, doc2, None, "research")
    assert outcome2.unverified == ["art. 2043 c.c.", "Cass. n. 99999/2024"]
    assert any(isinstance(e, p.Status) and "2 riferimenti non verificati" in e.text
               for e in events2)


async def test_an_answer_truncated_by_the_output_cap_is_reported():
    server, _ = make_fake_legal_server()
    truncated = text_turn("Risposta a metà")
    truncated.finish_reason = "length"
    async with LegalToolsClient(server) as tools:
        outcome, _, _ = await _run(ScriptedLLM([truncated]), FakeDocument(["x"]), tools)
    assert outcome.stopped == "length" and outcome.text == "Risposta a metà"
