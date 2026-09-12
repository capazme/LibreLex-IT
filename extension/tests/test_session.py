# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import importlib
import sys
import types

import pytest

from librelex_ext import PROTOCOL_VERSION, DocumentActionError
from librelex_ext.bridge import BridgeError
from librelex_ext.session import Session, dispatch_doc_call


def load_document_module():
    """Import the real (UNO-only) ``librelex_ext.document`` on a machine without UNO.

    Only the three names document.py binds at import time are stubbed; everything the test
    then touches (``DocumentAdapter._index``/``_entry``, ``DocumentActionError``) is the real
    code, so the exception class the adapter raises is the one the core will see.
    """
    if "librelex_ext.document" not in sys.modules:
        for name, attrs in (("uno", {}), ("com", {}), ("com.sun", {}), ("com.sun.star", {}),
                            ("com.sun.star.beans", {"PropertyValue": object}),
                            ("com.sun.star.text", {}),
                            ("com.sun.star.text.ControlCharacter", {"PARAGRAPH_BREAK": 0})):
            module = types.ModuleType(name)
            module.__dict__.update(attrs)
            sys.modules.setdefault(name, module)
    return importlib.import_module("librelex_ext.document")


class EmptyBody:
    """A Writer body text with no paragraphs at all (enough to make any id unknown)."""

    def createEnumeration(self):
        return self

    def hasMoreElements(self):
        return False


class EmptyModel:
    def getText(self):
        return EmptyBody()


class FakeAdapter:
    def __init__(self):
        self.calls = []
        self.selection = {"text": "", "anchor": None}

    def get_document_info(self):
        return {"title": "t", "url": "", "paragraph_count": 2, "has_selection": False,
                "cursor_paragraph": "p:0", "lo_version": "26.8", "has_markdown_filter": True}

    def read_selection(self):
        return self.selection

    def read_paragraphs(self, from_=None, to=None):
        self.calls.append(("read_paragraphs", from_, to))
        return [{"id": "p:0", "text": "a", "style": "Text body", "kind": "body"}]

    def find_text(self, query, paragraph_id=None):
        return [{"anchor": {"paragraph_id": "p:0", "start": 0, "end": 1}, "text": query}]

    def insert_markdown(self, where, markdown, undo_label, bookmark=None, author=None):
        self.calls.append(("insert_markdown", where, bookmark, author))
        return {"from_id": "p:1", "to_id": "p:2"}

    def replace_selection(self, markdown, undo_label):
        return {"from_id": "p:0", "to_id": "p:0"}

    def add_comment(self, paragraph_id, start, end, expected_text, author, text):
        self.calls.append(("add_comment", paragraph_id, author))
        return "exact"

    def remove_comments(self, author):
        return 2

    def goto(self, paragraph_id):
        self.calls.append(("goto", paragraph_id))


class FakeBridge:
    def __init__(self, fail_start=False, fail_send=False):
        self.sent, self.started, self.stopped, self.fail_start = [], False, False, fail_start
        self.fail_send = fail_send
        self.alive = False

    def start(self):
        if self.fail_start:
            raise BridgeError("impossibile avviare uv")
        self.started = self.alive = True

    def send(self, msg):
        if self.fail_send:
            raise BridgeError("core non raggiungibile: [Errno 32] Broken pipe")
        self.sent.append(msg)

    def is_alive(self):
        return self.alive

    def stop(self, timeout=3.0):
        self.stopped, self.alive = True, False


class FakeView:
    def __init__(self):
        self.lines, self.status, self.busy = [], "", None
        self.citations, self.transcript = None, None
        self.progress = None
        self.stream, self.usage, self.consent = "", None, None

    def append(self, text):
        self.lines.append(text)

    def set_transcript(self, text):
        self.transcript = text

    def set_status(self, text):
        self.status = text

    def set_busy(self, busy):
        self.busy = busy

    def set_citations(self, labels):
        self.citations = labels

    def set_progress(self, done, total):
        self.progress = (done, total)

    def append_stream(self, text):
        self.stream += text

    def set_usage(self, text):
        self.usage = text

    def set_consent(self, summary):
        self.consent = summary


def make(fail_start=False, adapter=None, fail_send=False):
    adapter, view = adapter or FakeAdapter(), FakeView()
    bridges = []

    def factory(on_event):
        b = FakeBridge(fail_start, fail_send)
        bridges.append(b)
        return b

    s = Session(adapter, factory, doc_id="d1", lo_version="26.8", has_markdown_filter=True,
                config_path="/cfg/config.toml")
    s.bind(view, s.handle_event)     # tests run everything on one thread
    return s, adapter, view, bridges


