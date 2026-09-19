# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Per-document session: core lifecycle, request state and doc_call dispatch (spec §4.3, §5.2).

Everything here runs on the UI thread except ``post_event`` (reader thread), which only
forwards to the callback the panel registered. No UNO imports.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any, Protocol

from librelex_ext import PROTOCOL_VERSION, DocumentActionError, __version__
from librelex_ext.bridge import BridgeError
from librelex_ext.render import (
    render_draft_status,
    render_error,
    render_insert_summary,
    render_list_summary,
    render_partitions,
    render_reference,
    render_riepilogo,
    render_show_text,
    render_template_notes,
    render_turn_notes,
    render_usage,
    render_verify_summary,
)

# Kept in sync by hand with the core's own limit (core/src/librelex_core/agent/state.py):
# the core trims again, but a reference this size would already brush the 4 MiB stdio line
# limit once JSON-escaped, so the extension trims first.
MAX_REFERENCE_CHARS = 60_000


class View(Protocol):
    def append(self, text: str) -> None: ...
    def set_transcript(self, text: str) -> None: ...
    def set_status(self, text: str) -> None: ...
    def set_busy(self, busy: bool) -> None: ...
    def set_citations(self, labels: list[str]) -> None: ...
    def set_progress(self, done: int, total: int | None) -> None: ...
    def append_stream(self, text: str) -> None: ...
    def set_usage(self, text: str) -> None: ...
    def set_consent(self, summary: dict | None) -> None: ...
    def set_templates(self, labels: list[str], selected: int | None) -> None: ...
    def set_template(self, info: dict | None) -> None: ...
    def set_reference(self, text: str, present: bool) -> None: ...
    def set_partitions(self, labels: list[str]) -> None: ...
    def set_draft_status(self, text: str, started: bool) -> None: ...
    def set_questions(self, questions: list[dict]) -> None: ...


class NullView:
    def append(self, text: str) -> None: ...
    def set_transcript(self, text: str) -> None: ...
    def set_status(self, text: str) -> None: ...
    def set_busy(self, busy: bool) -> None: ...
    def set_citations(self, labels: list[str]) -> None: ...
    def set_progress(self, done: int, total: int | None) -> None: ...
    def append_stream(self, text: str) -> None: ...
    def set_usage(self, text: str) -> None: ...
    def set_consent(self, summary: dict | None) -> None: ...
    def set_templates(self, labels: list[str], selected: int | None) -> None: ...
    def set_template(self, info: dict | None) -> None: ...
    def set_reference(self, text: str, present: bool) -> None: ...
    def set_partitions(self, labels: list[str]) -> None: ...
    def set_draft_status(self, text: str, started: bool) -> None: ...
    def set_questions(self, questions: list[dict]) -> None: ...


def dispatch_doc_call(adapter: Any, action: str, args: dict) -> dict:
    """Map a wire doc_call onto the adapter and wrap the result as the core expects."""
    if action == "get_document_info":
        return adapter.get_document_info()
    if action == "read_selection":
        return adapter.read_selection()
    if action == "read_paragraphs":
        from_ = args.get("from_", args.get("from"))
        return {"paragraphs": adapter.read_paragraphs(from_, args.get("to"))}
    if action == "find_text":
        return {"occurrences": adapter.find_text(args["query"], args.get("paragraph_id"))}
    if action == "insert_markdown":
        return adapter.insert_markdown(args["where"], args["markdown"], args["undo_label"],
                                       args.get("bookmark"), args.get("author"))
    if action == "replace_selection":
        return adapter.replace_selection(args["markdown"], args["undo_label"])
    if action == "replace_text":
        return adapter.replace_text(args["query"], args["replacement"], args["undo_label"],
                                    args.get("paragraph_id"), bool(args.get("all", False)))
    if action == "add_comment":
        return {"anchored": adapter.add_comment(
            args["paragraph_id"], args["start"], args["end"], args["expected_text"],
            args["author"], args["text"])}
    if action == "remove_comments":
        return {"count": adapter.remove_comments(args["author"])}
    if action == "goto":
        adapter.goto(args["paragraph_id"])
        return {}
    raise DocumentActionError(f"azione sconosciuta: {action}")


