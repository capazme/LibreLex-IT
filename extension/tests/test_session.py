# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import importlib
import sys
import types

import pytest

from librelex_ext import PROTOCOL_VERSION, DocumentActionError
from librelex_ext.bridge import BridgeError
from librelex_ext.layout import FIELD_ROWS
from librelex_ext.render import render_draft_status
from librelex_ext.session import MAX_REFERENCE_CHARS, Session, dispatch_doc_call


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

    def insert_markdown(self, where, markdown, undo_label, bookmark=None, author=None,
                        act_styles=False):
        self.calls.append(("insert_markdown", where, bookmark, author, act_styles))
        return {"from_id": "p:1", "to_id": "p:2"}

    def replace_selection(self, markdown, undo_label):
        return {"from_id": "p:0", "to_id": "p:0"}

    def replace_text(self, query, replacement, undo_label, paragraph_id=None, all=False):
        self.calls.append(("replace_text", query, replacement, paragraph_id, all))
        return {"count": 1, "anchors": [{"paragraph_id": "p:0", "start": 3, "end": 7}]}

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
        self.templates, self.template, self.reference = None, None, None
        self.partitions, self.draft_status, self.questions = None, None, None
        self.field_values, self.answer_values = None, None

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

    def set_templates(self, labels, selected):
        self.templates = (labels, selected)

    def set_template(self, info):
        self.template = info

    def set_reference(self, text, present):
        self.reference = (text, present)

    def set_partitions(self, labels):
        self.partitions = labels

    def set_draft_status(self, text, started):
        self.draft_status = (text, started)

    def set_questions(self, questions):
        self.questions = questions

    def set_field_values(self, fields, notes):
        self.field_values = (fields, notes)

    def set_answer_values(self, answers):
        self.answer_values = answers


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
    assert a.calls[-1] == ("insert_markdown", "cursor", None, "LibreLex", False)
    dispatch_doc_call(a, "insert_markdown", {
        "where": "cursor", "markdown": "x", "undo_label": "u", "bookmark": None,
        "author": "LibreLex"}, act_styles=True)
    assert a.calls[-1] == ("insert_markdown", "cursor", None, "LibreLex", True)
    assert dispatch_doc_call(a, "replace_text", {
        "query": "[SEDE]", "replacement": "Roma", "undo_label": "u", "all": True}) == {
        "count": 1, "anchors": [{"paragraph_id": "p:0", "start": 3, "end": 7}]}
    assert a.calls[-1] == ("replace_text", "[SEDE]", "Roma", None, True)
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
    assert s.transcript[-2] == "LibreLex: Il documento dice X." and s.state == "ready"
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


def test_final_with_no_streamed_text_still_shows_the_notes_and_the_usage_line():
    """Fix round 2, finding 1: a chat turn whose assistant message is tool calls only (the

    iteration limit fired) streams nothing, so the old ``was_streamed`` branch printed
    "Completato." and dropped both the interruption note and the usage line.
    """
    s, adapter, view, bridges = make()
    s.chat("leggi tutto")
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.2.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r1", "text": "", "cancelled": False,
        "usage": {"input_tokens": 900, "output_tokens": 0, "cost_usd": None},
        "summary": {"stopped": "iterations", "tool_calls": 12,
                    "usage_totals": {"input_tokens": 900, "output_tokens": 0}}}})
    assert "Completato." not in view.lines
    assert view.lines[-2:] == ["", "[interrotto: limite di iterazioni]"]
    assert view.usage == "Turno: 900 + 0 token · sessione: 900 token"


def test_research_final_without_deltas_shows_its_text_the_grounding_notes_and_usage():
    """Fix round 2, finding 1: the Ricerca turn did insert massime, so the notes of the M2

    exit criterion (inserted/flagged/unverified) must reach the panel even with no delta.
    """
    s, adapter, view, bridges = make()
    s.research("usucapione")
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.2.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r1", "text": "Inserite 2 massime.", "cancelled": False,
        "usage": {"input_tokens": 500, "output_tokens": 80, "cost_usd": None},
        "summary": {"inserted": [{"from_id": "p:2", "to_id": "p:5"}],
                    "flagged": ["Cass. n. 9/2024"], "unverified": ["Cass. n. 1/2020"],
                    "usage_totals": {"input_tokens": 500, "output_tokens": 80}}}})
    assert view.lines == ["Tu: ricerca: usucapione", "LibreLex: Inserite 2 massime.", "",
                          "Inserito nei paragrafi p:2-p:5",
                          "Riferimenti segnalati con un commento: Cass. n. 9/2024",
                          "Riferimenti non verificati (fonte non disponibile): Cass. n. 1/2020"]
    assert view.usage == "Turno: 500 + 80 token · sessione: 580 token"