def test_dispatch_maps_actions_and_wraps_results():
    a = FakeAdapter()
    assert dispatch_doc_call(a, "read_paragraphs", {"from_": 1, "to": None}) == {
        "paragraphs": [{"id": "p:0", "text": "a", "style": "Text body", "kind": "body"}]}
    assert a.calls[-1] == ("read_paragraphs", 1, None)
    dispatch_doc_call(a, "read_paragraphs", {"from": 2, "to": 3})    # Appendix A spelling
    assert a.calls[-1] == ("read_paragraphs", 2, 3)
    found = dispatch_doc_call(a, "find_text", {"query": "a", "paragraph_id": None})
    assert found["occurrences"][0]["text"] == "a"
    assert dispatch_doc_call(a, "add_comment", {
        "paragraph_id": "p:0", "start": 0, "end": 1,
        "expected_text": "a", "author": "x", "text": "t"}) == {"anchored": "exact"}
    assert dispatch_doc_call(a, "remove_comments", {"author": "x"}) == {"count": 2}
    assert dispatch_doc_call(a, "goto", {"paragraph_id": "p:0"}) == {}
    assert dispatch_doc_call(a, "get_document_info", {})["paragraph_count"] == 2
    assert dispatch_doc_call(a, "insert_markdown", {
        "where": "cursor", "markdown": "x", "undo_label": "u", "bookmark": None,
        "author": "LibreLex"}) == {"from_id": "p:1", "to_id": "p:2"}
    with pytest.raises(Exception, match="azione sconosciuta"):
        dispatch_doc_call(a, "format_disk", {})


def test_first_command_starts_core_sends_hello_then_command():
    s, adapter, view, bridges = make()
    s.run_command("verify_citations", {"scope": "document"})
    assert s.state == "starting" and bridges[0].started
    hello = bridges[0].sent[0]
    assert hello["type"] == "hello" and hello["protocol"] == PROTOCOL_VERSION
    assert hello["lo_version"] == "26.8" and hello["has_markdown_filter"] is True
    assert view.status == "Avvio del core..."
    s.handle_event({"kind": "message", "msg": {
        "type": "hello_ok", "core_version": "0.1.0", "protocol": PROTOCOL_VERSION,
        "mcp_server_version": None, "warnings": ["w1"]}})
    assert s.state == "busy" and view.busy is True
    cmd = bridges[0].sent[1]
    assert cmd == {"type": "command", "id": "r1", "doc_id": "d1", "name": "verify_citations",
                   "args": {"scope": "document"}}
    assert "w1" in view.lines[-1]


def test_doc_call_is_answered_with_matching_ids_and_errors_become_ok_false():
    s, adapter, view, bridges = make()
    s.run_command("insert_norm", {"reference": "art. 2043 c.c."})
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.1.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    s.handle_event({"kind": "message", "msg": {
        "type": "doc_call", "request_id": "r1", "call_id": "c7", "action": "insert_markdown",
        "args": {"where": "cursor", "markdown": "m", "undo_label": "u",
                 "bookmark": "b", "author": "LibreLex"}}})
    assert bridges[0].sent[-1] == {"type": "doc_result", "id": "r1", "call_id": "c7", "ok": True,
                                   "result": {"from_id": "p:1", "to_id": "p:2"}}
    s.handle_event({"kind": "message", "msg": {
        "type": "doc_call", "request_id": "r1", "call_id": "c8", "action": "nope", "args": {}}})
    res = bridges[0].sent[-1]
    assert res["ok"] is False and "azione sconosciuta" in res["error"] and res["call_id"] == "c8"


def test_doc_call_error_from_the_real_adapter_keeps_its_italian_message():
    """The adapter's DocumentActionError must reach the core as plain Italian, no class name.

    Regression: document.py used to define its own DocumentActionError, so session's
    isinstance() check never matched and every document error was prefixed with the Python
    class name.
    """
    document = load_document_module()
    s, adapter, view, bridges = make(adapter=document.DocumentAdapter(None, EmptyModel()))
    s.run_command("insert_norm", {"reference": "art. 2043 c.c."})
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.1.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    s.handle_event({"kind": "message", "msg": {
        "type": "doc_call", "request_id": "r1", "call_id": "c1", "action": "goto",
        "args": {"paragraph_id": "p:99"}}})
    assert bridges[0].sent[-1] == {"type": "doc_result", "id": "r1", "call_id": "c1",
                                   "ok": False, "error": "paragrafo non trovato: p:99"}
    assert document.DocumentActionError is DocumentActionError