class Session:
    def __init__(self, adapter: Any, bridge_factory: Callable[[Callable[[dict], None]], Any],
                 doc_id: str, lo_version: str, has_markdown_filter: bool, config_path: str):
        self.adapter = adapter
        self.bridge_factory = bridge_factory
        self.doc_id, self.lo_version = doc_id, lo_version
        self.has_markdown_filter, self.config_path = has_markdown_filter, config_path
        self.bridge: Any = None
        self.state = "stopped"
        self.pending: Callable[[str], dict] | None = None
        self.pending_label: str | None = None
        self.request_id: str | None = None
        # Guided drafting (spec §6): the state behind the Redazione and Domande panels.
        self.draft_view: dict = {
            "templates": [], "query": None, "template": None, "fields": {}, "notes": "",
            "reference": None, "questions": [], "partitions": [], "open_placeholders": [],
            "started": False, "done": False, "stopped": None,
        }
        # True while a draft (start/answer/continue) request is queued or in flight: drives
        # the "Redazione in corso…" status independently of draft_view["started"], which
        # tracks the guided flow itself rather than a single request.
        self._draft_request = False
        self.pending_consent: tuple[str, str] | None = None
        # what a rebuilt Azioni panel has to be told again (it is created empty): the summary
        # of the consent the core is still waiting on, and the usage line of the last turn
        self.consent_summary: dict | None = None
        self.usage_text: str = ""
        self._n = 0
        self.transcript: list[str] = []
        self.citations: list[tuple[str, str, str]] = []
        self.texts: dict[str, str] = {}
        self.view: View = NullView()
        self._buffer: list[dict] = []
        self.ui_post: Callable[[dict], None] = self._buffer.append
        self._streamed = False
        self._stream_buffer = ""

    # --- panel binding -------------------------------------------------------
    def bind(self, view: View, ui_post: Callable[[dict], None]) -> None:
        self.view, self.ui_post = view, ui_post
        view.set_transcript("\n".join(self.transcript))
        view.set_citations([label for label, _, _ in self.citations])
        view.set_templates(self._template_labels(), None)
        view.set_template(self.draft_view["template"])
        view.set_reference(render_reference(self.draft_view["reference"]),
                           bool(self.draft_view["reference"]))
        view.set_partitions(render_partitions(self.draft_view["partitions"],
                                              self.draft_view["open_placeholders"]))
        self._refresh_draft_status()
        view.set_questions(self.draft_view["questions"])
        self._set_busy(self.state in ("starting", "busy"))
        view.set_consent(self.consent_summary)
        view.set_usage(self.usage_text)
        buffered, self._buffer = self._buffer, []
        for ev in buffered:
            ui_post(ev)

    def unbind(self) -> None:
        self.view = NullView()
        self.ui_post = self._buffer.append

    def post_event(self, ev: dict) -> None:
        """Called from the bridge reader thread: hand the event to the UI thread."""
        self.ui_post(ev)

    # --- user actions (UI thread) -------------------------------------------
    def run_command(self, name: str, args: dict, label: str | None = None) -> bool:
        """Submit a command; returns whether it was queued or sent (see ``_submit``)."""
        return self._submit(name, lambda rid: {"type": "command", "id": rid,
                                                "doc_id": self.doc_id, "name": name,
                                                "args": args}, label)

    def chat(self, message: str) -> None:
        if not message.strip():
            self.view.set_status("Scrivi un messaggio")
            return
        context = self._document_context()
        self._submit(None, lambda rid: {"type": "chat", "id": rid, "doc_id": self.doc_id,
                                        "message": message, "context": context},
                     label=f"Tu: {message}")

    def research(self, question: str) -> None:
        self.run_command("research", {"question": question} if question.strip() else {},
                         label=f"Tu: ricerca: {question or 'testo selezionato'}")

    # --- guided drafting (spec §6) -------------------------------------------
    def templates(self, query: str = "") -> None:
        self.run_command("list_templates", {"query": query.strip()} if query.strip() else {})

    def template(self, tipo_atto: str) -> None:
        self.run_command("template_info", {"tipo_atto": tipo_atto})

    def set_reference(self, name: str, text: str) -> None:
        """Forward a reference file to the core; the panel already read it from disk."""
        self.run_command("set_reference", {"name": name, "text": text[:MAX_REFERENCE_CHARS]})

    def clear_reference(self) -> None:
        self.run_command("set_reference", {"text": ""})

    def draft_start(self, tipo_atto: str, fields: dict[str, str], notes: str) -> None:
        if not tipo_atto:
            self.view.set_status("Scegli prima un tipo di atto")
            return
        template = self.draft_view.get("template") or {}
        missing = [c["nome"] for c in template.get("campi", [])
                  if c.get("obbligatorio") and not (fields.get(c["nome"]) or "").strip()]
        if missing:
            self.view.set_status(f"Compila i campi obbligatori: {', '.join(missing)}")
            return
        # draft_view/_draft_request are mutated only once the request is actually queued or
        # sent (run_command's return value): any refusal (busy, the core failing to start,
        # or a dead pipe on the hello) must leave the Redazione panel exactly as it was, or a
        # drafting that never reached the core would be shown as under way.
        if not self.run_command(
                "draft", {"action": "start", "tipo_atto": tipo_atto, "fields": fields,
                         "notes": notes},
                label=f"Tu: avvio redazione {tipo_atto} ({len(fields)} campi)"):
            return
        self.draft_view["fields"], self.draft_view["notes"] = fields, notes
        self.draft_view["started"] = True
        self._draft_request = True
        self._refresh_draft_status()

    def draft_answer(self, answers: dict[str, str]) -> None:
        if not self.draft_view["questions"]:
            self.view.set_status("Nessuna domanda in sospeso")
            return
        if not self.run_command("draft", {"action": "answer", "answers": answers},
                                label=f"Tu: risposte a {len(answers)} domande"):
            return
        self._draft_request = True
        self._refresh_draft_status()

    def draft_continue(self, message: str = "") -> None:
        if not self.draft_view["started"]:
            self.view.set_status("Nessuna redazione in corso")
            return
        if not self.run_command(
                "draft", {"action": "continue", "message": message.strip()},
                label=f"Tu: continua{': ' + message if message else ''}"):
            return
        self._draft_request = True
        self._refresh_draft_status()

    def goto_partition(self, index: int) -> None:
        partitions = self.draft_view["partitions"]
        if not (0 <= index < len(partitions)):
            return
        try:
            self.adapter.goto(partitions[index]["from_id"])
        except Exception as e:  # navigation is best effort, as in select_citation
            self.view.set_status(f"Posizione non raggiungibile: {e}")

    def _template_labels(self) -> list[str]:
        return [f"{m['categoria']} · {m['descrizione']}" for m in self.draft_view["templates"]]

    def _document_context(self) -> dict:
        try:
            info = self.adapter.get_document_info()
        except Exception:
            return {}
        return {"title": info.get("title", ""), "has_selection": info.get("has_selection", False),
                "cursor_paragraph": info.get("cursor_paragraph")}

    def _submit(self, name: str | None, payload_factory: Callable[[str], dict],
               label: str | None = None) -> bool:
        """Queue or send the request; return whether it was taken.

        False on every refusal (busy, the core failing to start, a dead pipe on the hello):
        callers that mutate their own state before submitting (the three draft methods) rely
        on this to know whether that state actually reflects a request the core will see.
        """
        if self.state == "busy":
            self.view.set_status("Richiesta in corso: attendi o premi Annulla")
            return False
        if self.state == "starting":
            self.pending, self.pending_label = payload_factory, label
            return True
        if self.state == "stopped":
            try:
                self.bridge = self.bridge_factory(self.post_event)
                self.bridge.start()
            except BridgeError as e:
                self.bridge = None
                self._append(f"Impossibile avviare il core: {e}")
                return False
            self.state = "starting"
            self.pending, self.pending_label = payload_factory, label
            self._set_busy(True)
            self.view.set_status("Avvio del core...")
            return self._send({"type": "hello", "id": "h1", "protocol": PROTOCOL_VERSION,
                               "extension_version": __version__, "lo_version": self.lo_version,
                               "has_markdown_filter": self.has_markdown_filter})
        self._send_payload(payload_factory, label)
        return True

    def cancel(self) -> None:
        if self.state == "busy" and self.request_id and self.bridge is not None:
            if self._send({"type": "cancel", "id": self.request_id, "doc_id": self.doc_id}):
                self.view.set_status("Annullamento...")

    def select_citation(self, index: int) -> None:
        if not (0 <= index < len(self.citations)):
            return
        _label, paragraph_id, canonical = self.citations[index]
        try:
            self.adapter.goto(paragraph_id)
        except Exception as e:  # navigation is best effort
            self.view.set_status(f"Posizione non raggiungibile: {e}")
        # Cache first: a text we already downloaded needs no core, so it is shown even
        # while another request is running; only an actual fetch has to wait.
        if canonical in self.texts:
            self._append(self.texts[canonical])
        elif self.state not in ("ready", "stopped"):
            self.view.set_status("Testo disponibile a fine richiesta: riprova tra poco")
        else:
            self.run_command("show_text", {"reference": canonical})

    def note(self, text: str) -> None:
        """Write a view-agnostic message to the transcript (startup banner, settings info)

        that does not come from the core, keeping ``self.transcript`` and the view in sync so
        it survives the panel being closed and reopened.
        """
        self._append(text)

    def clear_transcript(self) -> None:
        """Empty the answers pane and the replay buffer a reopened panel is rebuilt from."""
        self.transcript.clear()
        self.view.set_transcript("")

    def answer_consent(self, decision: str) -> None:
        if self.pending_consent is None:
            return
        request_id, call_id = self.pending_consent
        self._clear_pending_consent()
        if self.bridge is not None:
            self._send({"type": "consent_result", "id": request_id, "call_id": call_id,
                        "decision": decision})

    def shutdown(self) -> None:
        if self.bridge is not None:
            try:
                self.bridge.stop()
            finally:
                self.bridge = None
        self.state = "stopped"
        self.pending = None
        self.pending_label = None
        self.request_id = None
        self._draft_request = False

    # --- events from the core (UI thread) -----------------------------------
    def handle_event(self, ev: dict) -> None:
        kind = ev.get("kind")
        if kind == "exit":
            was_active = self.state in ("starting", "busy")
            self.bridge = None
            self.state, self.pending, self.pending_label, self.request_id = (
                "stopped", None, None, None)
            self._draft_request = False
            self._flush_stream()
            self._clear_pending_consent()
            self._set_busy(False)
            self.view.set_progress(0, None)
            self.view.set_status("Core non attivo")
            if was_active:
                log = os.path.join(os.path.dirname(self.config_path), "core-stderr.log")
                self._append(f"Il core si è chiuso inaspettatamente (codice {ev.get('code')}). "
                             f"Dettagli in {log}. Riprova: verrà riavviato.")
            return
        if kind == "garbage":
            return
        if kind != "message":
            return
        msg = ev["msg"]
        handler = getattr(self, f"_on_{msg.get('type', '')}", None)
        if handler is not None:
            handler(msg)

    def _on_hello_ok(self, msg: dict) -> None:
        for w in msg.get("warnings") or []:
            self._append(f"Avviso del core: {w}")
        if msg.get("protocol") != PROTOCOL_VERSION:
            self._append(
                f"Core incompatibile: protocollo {msg.get('protocol')}, richiesto "
                f"{PROTOCOL_VERSION} (core {msg.get('core_version')}). Aggiorna l'estensione."
            )
            self.shutdown()
            self._set_busy(False)
            return
        self.state = "ready"
        self.view.set_status("Pronto")
        if self.pending is not None:
            payload_factory, label = self.pending, self.pending_label
            self.pending = self.pending_label = None
            self._send_payload(payload_factory, label)
        else:
            self._set_busy(False)

    def _on_status(self, msg: dict) -> None:
        self.view.set_status(msg.get("text", ""))

    def _on_progress(self, msg: dict) -> None:
        done, total = msg.get("done", 0), msg.get("total", 0)
        self.view.set_status(f"Verificate {done} di {total}")
        self.view.set_progress(done, total)

    def _on_delta(self, msg: dict) -> None:
        text = msg.get("text", "")
        if not self._streamed:
            text = "LibreLex: " + text     # only the first chunk of the turn carries it
        self._streamed = True
        self._stream_buffer += text
        self.view.append_stream(text)

    def _on_log(self, msg: dict) -> None:
        return

    def _on_consent_request(self, msg: dict) -> None:
        self.pending_consent = (msg["request_id"], msg["call_id"])
        self.consent_summary = msg.get("summary")
        self.view.set_consent(self.consent_summary)
        self.view.set_status("In attesa del consenso")

    def _on_doc_call(self, msg: dict) -> None:
        if self.bridge is None:
            # shutdown() already ran (e.g. the document closed mid-request); the reader
            # thread had already queued this event before the pipe was torn down. There is
            # no bridge left to answer on, so drop it.
            return
        reply = {"type": "doc_result", "id": msg["request_id"], "call_id": msg["call_id"]}
        try:
            reply.update(ok=True, result=dispatch_doc_call(self.adapter, msg["action"],
                                                           msg.get("args") or {}))
        except Exception as e:
            reply.update(ok=False, error=f"{type(e).__name__}: {e}"
                         if not isinstance(e, DocumentActionError) else str(e))
        self.bridge.send(reply)

    def _on_final(self, msg: dict) -> None:
        self.state, self.request_id = "ready", None
        self._draft_request = False
        self._set_busy(False)
        self.view.set_progress(0, None)
        self.view.set_status("Pronto")
        self._clear_pending_consent()
        was_streamed = self._streamed
        self._flush_stream()
        summary = msg.get("summary") or {}
        if "modelli" in summary:
            self.draft_view["templates"] = summary["modelli"]
            self.draft_view["query"] = summary.get("query")
            self.view.set_templates(self._template_labels(), None)
            self._append(msg["text"])
        elif "campi" in summary and "routing" in summary:
            self.draft_view["template"] = summary
            self.view.set_template(summary)
            self.view.set_draft_status(render_draft_status(self._status_view()), False)
            self._append(render_template_notes(summary))
        elif "riferimento" in summary and not isinstance(summary.get("riferimento"), str):
            # A dict-or-None value is the new set_reference final; a plain string is the
            # older insert_norm final, which also happens to use the "riferimento" key and
            # is handled further down, unchanged.
            ref = summary["riferimento"]
            self.draft_view["reference"] = ref
            self.view.set_reference(render_reference(ref), bool(ref))
            self._append(msg["text"])
        elif was_streamed or "usage_totals" in summary or "tool_calls" in summary:
            # A model turn (chat, research or draft) is recognised by the shape of its final,
            # not by whether anything was streamed: a turn that ends on tool calls only
            # (iteration limit, timeout while tools run) emits no delta and must still show
            # its notes ([interrotto: ...], the inserted/flagged/unverified lines) and the
            # usage line. A streamed turn always replays through here, cancelled or not: the
            # cancellation shows up as a "[annullato]" note (render_turn_notes reads
            # summary["stopped"]), not as a separate "Annullato." line. A draft turn
            # (identified by "partizioni") additionally merges into draft_view below,
            # cancelled or not (plan 2 wire contract: a cancelled draft Final still carries
            # the partitions inserted so far).
            if not was_streamed and (msg.get("text") or "").strip():
                self._append("LibreLex: " + msg["text"])     # the prose the turn never streamed
            self._append("")
            for note in render_turn_notes(summary):
                self._append(note)
            self._set_usage(render_usage(msg.get("usage"), summary.get("usage_totals")))
            if "partizioni" in summary:
                self._merge_draft_turn(summary)
        elif msg.get("cancelled"):
            self._append(msg.get("text") or "Annullato.")
        elif "elenco" in summary or "per_verdetto" in summary:
            text, items = render_verify_summary(summary)
            self._set_citations(items)
            self._append(text)
        elif "citazioni" in summary:
            text, items = render_list_summary(summary)
            self._set_citations(items)
            self._append(text)
        elif "testo" in summary and "riferimento" in summary:
            rendered = render_show_text(summary)
            self.texts[summary["riferimento"]] = rendered
            self._append(rendered)
        elif "riferimento" in summary:
            self._append(render_insert_summary(summary))
        else:
            self._append(msg.get("text") or "Completato.")

    def _merge_draft_turn(self, summary: dict) -> None:
        """A draft turn's Final (start/answer/continue, cancelled or not): update draft_view

        and the Redazione/Domande panels. ``base_errore`` (wire contract addition) overrides
        the computed status with the base-generation failure, when the core reports one.
        """
        self.draft_view["questions"] = summary.get("domande") or []
        self.draft_view["partitions"] = summary.get("partizioni") or []
        self.draft_view["open_placeholders"] = summary.get("segnaposto_aperti") or []
        self.draft_view["done"] = summary.get("completata", False)
        self.draft_view["started"] = True
        self.draft_view["stopped"] = summary.get("stopped")
        self.view.set_questions(self.draft_view["questions"])
        self.view.set_partitions(render_partitions(self.draft_view["partitions"],
                                                    self.draft_view["open_placeholders"]))
        base_errore = summary.get("base_errore")
        if base_errore:
            status = f"Base non generata: {base_errore}"
            self.view.set_draft_status(status, True)
            self._append(status)
        else:
            self._refresh_draft_status()
        if self.draft_view["done"] and summary.get("riepilogo"):
            self._append(render_riepilogo(summary["riepilogo"]))

    def _on_error(self, msg: dict) -> None:
        if self.state == "busy" and msg.get("request_id") in (self.request_id, None):
            self.state, self.request_id = "ready", None
            self._draft_request = False
            self._set_busy(False)
            self.view.set_status("Pronto")
        self.view.set_progress(0, None)
        self._flush_stream()
        self._clear_pending_consent()
        self._append(render_error(msg.get("code", "?"), msg.get("message", ""), self.config_path))

    # --- helpers -------------------------------------------------------------
    def _send(self, msg: dict) -> bool:
        """Write to the core, reporting a dead pipe in the panel instead of raising.

        Every caller runs inside a UNO listener (a button click or an AsyncCallback), where an
        escaping ``BridgeError`` is swallowed by pyuno: the user would see nothing and the
        buttons would stay disabled until the ``exit`` event happened to be drained. The
        typical trigger is a first run where ``uv run --frozen`` cannot build the environment,
        so the child dies and this very first write hits EPIPE.
        """
        try:
            self.bridge.send(msg)
            return True
        except BridgeError as e:
            self.shutdown()          # drops the bridge; the next command restarts it
            self._set_busy(False)
            self.view.set_status("Core non attivo")
            self._append(f"Core non raggiungibile: {e}. Riprova: verrà riavviato.")
            return False

    def _send_payload(self, payload_factory: Callable[[str], dict],
                      label: str | None = None) -> None:
        self._n += 1
        self.request_id = f"r{self._n}"
        self.state = "busy"
        self._set_busy(True)
        self.view.set_status("Invio della richiesta...")
        if label is not None:
            self._append(label)
        self._send(payload_factory(self.request_id))

    def _flush_stream(self) -> None:
        if self._streamed:
            self.transcript.append(self._stream_buffer)
        self._streamed = False
        self._stream_buffer = ""

    def _set_busy(self, busy: bool) -> None:
        self.view.set_busy(busy)
        if busy and self._draft_request:
            self._refresh_draft_status()

    def _refresh_draft_status(self) -> None:
        self.view.set_draft_status(render_draft_status(self._status_view()),
                                   self.draft_view["started"])

    def _status_view(self) -> dict:
        return {**self.draft_view, "busy": self._draft_request}

    def _clear_pending_consent(self) -> None:
        if self.pending_consent is not None:
            self.pending_consent = self.consent_summary = None
            self.view.set_consent(None)

    def _set_usage(self, text: str) -> None:
        """Show the usage line and remember it, so a rebuilt panel can replay it."""
        self.usage_text = text
        self.view.set_usage(text)

    def _append(self, text: str) -> None:
        self.transcript.append(text)
        self.view.append(text)

    def _set_citations(self, items: list[tuple[str, str, str]]) -> None:
        self.citations = items
        self.view.set_citations([label for label, _, _ in items])