def _pending_consent(s, view):
    """Start a chat and get to a pending consent_request."""
    s.chat("leggi")
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.2.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    summary = {"scope": "paragraphs", "chars": 50, "endpoint_host": "h", "model": "m", "zdr": True}
    s.handle_event({"kind": "message", "msg": {
        "type": "consent_request", "request_id": "r1", "call_id": "k1", "summary": summary}})
    assert view.consent == summary and s.pending_consent is not None
    return summary


def test_a_pending_consent_is_cleared_by_an_error_an_exit_and_a_cancelled_final():
    """Fix round 2, finding 6: the block must never survive the end of its turn, whichever

    of the three ways the turn ends (plan, Global Constraints).
    """
    s, adapter, view, bridges = make()
    _pending_consent(s, view)
    s.handle_event({"kind": "message", "msg": {"type": "error", "request_id": "r1",
                                               "code": "tool_error", "message": "boom"}})
    assert view.consent is None and s.pending_consent is None and s.consent_summary is None

    s2, _adapter2, view2, _bridges2 = make()
    _pending_consent(s2, view2)
    s2.handle_event({"kind": "exit", "code": 1})
    assert view2.consent is None and s2.pending_consent is None and s2.consent_summary is None

    s3, _adapter3, view3, bridges3 = make()
    _pending_consent(s3, view3)
    s3.cancel()
    assert bridges3[0].sent[-1] == {"type": "cancel", "id": "r1", "doc_id": "d1"}
    s3.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r1", "text": "Annullato.", "cancelled": True,
        "usage": None, "summary": {"stopped": "cancelled"}}})
    assert view3.consent is None and s3.pending_consent is None and s3.consent_summary is None


def test_a_rebuilt_panel_gets_back_the_pending_consent_and_the_usage_line():
    """Fix round 2, finding 7: a panel rebuilt mid-turn (deck switch, collapse/expand) is

    created empty, so bind/_replay have to show the question the core is still waiting on
    and the usage line of the last turn again.
    """
    s, adapter, view, bridges = make()
    s.chat("prima domanda")
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.2.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r1", "text": "Fatto.", "cancelled": False,
        "usage": {"input_tokens": 10, "output_tokens": 5, "cost_usd": None},
        "summary": {"tool_calls": 1, "usage_totals": {"input_tokens": 10, "output_tokens": 5}}}})
    assert s.usage_text == "Turno: 10 + 5 token · sessione: 15 token"
    s.chat("seconda domanda")
    summary = {"scope": "selection", "chars": 80, "endpoint_host": "h", "model": "m", "zdr": False}
    s.handle_event({"kind": "message", "msg": {
        "type": "consent_request", "request_id": "r2", "call_id": "k2", "summary": summary}})
    assert s.consent_summary == summary

    fresh = FakeView()                      # the panel was destroyed and built again
    s.bind(fresh, lambda ev: None)
    assert fresh.consent == summary
    assert fresh.usage == "Turno: 10 + 5 token · sessione: 15 token"
    s.answer_consent("document")
    assert s.consent_summary is None and fresh.consent is None


# Session.draft(message) (a single free-text command) is superseded by draft_start/
# draft_answer/draft_continue: the wire contract's `draft` command now carries a structured
# `action` (start/answer/continue), not a plain `message` (plan 2 wire contract). The scenario
# the old test covered (start, then answer through the same call) is now covered by
# test_draft_start_validates_fields_then_sends_and_the_turn_updates_the_view below.


def _hello(s, bridges):
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.4.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})


def test_templates_and_template_info_fill_the_drafting_view():
    s, adapter, view, bridges = make()
    s.templates("  ingiuntivo ")
    _hello(s, bridges)
    assert bridges[0].sent[-1]["name"] == "list_templates"
    assert bridges[0].sent[-1]["args"] == {"query": "ingiuntivo"}
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r1", "text": "Catalogo: 1 modelli.",
        "summary": {"modelli": [{"tipo_atto": "decreto_ingiuntivo_ordinario",
                                 "descrizione": "Ricorso per decreto ingiuntivo",
                                 "categoria": "atti_introduttivi", "tier": 1}],
                    "totale": 1, "query": "ingiuntivo"}}})
    assert view.templates == (["atti_introduttivi · Ricorso per decreto ingiuntivo"], None)
    assert s.draft_view["templates"][0]["tipo_atto"] == "decreto_ingiuntivo_ordinario"
    s.template("decreto_ingiuntivo_ordinario")
    assert bridges[0].sent[-1] == {"type": "command", "id": "r2", "doc_id": "d1",
                                   "name": "template_info",
                                   "args": {"tipo_atto": "decreto_ingiuntivo_ordinario"}}
    info = {"tipo_atto": "decreto_ingiuntivo_ordinario", "descrizione": "Ricorso",
            "categoria": "atti_introduttivi",
            "campi": [{"nome": "creditore", "tipo": "testo", "obbligatorio": True,
                      "descrizione": ""},
                      {"nome": "importo", "tipo": "numero", "obbligatorio": True,
                      "descrizione": ""}],
            "routing": {"tipo": "tool_diretto", "tool": "decreto_ingiuntivo",
                       "parametri_fissi": {}, "resource": None},
            "avvertenze": ["Bozza indicativa"], "campi_obbligatori": ["creditore", "importo"],
            "campi_opzionali": [], "tool_calcolo": [], "riferimenti_normativi": [],
            "istruzioni": ""}
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r2", "text": "Modello: 2 campi.", "summary": info}})
    assert view.template == info and s.draft_view["template"] == info
    assert view.draft_status == ("Compila i campi obbligatori e premi Avvia redazione", False)
    assert "Base deterministica: decreto_ingiuntivo" in view.lines[-1]