def test_doc_call_after_shutdown_is_dropped_without_error():
    s, adapter, view, bridges = make()
    s.run_command("insert_norm", {"reference": "art. 2043 c.c."})
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.1.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    s.shutdown()
    sent_before = list(bridges[0].sent)
    # A doc_call the reader thread had already queued arrives on the UI thread after
    # shutdown() nulled self.bridge; it must be dropped, not raise AttributeError.
    s.handle_event({"kind": "message", "msg": {
        "type": "doc_call", "request_id": "r1", "call_id": "c9", "action": "goto",
        "args": {"paragraph_id": "p:0"}}})
    assert bridges[0].sent == sent_before
    assert adapter.calls == []


def test_consent_request_after_shutdown_answers_without_a_bridge_and_without_error():
    """M2: the M1 auto-deny handler is gone; the panel just shows the request. Answering it

    after the bridge died (document closed mid-request) must not raise, and nothing is sent.
    """
    s, adapter, view, bridges = make()
    s.run_command("verify_citations", {})
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.1.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    s.shutdown()
    sent_before = list(bridges[0].sent)
    summary = {"scope": "paragraphs", "chars": 10, "endpoint_host": "h", "model": "m", "zdr": True}
    s.handle_event({"kind": "message", "msg": {
        "type": "consent_request", "request_id": "r1", "call_id": "c9", "summary": summary}})
    assert bridges[0].sent == sent_before and view.consent == summary
    s.answer_consent("once")
    assert bridges[0].sent == sent_before and s.pending_consent is None


def test_final_renders_summary_and_frees_the_session():
    s, adapter, view, bridges = make()
    s.run_command("verify_citations", {})
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.1.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    s.handle_event({"kind": "message", "msg": {
        "type": "status", "request_id": "r1", "text": "Leggo"}})
    assert view.status == "Leggo"
    s.handle_event({"kind": "message", "msg": {
        "type": "progress", "request_id": "r1", "done": 3, "total": 9}})
    assert view.status == "Verificate 3 di 9"
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r1",
        "text": "Verificate 1 citazioni, 1 segnalazioni inserite.",
        "cancelled": False, "usage": None,
        "summary": {"scope": "document", "citazioni_totali": 1, "citazioni_uniche": 1,
                    "per_verdetto": {"inesistente": 1},
                    "problemi": [{"citazione": "Cass. n. 9/2024", "verdetto": "inesistente",
                                  "nota": "",
                                  "occorrenze": [{"paragraph_id": "p:4", "start": 0, "end": 1}]}],
                    "elenco": [{"citazione": "Cass. n. 9/2024", "tipo": "sentenza",
                                "verdetto": "inesistente", "nota": "",
                                "occorrenze": [{"paragraph_id": "p:4", "start": 0, "end": 1}]}],
                    "da_controllare_a_mano": [], "non_interpretabili": [], "non_verificabili": [],
                    "da_riprovare": [], "commenti_inseriti": 1}}})
    assert s.state == "ready" and view.busy is False and view.status == "Pronto"
    assert view.citations == ["✗ Cass. n. 9/2024"]
    s.texts["Cass. n. 9/2024"] = "cached text"       # already fetched: navigation only
    s.select_citation(0)
    assert adapter.calls[-1] == ("goto", "p:4") and view.lines[-1] == "cached text"
    s.run_command("insert_norm", {})                       # core already running: sent directly
    assert bridges[0].sent[-1]["id"] == "r2" and s.state == "busy"


def test_busy_rejects_a_second_command_and_cancel_is_forwarded():
    s, adapter, view, bridges = make()
    s.run_command("verify_citations", {})
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.1.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    n = len(bridges[0].sent)
    s.run_command("insert_norm", {})
    assert len(bridges[0].sent) == n and "in corso" in view.status
    s.cancel()
    assert bridges[0].sent[-1] == {"type": "cancel", "id": "r1", "doc_id": "d1"}
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r1", "text": "Annullato.",
        "cancelled": True, "usage": None, "summary": {}}})
    assert s.state == "ready" and view.lines[-1] == "Annullato."