def test_draft_start_validates_fields_then_sends_and_the_turn_updates_the_view():
    s, adapter, view, bridges = make()
    s.draft_start("", {}, "")
    assert view.status == "Scegli prima un tipo di atto" and not bridges
    # M3: a refusal the lawyer reads next to the button he just pressed, not only in Azioni
    assert view.draft_status == ("Scegli prima un tipo di atto", False)
    s.draft_view["template"] = {"tipo_atto": "x", "campi": [
        {"nome": "creditore", "tipo": "testo", "obbligatorio": True},
        {"nome": "importo", "tipo": "numero", "obbligatorio": True},
        {"nome": "note_extra", "tipo": "testo", "obbligatorio": False}]}
    s.draft_start("x", {"creditore": "Alfa", "importo": " "}, "")
    assert view.status == "Compila i campi obbligatori: importo" and not bridges
    assert view.draft_status == ("Compila i campi obbligatori: importo", False)
    s.draft_start("x", {"creditore": "Alfa", "importo": "12000"}, "fattura 12")
    _hello(s, bridges)
    sent = bridges[0].sent[-1]
    assert sent["name"] == "draft"
    assert sent["args"] == {"action": "start", "tipo_atto": "x",
                            "fields": {"creditore": "Alfa", "importo": "12000"},
                            "notes": "fattura 12"}
    assert s.transcript[-1] == "Tu: avvio redazione x (2 campi)"
    assert view.draft_status == ("Compila i campi obbligatori e premi Avvia redazione", True)
    s.handle_event({"kind": "message",
                    "msg": {"type": "delta", "request_id": "r1", "text": "Mi servono"}})
    assert view.stream == "LibreLex: Mi servono"
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r1", "text": "Mi servono",
        "usage": {"input_tokens": 10, "output_tokens": 2, "cost_usd": None},
        "summary": {"tool_calls": 2,
                    "inserted": [{"from_id": "p:1", "to_id": "p:9", "titolo": "Base: Ricorso"}],
                    "flagged": [], "unverified": [],
                    "usage_totals": {"input_tokens": 10, "output_tokens": 2},
                    "tipo_atto": "x",
                    "domande": [{"campo": "sede", "domanda": "Sede?", "esempio": "Milano",
                                "tipo": "testo"}],
                    "partizioni": [{"titolo": "Base: Ricorso", "from_id": "p:1", "to_id": "p:9"}],
                    "segnaposto_aperti": ["[SEDE]"], "completata": False, "riepilogo": "",
                    "ended_by": "questions"}}})
    assert s.transcript[-3:] == ["LibreLex: Mi servono", "", "Inserito nei paragrafi p:1-p:9"]
    assert view.questions == [{"campo": "sede", "domanda": "Sede?", "esempio": "Milano",
                               "tipo": "testo"}]
    assert view.partitions == ["✓ Base: Ricorso", "… segnaposto aperti: 1"]
    assert view.draft_status == ("Compila i campi obbligatori e premi Avvia redazione", True)
    s.draft_answer({"sede": "Milano"})
    assert bridges[0].sent[-1]["args"] == {"action": "answer", "answers": {"sede": "Milano"}}
    assert s.transcript[-1] == "Tu: risposte a 1 domande"
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r2", "text": "Fatto.",
        "usage": {"input_tokens": 10, "output_tokens": 2, "cost_usd": None},
        "summary": {"tool_calls": 3,
                    "inserted": [{"from_id": "p:10", "to_id": "p:12", "titolo": "Conclusioni"}],
                    "flagged": [], "unverified": [],
                    "usage_totals": {"input_tokens": 20, "output_tokens": 4}, "tipo_atto": "x",
                    "domande": [],
                    "partizioni": [{"titolo": "Base: Ricorso", "from_id": "p:1", "to_id": "p:9"},
                                  {"titolo": "Conclusioni", "from_id": "p:10", "to_id": "p:12"}],
                    "segnaposto_aperti": [], "completata": True,
                    "riepilogo": "Calcoli: CU 129,50.", "ended_by": "done"}}})
    assert view.questions == [] and view.partitions == ["✓ Base: Ricorso", "✓ Conclusioni"]
    assert view.draft_status == ("Compila i campi obbligatori e premi Avvia redazione", True)
    assert "LibreLex: Fatto." in view.lines
    assert view.lines[-1] == "Riepilogo della redazione:\nCalcoli: CU 129,50."
    s.draft_answer({"x": "y"})
    assert view.status == "Nessuna domanda in sospeso"
    assert view.draft_status == ("Nessuna domanda in sospeso", True)
    s.draft_continue("aggiungi la provvisoria esecuzione")
    assert bridges[0].sent[-1]["args"] == {"action": "continue",
                                           "message": "aggiungi la provvisoria esecuzione"}


def test_draft_continue_refuses_when_nothing_started():
    s, adapter, view, bridges = make()
    s.draft_continue("qualcosa")
    assert view.status == "Nessuna redazione in corso" and not bridges
    assert view.draft_status == ("Nessuna redazione in corso", False)


def test_draft_start_refuses_while_busy_without_touching_the_drafting_view():
    """Fix round 1, Important: draft_start used to set draft_view["started"] and

    _draft_request before _submit had a chance to refuse a busy session, so a lawyer who
    clicked "Avvia redazione" during an unrelated chat turn saw the Redazione panel claim a
    drafting that was never sent to the core, stuck showing "Pronta per il prossimo passo"
    once the unrelated turn ended instead of "Compila i campi obbligatori".
    """
    s, adapter, view, bridges = make()
    s.draft_view["template"] = {"tipo_atto": "x", "campi": []}
    s.chat("leggi")
    _hello(s, bridges)
    assert s.state == "busy"
    sent_before = list(bridges[0].sent)
    s.draft_start("x", {}, "")
    assert view.status == "Richiesta in corso: attendi o premi Annulla"
    assert s.draft_view["started"] is False and s._draft_request is False
    assert bridges[0].sent == sent_before                    # nothing new sent
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r1", "text": "Fatto.",
        "usage": {"input_tokens": 1, "output_tokens": 1, "cost_usd": None},
        "summary": {"tool_calls": 0, "usage_totals": {"input_tokens": 1, "output_tokens": 1}}}})
    assert render_draft_status({**s.draft_view, "busy": s._draft_request}) == (
        "Compila i campi obbligatori e premi Avvia redazione")


def test_draft_answer_refuses_while_busy_without_touching_the_drafting_view():
    s, adapter, view, bridges = make()
    s.draft_view["questions"] = [{"campo": "a"}]
    s.chat("leggi")
    _hello(s, bridges)
    sent_before = list(bridges[0].sent)
    s.draft_answer({"a": "b"})
    assert view.status == "Richiesta in corso: attendi o premi Annulla"
    assert s._draft_request is False
    assert bridges[0].sent == sent_before


def test_draft_continue_refuses_while_busy_without_touching_the_drafting_view():
    s, adapter, view, bridges = make()
    s.draft_view["started"] = True
    s.chat("leggi")
    _hello(s, bridges)
    sent_before = list(bridges[0].sent)
    s.draft_continue("qualcosa")
    assert view.status == "Richiesta in corso: attendi o premi Annulla"
    assert s._draft_request is False
    assert bridges[0].sent == sent_before


def test_draft_start_leaves_the_drafting_view_untouched_when_the_core_fails_to_start():
    """Fix round 2, Important (still open after round 1): the busy refusal is guarded, but a

    core that fails to start (bridge.start() raises) is a second refusal path _submit takes,
    and draft_start/draft_answer/draft_continue used to mutate draft_view/_draft_request
    before knowing whether _submit would take the request at all. Nothing then ever clears
    _draft_request (no core process exists, so no final/error/exit ever fires), so the next
    unrelated request would show "Redazione in corso…" for a drafting that was never sent.
    """
    s, adapter, view, bridges = make(fail_start=True)
    s.draft_view["template"] = {"tipo_atto": "x", "campi": [
        {"nome": "creditore", "tipo": "testo", "obbligatorio": True}]}
    s.draft_start("x", {"creditore": "Alfa"}, "")
    assert s.draft_view["started"] is False and s._draft_request is False
    assert s.transcript[-1].startswith("Impossibile avviare il core")
    assert view.draft_status is None or view.draft_status[0] != "Redazione in corso…"


def test_draft_answer_leaves_the_drafting_view_untouched_when_the_core_fails_to_start():
    s, adapter, view, bridges = make(fail_start=True)
    s.draft_view["started"] = True
    s.draft_view["questions"] = [{"campo": "a"}]
    s.draft_answer({"a": "b"})
    assert s._draft_request is False
    assert s.transcript[-1].startswith("Impossibile avviare il core")