def test_error_message_and_core_exit_reset_the_state():
    s, adapter, view, bridges = make()
    s.run_command("insert_norm", {})
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.1.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    s.handle_event({"kind": "message", "msg": {"type": "error", "request_id": "r1",
                                               "code": "reference_unparsed", "message": "boh"}})
    assert s.state == "ready" and view.lines[-1] == "Errore (reference_unparsed): boh"
    s.run_command("insert_norm", {})
    s.handle_event({"kind": "exit", "code": 1})
    assert s.state == "stopped" and view.busy is False
    assert "chiuso" in view.lines[-1] and "core-stderr.log" in view.lines[-1]
    s.run_command("insert_norm", {})                        # restarts lazily
    assert len(bridges) == 2 and s.state == "starting"


def test_protocol_mismatch_and_start_failure_are_reported():
    s, adapter, view, bridges = make()
    s.run_command("insert_norm", {})
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "9.0.0",
                                               "protocol": 99, "warnings": []}})
    assert s.state == "stopped" and bridges[0].stopped
    assert "protocollo 99" in view.lines[-1] and "richiesto 1" in view.lines[-1]
    s2, _, view2, _ = make(fail_start=True)
    s2.run_command("insert_norm", {})
    assert s2.state == "stopped" and "impossibile avviare uv" in view2.lines[-1]


def test_a_dead_pipe_on_hello_is_shown_in_the_panel_instead_of_raising():
    """Regression (whole-branch review I2): BridgeError escaped into the UNO listener.

    Typical trigger: a first run where ``uv run --frozen`` cannot build the environment, the
    child dies at once and the very first write hits EPIPE. The user must see why, and the
    buttons must be re-enabled without waiting for the ``exit`` event to be drained.
    """
    s, adapter, view, bridges = make(fail_send=True)
    s.run_command("verify_citations", {"scope": "document"})
    assert s.state == "stopped" and s.bridge is None and s.pending is None
    assert view.busy is False and view.status == "Core non attivo"
    assert "Core non raggiungibile" in view.lines[-1] and bridges[0].stopped
    lines = list(view.lines)
    s.handle_event({"kind": "exit", "code": 1})     # the reader thread reports the exit later
    assert view.lines == lines                       # already reported: no duplicate message
    s.run_command("insert_norm", {})                 # still restarts lazily on the next action
    assert len(bridges) == 2


def test_a_dead_pipe_on_a_command_is_shown_in_the_panel_instead_of_raising():
    s, adapter, view, bridges = make()
    s.run_command("verify_citations", {})
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.1.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r1", "text": "Fatto.", "cancelled": False,
        "usage": None, "summary": {}}})
    assert s.state == "ready"
    bridges[0].fail_send = True                      # the core dies between two requests
    s.run_command("insert_norm", {})
    assert s.state == "stopped" and s.request_id is None and view.busy is False
    assert view.status == "Core non attivo" and "Core non raggiungibile" in view.lines[-1]


def test_a_dead_pipe_on_cancel_is_shown_in_the_panel_instead_of_raising():
    s, adapter, view, bridges = make()
    s.run_command("verify_citations", {})
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.1.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    assert s.state == "busy"
    bridges[0].fail_send = True
    s.cancel()
    assert s.state == "stopped" and view.busy is False
    assert view.status == "Core non attivo"          # not "Annullamento..."
    assert "Core non raggiungibile" in view.lines[-1]


def test_events_are_buffered_while_unbound_and_replayed_on_bind():
    s, adapter, view, bridges = make()
    s.run_command("insert_norm", {})
    s.unbind()
    s.post_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.1.0",
                                             "protocol": PROTOCOL_VERSION, "warnings": []}})
    assert s.state == "starting"                            # nothing handled yet
    view2 = FakeView()
    s.bind(view2, s.handle_event)
    assert s.state == "busy" and view2.transcript is not None and view2.busy is True


def test_shutdown_stops_the_bridge():
    s, adapter, view, bridges = make()
    s.run_command("insert_norm", {})
    s.shutdown()
    assert bridges[0].stopped and s.state == "stopped"


def test_note_updates_transcript_and_view_so_it_survives_rebind():
    s, adapter, view, bridges = make()
    s.note("LibreLex-IT pronto.")
    assert view.lines[-1] == "LibreLex-IT pronto." and s.transcript[-1] == "LibreLex-IT pronto."
    view2 = FakeView()
    s.bind(view2, s.handle_event)                            # panel closed and reopened
    assert view2.transcript == "LibreLex-IT pronto."