def test_draft_continue_leaves_the_drafting_view_untouched_when_the_core_fails_to_start():
    s, adapter, view, bridges = make(fail_start=True)
    s.draft_view["started"] = True
    s.draft_continue("qualcosa")
    assert s._draft_request is False
    assert s.transcript[-1].startswith("Impossibile avviare il core")


def test_draft_continue_leaves_the_drafting_view_untouched_on_a_dead_pipe_to_a_ready_core():
    """Fix round 3, Important (still open after rounds 1-2): _submit's "ready" branch used to

    report True unconditionally after handing the payload to _send_payload, even though
    _send_payload's own _send() can fail on a dead pipe to a core that was ready a moment
    ago (it calls shutdown(), which correctly resets _draft_request to False) — but the
    caller (draft_continue) then ran anyway and set _draft_request back to True and pushed
    "Redazione in corso…" with no bridge left to ever clear it again.
    """
    s, adapter, view, bridges = make()
    s.run_command("verify_citations", {})
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.1.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r1", "text": "Fatto.", "cancelled": False,
        "usage": None, "summary": {}}})
    assert s.state == "ready"
    s.draft_view["started"] = True
    bridges[0].fail_send = True                      # the core dies between two requests
    s.draft_continue("continua")
    assert s._draft_request is False
    assert view.draft_status != ("Redazione in corso…", True)
    assert s.state == "stopped"
    assert not any(line.startswith("Tu: continua") for line in s.transcript)
    assert "Core non raggiungibile" in s.transcript[-1]


def test_reference_round_trip_and_rebind_replays_the_drafting_view():
    s, adapter, view, bridges = make()
    s.set_reference("ricorso_rossi.docx", "RICORSO ...")
    _hello(s, bridges)
    assert bridges[0].sent[-1]["args"] == {"name": "ricorso_rossi.docx", "text": "RICORSO ..."}
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r1",
        "text": "Atto di riferimento: ricorso_rossi.docx (11 caratteri).",
        "summary": {"riferimento": {"name": "ricorso_rossi.docx", "chars": 11,
                                    "troncato": False}}}})
    assert view.reference == ("Caso simile: ricorso_rossi.docx (11 caratteri)", True)
    view2 = FakeView()
    s.bind(view2, lambda ev: None)
    assert view2.reference == ("Caso simile: ricorso_rossi.docx (11 caratteri)", True)
    assert view2.draft_status == ("Scegli un atto", False)
    assert view2.questions == [] and view2.partitions == []
    s.clear_reference()
    assert bridges[0].sent[-1]["args"] == {"text": ""}
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r2", "text": "Atto di riferimento rimosso.",
        "summary": {"riferimento": None}}})
    # s.bind(view2, ...) above made view2 the session's current view (as every other rebind
    # test in this file does: events after a rebind reach the fresh view, not the old one).
    assert view2.reference == ("Caso simile: nessuno", False)


def test_chat_and_research_get_turn_separators():
    s, adapter, view, bridges = make()
    s.chat("che dice?")
    _hello(s, bridges)
    assert s.transcript[-1] == "Tu: che dice?"
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r1", "text": "Dice X.",
        "usage": {"input_tokens": 1, "output_tokens": 1, "cost_usd": None},
        "summary": {"tool_calls": 0, "inserted": [], "flagged": [], "unverified": [],
                    "usage_totals": {"input_tokens": 1, "output_tokens": 1}}}})
    assert view.lines[-2:] == ["LibreLex: Dice X.", ""]
    s.research("usucapione")
    assert s.transcript[-1] == "Tu: ricerca: usucapione"


def test_cancelled_draft_turn_merges_into_the_view_without_resetting_it():
    """Plan 2 wire contract addition (post-brief): a cancelled draft turn still carries the

    draft keys (partitions inserted so far) and must be merged into draft_view, not discarded
    as a plain "[annullato]" note with nothing else updated.
    """
    s, adapter, view, bridges = make()
    s.draft_view["template"] = {"tipo_atto": "x", "campi": []}
    s.draft_start("x", {}, "")
    _hello(s, bridges)
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r1", "text": "", "cancelled": True,
        "usage": {"input_tokens": 5, "output_tokens": 1, "cost_usd": None},
        "summary": {"stopped": "cancelled", "tool_calls": 1, "inserted": [], "flagged": [],
                    "unverified": [],
                    "usage_totals": {"input_tokens": 5, "output_tokens": 1}, "tipo_atto": "x",
                    "domande": [],
                    "partizioni": [{"titolo": "Base: Ricorso", "from_id": "p:1",
                                   "to_id": "p:9"}],
                    "segnaposto_aperti": [], "completata": False, "riepilogo": "",
                    "ended_by": None, "base_errore": None}}})
    assert "[annullato]" in view.lines
    assert view.partitions == ["✓ Base: Ricorso"]
    assert s.draft_view["partitions"] == [
        {"titolo": "Base: Ricorso", "from_id": "p:1", "to_id": "p:9"}]
    assert view.draft_status == ("Compila i campi obbligatori e premi Avvia redazione", True)