def _ready(s):
    s.run_command("list_citations", {"scope": "document"})
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.2.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})


def test_list_citations_fills_the_list_and_click_fetches_then_caches_text():
    s, adapter, view, bridges = make()
    _ready(s)
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r1", "text": "Trovate 1 citazioni (1 occorrenze).",
        "cancelled": False, "usage": None,
        "summary": {"scope": "document", "citazioni_totali": 2, "citazioni_uniche": 2,
                    "citazioni": [{"citazione": "art. 2043 c.c.", "tipo": "norma", "corte": None,
                                   "verificabile": True,
                                   "occorrenze": [{"paragraph_id": "p:4", "start": 0, "end": 1}]},
                                  {"citazione": "art. 1218 c.c.", "tipo": "norma", "corte": None,
                                   "verificabile": True,
                                   "occorrenze": [{"paragraph_id": "p:7", "start": 0, "end": 1}]}],
                    "non_interpretabili": []}}})
    assert view.citations == ["art. 2043 c.c.", "art. 1218 c.c."] and s.state == "ready"
    s.select_citation(0)
    assert adapter.calls[-1] == ("goto", "p:4")
    assert bridges[0].sent[-1]["name"] == "show_text"
    assert bridges[0].sent[-1]["args"] == {"reference": "art. 2043 c.c."}
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r2", "text": "Testo di art. 2043 c.c.",
        "cancelled": False, "usage": None,
        "summary": {"tipo": "norma", "riferimento": "art. 2043 c.c.",
                    "titolo": "art. 2043 c.c. (Risarcimento)", "testo": "Qualunque fatto",
                    "massima": None, "fonte": "Normattiva", "url": "https://x",
                    "troncato": False}}})
    assert view.lines[-1].startswith("— art. 2043 c.c. (Risarcimento)")
    assert "art. 2043 c.c." in s.texts
    n = len(bridges[0].sent)
    s.select_citation(0)                                # cached: no new request
    assert len(bridges[0].sent) == n and view.lines[-1] == s.texts["art. 2043 c.c."]
    s.run_command("verify_citations", {})
    n = len(bridges[0].sent)
    s.select_citation(0)                                # busy but cached: shown anyway
    assert adapter.calls[-1] == ("goto", "p:4") and view.lines[-1] == s.texts["art. 2043 c.c."]
    assert len(bridges[0].sent) == n                    # no request while the core is busy
    view.status = ""
    s.select_citation(1)                                # busy and not cached: navigate only
    assert adapter.calls[-1] == ("goto", "p:7") and "fine richiesta" in view.status
    assert len(bridges[0].sent) == n


def test_show_text_button_flow_and_unavailable_error():
    s, adapter, view, bridges = make()
    _ready(s)
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r1", "text": "x", "cancelled": False, "usage": None,
        "summary": {"scope": "document", "citazioni_totali": 0, "citazioni_uniche": 0,
                    "citazioni": [], "non_interpretabili": []}}})
    s.run_command("show_text", {"reference": "TAR Lazio n. 1/2023"})
    s.handle_event({"kind": "message", "msg": {
        "type": "error", "request_id": "r2", "code": "text_unavailable",
        "message": "testo non disponibile per TAR Lazio n. 1/2023"}})
    assert s.state == "ready" and view.lines[-1].startswith("Errore (text_unavailable)")


def test_progress_drives_the_bar_and_the_end_of_a_request_hides_it():
    s, adapter, view, bridges = make()
    s.run_command("verify_citations", {})
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.1.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    assert view.progress is None
    s.handle_event({"kind": "message", "msg": {
        "type": "progress", "request_id": "r1", "done": 3, "total": 9}})
    assert view.progress == (3, 9) and view.status == "Verificate 3 di 9"
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r1", "text": "Fatto.", "cancelled": False,
        "usage": None, "summary": {}}})
    assert view.progress == (0, None)


def test_an_error_and_a_dead_core_also_hide_the_bar():
    s, adapter, view, bridges = make()
    s.run_command("verify_citations", {})
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.1.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    s.handle_event({"kind": "message", "msg": {
        "type": "progress", "request_id": "r1", "done": 1, "total": 4}})
    s.handle_event({"kind": "message", "msg": {
        "type": "error", "request_id": "r1", "code": "tool_error", "message": "boom"}})
    assert view.progress == (0, None)
    s.handle_event({"kind": "message", "msg": {
        "type": "progress", "request_id": "r2", "done": 2, "total": 4}})
    s.handle_event({"kind": "exit", "code": 1})
    assert view.progress == (0, None)


def test_clear_transcript_empties_the_replay_buffer_and_the_view():
    s, adapter, view, bridges = make()
    s.note("prima riga")
    s.note("seconda riga")
    assert s.transcript == ["prima riga", "seconda riga"]
    s.clear_transcript()
    assert s.transcript == [] and view.transcript == ""


def test_chat_sends_context_streams_deltas_and_shows_usage():
    s, adapter, view, bridges = make()
    s.chat("   ")
    assert view.status == "Scrivi un messaggio" and not bridges
    s.chat("che dice il documento?")
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.2.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    msg = bridges[0].sent[-1]
    assert msg["type"] == "chat" and msg["id"] == "r1"
    assert msg["message"] == "che dice il documento?"
    assert msg["context"] == {"title": "t", "has_selection": False, "cursor_paragraph": "p:0"}
    s.handle_event({"kind": "message",
                    "msg": {"type": "delta", "request_id": "r1", "text": "Il documento "}})
    s.handle_event({"kind": "message",
                    "msg": {"type": "delta", "request_id": "r1", "text": "dice X."}})
    assert (view.stream == "Il documento dice X." and view.lines == []
            or view.lines[-1] != "Il documento dice X.")
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r1", "text": "Il documento dice X.",
        "cancelled": False, "usage": {"input_tokens": 100, "output_tokens": 20, "cost_usd": None},
        "summary": {"tool_calls": 1, "usage_totals": {"input_tokens": 100, "output_tokens": 20}}}})
    assert view.lines[-1] == "" and "Il documento dice X." not in view.lines      # not duplicated
    assert s.transcript[-2] == "Il documento dice X." and s.state == "ready"
    assert view.usage == "Turno: 100 + 20 token · sessione: 120 token"


def test_consent_request_is_shown_and_answered_in_the_panel():
    s, adapter, view, bridges = make()
    s.chat("leggi")
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.2.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    summary = {"scope": "paragraphs", "chars": 50, "endpoint_host": "h", "model": "m", "zdr": True}
    s.handle_event({"kind": "message", "msg": {
        "type": "consent_request", "request_id": "r1", "call_id": "k1", "summary": summary}})
    assert view.consent == summary and view.status == "In attesa del consenso"
    s.answer_consent("once")
    assert bridges[0].sent[-1] == {
        "type": "consent_result", "id": "r1", "call_id": "k1", "decision": "once"}
    assert view.consent is None and s.pending_consent is None
    s.answer_consent("deny")                                   # nothing pending: ignored
    assert bridges[0].sent[-1]["decision"] == "once"


def test_research_and_llm_config_error_hint():
    s, adapter, view, bridges = make()
    s.research("  ")
    assert bridges[0].sent[0]["type"] == "hello"
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.2.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    assert bridges[0].sent[-1] == {
        "type": "command", "id": "r1", "doc_id": "d1", "name": "research", "args": {}}
    s.handle_event({"kind": "message", "msg": {"type": "error", "request_id": "r1",
                                               "code": "llm_config",
                                               "message": "llm.model non impostato"}})
    assert "Configura la sezione [llm]" in view.lines[-1]
    assert "/cfg/config.toml" in view.lines[-1]
    s.research("usucapione")
    assert bridges[0].sent[-1]["args"] == {"question": "usucapione"}


def test_final_cancelled_after_streaming_still_shows_notes_and_usage():
    """Fix round 1, finding 2: a streamed turn stays on the streamed path even when

    cancelled=True — blank line, notes (including "[annullato]"), then set_usage — instead of
    falling back to the plain "Annullato." line reserved for a turn with no streamed text.
    """
    s, adapter, view, bridges = make()
    s.chat("leggi")
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.2.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    s.handle_event({"kind": "message",
                    "msg": {"type": "delta", "request_id": "r1", "text": "parziale"}})
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r1", "text": "", "cancelled": True,
        "usage": {"input_tokens": 30, "output_tokens": 10, "cost_usd": None},
        "summary": {"stopped": "cancelled",
                    "usage_totals": {"input_tokens": 30, "output_tokens": 10}}}})
    assert "Annullato." not in view.lines
    assert "[annullato]" in view.lines
    assert view.usage == "Turno: 30 + 10 token · sessione: 40 token"
    assert s.transcript[-2:] == ["", "[annullato]"]