def test_base_errore_reports_the_missing_base_in_status_and_transcript():
    s, adapter, view, bridges = make()
    s.draft_view["template"] = {"tipo_atto": "x", "campi": []}
    s.draft_start("x", {}, "")
    _hello(s, bridges)
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r1", "text": "Non riesco.",
        "usage": {"input_tokens": 5, "output_tokens": 1, "cost_usd": None},
        "summary": {"tool_calls": 1, "inserted": [], "flagged": [], "unverified": [],
                    "usage_totals": {"input_tokens": 5, "output_tokens": 1}, "tipo_atto": "x",
                    "domande": [], "partizioni": [], "segnaposto_aperti": [],
                    "completata": False, "riepilogo": "", "ended_by": None,
                    "base_errore": "strumento decreto_ingiuntivo non disponibile"}}})
    status = "Base non generata: strumento decreto_ingiuntivo non disponibile"
    draft_status = "Compila i campi obbligatori e premi Avvia redazione"
    assert view.draft_status == (draft_status, True)
    assert status in view.lines
    # M6: the failure is part of the drafting state, so a rebuilt panel is told again
    assert s.draft_view["base_errore"] == "strumento decreto_ingiuntivo non disponibile"
    fresh = FakeView()
    s.bind(fresh, lambda ev: None)
    assert fresh.draft_status == (draft_status, True)
    # a later turn that does produce a base clears it
    s.draft_continue("riprova")
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r2", "text": "Fatto.",
        "usage": {"input_tokens": 5, "output_tokens": 1, "cost_usd": None},
        "summary": {"tool_calls": 1, "inserted": [], "flagged": [], "unverified": [],
                    "usage_totals": {"input_tokens": 5, "output_tokens": 1}, "tipo_atto": "x",
                    "domande": [], "partizioni": [{"titolo": "Base", "from_id": "p:1",
                                                   "to_id": "p:9"}],
                    "segnaposto_aperti": [], "completata": False, "riepilogo": "",
                    "ended_by": None}}})
    assert s.draft_view["base_errore"] is None
    assert fresh.draft_status == (draft_status, True)


def test_a_reference_the_extension_cut_is_labelled_troncato():
    """I2: set_reference trims to MAX_REFERENCE_CHARS before sending, so the core's own

    ``troncato`` is always False and the lawyer was never told that only part of the similar
    case reached the model. The cut the extension made is OR-ed into the final's dict.
    """
    s, adapter, view, bridges = make()
    s.set_reference("x.odt", "a" * (MAX_REFERENCE_CHARS + 1))
    _hello(s, bridges)
    assert len(bridges[0].sent[-1]["args"]["text"]) == MAX_REFERENCE_CHARS
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r1", "text": "Atto di riferimento: x.odt.",
        "summary": {"riferimento": {"name": "x.odt", "chars": MAX_REFERENCE_CHARS,
                                    "troncato": False}}}})
    assert view.reference[0].endswith(", troncato)")
    assert s.draft_view["reference"]["troncato"] is True     # merged, so a rebuild keeps it
    fresh = FakeView()
    s.bind(fresh, lambda ev: None)
    assert fresh.reference[0].endswith(", troncato)")
    s.set_reference("y.odt", "b" * 10)                       # a short act that follows
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r2", "text": "Atto di riferimento: y.odt.",
        "summary": {"riferimento": {"name": "y.odt", "chars": 10, "troncato": False}}}})
    assert fresh.reference == ("Caso simile: y.odt (10 caratteri)", True)
    s.clear_reference()
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r3", "text": "Atto di riferimento rimosso.",
        "summary": {"riferimento": None}}})
    assert fresh.reference == ("Caso simile: nessuno", False)


def test_draft_start_validates_only_the_field_rows_the_panel_offers():
    """I3: the Redazione panel offers the first FIELD_ROWS fields of the template and names

    the rest in the notes line, so validating every mandatory field dead-ended a template
    with more of them: the lawyer could not fill what he was never shown. The model asks for
    the missing data through ``chiedi_dati``.
    """
    s, adapter, view, bridges = make()
    campi = [{"nome": f"c{n}", "tipo": "testo", "obbligatorio": True}
             for n in range(FIELD_ROWS + 1)]
    s.draft_view["template"] = {"tipo_atto": "x", "campi": campi}
    fields = {f"c{n}": "v" for n in range(FIELD_ROWS)}        # the offered rows, all filled
    s.draft_start("x", fields, "")
    _hello(s, bridges)
    assert bridges[0].sent[-1]["args"]["fields"] == fields
    assert s.draft_view["started"] is True
    s2, _adapter2, view2, bridges2 = make()                   # an offered row left empty
    s2.draft_view["template"] = {"tipo_atto": "x", "campi": campi}
    s2.draft_start("x", {f"c{n}": "v" for n in range(FIELD_ROWS - 1)}, "")
    assert view2.status == f"Compila i campi obbligatori: c{FIELD_ROWS - 1}" and not bridges2


def test_choosing_another_template_mid_drafting_keeps_the_resume_controls():
    """I4: the template_info final pushed started=False, which hides "Continua la redazione"

    on a drafting that is still under way: looking at another act's fields must not lose the
    only way back into the drafting. The typed values of the previous template do go.
    """
    s, adapter, view, bridges = make()
    s.draft_view.update(started=True, fields={"creditore": "Alfa"}, notes="fattura 12",
                        partitions=[{"titolo": "Base", "from_id": "p:1", "to_id": "p:9"}])
    info = {"tipo_atto": "y", "campi": [], "routing": {"tipo": "resource"}, "avvertenze": []}
    s.template("y")
    _hello(s, bridges)
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r1", "text": "Modello.", "summary": info}})
    assert view.template == info
    assert view.draft_status == ("Compila i campi obbligatori e premi Avvia redazione", True)
    # I5: another act, other fields — the stored copy goes with the rows the panel clears,
    # while the notes box (free text about the case, kept by the panel) stays as it was
    assert s.draft_view["fields"] == {} and s.draft_view["notes"] == "fattura 12"


def test_replay_drafting_gives_back_the_typed_values_and_is_the_only_path_bind_uses():
    """I5 and M2: what the lawyer typed is state (design §6.2), and one method replays the

    whole Redazione/Domande state: ``bind`` and a panel rebuilt on its own go through it.
    """
    s, adapter, view, bridges = make()
    info = {"tipo_atto": "x", "campi": [{"nome": "creditore", "tipo": "testo",
                                         "obbligatorio": True}],
            "routing": {"tipo": "resource"}, "avvertenze": []}
    s.draft_view.update(
        templates=[{"tipo_atto": "x", "descrizione": "Ricorso",
                    "categoria": "atti_introduttivi"}],
        template=info, fields={"creditore": "Alfa"}, notes="fattura 12",
        reference={"name": "x.odt", "chars": 10, "troncato": False},
        partitions=[{"titolo": "Base", "from_id": "p:1", "to_id": "p:9"}],
        open_placeholders=["[SEDE]"], questions=[{"campo": "sede", "domanda": "Sede?"}],
        answers_draft={"sede": "Milano"}, started=True)
    fresh = FakeView()
    s.replay_drafting(fresh)
    assert fresh.templates == (["atti_introduttivi · Ricorso"], None)
    assert fresh.template == info
    assert fresh.field_values == ({"creditore": "Alfa"}, "fattura 12")
    assert fresh.reference == ("Caso simile: x.odt (10 caratteri)", True)
    assert fresh.partitions == ["✓ Base", "… segnaposto aperti: 1"]
    assert fresh.draft_status == ("Compila i campi obbligatori e premi Avvia redazione", True)
    assert fresh.questions == [{"campo": "sede", "domanda": "Sede?"}]
    assert fresh.answer_values == {"sede": "Milano"}
    seen = []
    s.replay_drafting = seen.append          # bind replays through that one method only
    other = FakeView()
    s.bind(other, lambda ev: None)
    assert seen == [other]
    assert other.template is None and other.draft_status is None


def test_draft_answer_clears_the_stored_answers_only_when_the_request_is_taken():
    """I5: the answers typed into the Domande panel are kept for a rebuild until the turn

    that consumes them is on its way; a refused request must keep them on screen.
    """
    s, adapter, view, bridges = make()
    s.draft_view["questions"] = [{"campo": "sede"}]
    s.draft_view["answers_draft"] = {"sede": "Milano"}
    s.draft_answer({"sede": "Milano"})
    assert s.draft_view["answers_draft"] == {}
    s2, _adapter2, view2, _bridges2 = make()
    s2.draft_view["answers_draft"] = {"sede": "Milano"}       # no question pending: refused
    s2.draft_answer({"sede": "Milano"})
    assert s2.draft_view["answers_draft"] == {"sede": "Milano"}


def test_a_queued_draft_request_that_never_reaches_the_core_is_not_shown_as_started():
    """M4: a draft request submitted while the core is starting is taken by ``_submit`` and

    the drafting view commits to it, but the write that follows the hello can still hit a
    dead pipe: nothing would ever clear the "Redazione in corso…" it left behind.
    """
    s, adapter, view, bridges = make()
    s.draft_view["template"] = {"tipo_atto": "x", "campi": []}
    s.draft_start("x", {}, "")
    assert s.draft_view["started"] is True and s._draft_request is True
    bridges[0].fail_send = True              # the core died between the hello and its answer
    _hello(s, bridges)
    assert s._draft_request is False and s.draft_view["started"] is False
    assert view.draft_status == ("Compila i campi obbligatori e premi Avvia redazione", False)
    assert "Core non raggiungibile" in s.transcript[-1]
    # a drafting that already put a partition in the document is real: it stays started
    s2, _adapter2, view2, bridges2 = make()
    s2.draft_view.update(template={"tipo_atto": "x", "campi": []}, started=True,
                         partitions=[{"titolo": "Base", "from_id": "p:1", "to_id": "p:9"}])
    s2.draft_continue("ancora")
    bridges2[0].fail_send = True
    _hello(s2, bridges2)
    assert s2._draft_request is False and s2.draft_view["started"] is True
    assert view2.draft_status == ("Compila i campi obbligatori e premi Avvia redazione", True)


def test_an_error_on_the_start_request_drops_the_started_it_had_claimed():
    """M5: the core refusing the start (an unknown tipo_atto, a missing llm configuration)

    left the Redazione panel claiming a drafting that never produced a line, with "Continua
    la redazione" offered for a turn the core knows nothing about.
    """
    s, adapter, view, bridges = make()
    s.draft_view["template"] = {"tipo_atto": "x", "campi": []}
    s.draft_start("x", {}, "")
    _hello(s, bridges)
    assert s.draft_view["started"] is True
    s.handle_event({"kind": "message", "msg": {
        "type": "error", "request_id": "r1", "code": "llm_config",
        "message": "llm.model non impostato"}})
    assert s.draft_view["started"] is False and s._draft_request is False
    assert view.draft_status == ("Compila i campi obbligatori e premi Avvia redazione", False)
    # a start whose turn already inserted a partition stays started
    s2, _adapter2, view2, bridges2 = make()
    s2.draft_view["template"] = {"tipo_atto": "x", "campi": []}
    s2.draft_start("x", {}, "")
    _hello(s2, bridges2)
    s2.draft_view["partitions"] = [{"titolo": "Base", "from_id": "p:1", "to_id": "p:9"}]
    s2.handle_event({"kind": "message", "msg": {
        "type": "error", "request_id": "r1", "code": "tool_error", "message": "boom"}})
    assert s2.draft_view["started"] is True
    # an error on a later turn of the drafting is not a failed start
    s3, _adapter3, view3, bridges3 = make()
    s3.draft_view.update(template={"tipo_atto": "x", "campi": []}, started=True)
    s3.draft_continue("ancora")
    _hello(s3, bridges3)
    s3.handle_event({"kind": "message", "msg": {
        "type": "error", "request_id": "r1", "code": "tool_error", "message": "boom"}})
    assert s3.draft_view["started"] is True
    assert view3.draft_status == ("Compila i campi obbligatori e premi Avvia redazione", True)


def test_goto_partition_navigates_and_ignores_the_rows_that_are_not_partitions():
    """M11: the Partizioni list box carries one row per partition plus, when there are open

    placeholders, a trailing count that is not a position; every index outside the partitions
    themselves is a no-op.
    """
    s, adapter, view, bridges = make()
    s.draft_view["partitions"] = [{"titolo": "Base", "from_id": "p:1", "to_id": "p:9"}]
    s.draft_view["open_placeholders"] = ["[SEDE]"]
    s.goto_partition(0)
    assert adapter.calls[-1] == ("goto", "p:1")
    calls = list(adapter.calls)
    s.goto_partition(1)                      # the "… segnaposto aperti: 1" row
    s.goto_partition(-1)
    s.goto_partition(7)
    assert adapter.calls == calls


def test_a_core_that_dies_mid_drafting_stops_claiming_a_running_turn():
    """The exit event clears the in-flight draft request; the Redazione line has to hear it,

    or a core that crashed mid-drafting leaves "Redazione in corso…" on screen for good.
    """
    s, adapter, view, bridges = make()
    s.draft_view.update(template={"tipo_atto": "x", "campi": []}, started=True,
                        partitions=[{"titolo": "Base", "from_id": "p:1", "to_id": "p:9"}])
    s.draft_continue("ancora")
    _hello(s, bridges)
    assert view.draft_status == ("Compila i campi obbligatori e premi Avvia redazione", True)
    s.handle_event({"kind": "exit", "code": 1})
    assert s._draft_request is False
    assert view.draft_status == ("Compila i campi obbligatori e premi Avvia redazione", True)
