# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Per-document session: core lifecycle, request state and doc_call dispatch (spec §4.3, §5.2).

Everything here runs on the UI thread except ``post_event`` (reader thread), which only
forwards to the callback the panel registered. No UNO imports.
"""
from __future__ import annotations

import os
import urllib.parse
from collections.abc import Callable
from contextlib import suppress
from typing import Any, Protocol

from librelex_ext import PROTOCOL_VERSION, DocumentActionError, __version__, letterheads
from librelex_ext.bridge import BridgeError
from librelex_ext.layout import FIELD_ROWS  # pure table module: no UNO import here
from librelex_ext.render import (
    EXPECTED_PARTITIONS,
    render_attachments,
    render_base_error,
    render_draft_status,
    render_error,
    render_expected_partitions,
    render_insert_summary,
    render_letterhead_labels,
    render_list_summary,
    render_log_insert,
    render_partitions,
    render_reference,
    render_riepilogo,
    render_show_text,
    render_summary,
    render_template_notes,
    render_turn_notes,
    render_usage,
    render_verify_summary,
)

# Kept in sync by hand with the core's own limit (core/src/librelex_core/agent/state.py):
# the core trims again, but a reference this size would already brush the 4 MiB stdio line
# limit once JSON-escaped, so the extension trims first.
MAX_REFERENCE_CHARS = 60_000

# Drafting workbench (design §4.2, §3.6): the case documents are sent as one replaced set.
MAX_ATTACHMENT_CHARS = 60_000
MAX_ATTACHMENTS = 12
MAX_ATTACHMENTS_CHARS = 300_000
MAX_LOG_LINES = 200
ACT_EXTENSIONS = (".odt", ".docx", ".doc", ".rtf", ".txt")


def drop_role(name: str, reference_present: bool) -> str:
    """Where a file dropped on the Redazione panel (design §3.1) lands: the reference slot

    (act-like extension, empty slot) or the attachments set (everything else, and a second
    act-like file once the reference is already taken).
    """
    if name.lower().endswith(ACT_EXTENSIONS) and not reference_present:
        return "reference"
    return "attachment"


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
    def set_field_values(self, fields: dict, notes: str) -> None: ...
    def set_answer_values(self, answers: dict) -> None: ...
    def set_step(self, step: int) -> None: ...
    def set_log(self, lines: list[str]) -> None: ...
    def append_log(self, line: str) -> None: ...
    def set_expected_partitions(self, labels: list[str]) -> None: ...
    def set_attachments(self, labels: list[str]) -> None: ...
    def set_letterheads(self, labels: list[str], selected: int) -> None: ...
    def set_summary(self, text: str) -> None: ...


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
    def set_field_values(self, fields: dict, notes: str) -> None: ...
    def set_answer_values(self, answers: dict) -> None: ...
    def set_step(self, step: int) -> None: ...
    def set_log(self, lines: list[str]) -> None: ...
    def append_log(self, line: str) -> None: ...
    def set_expected_partitions(self, labels: list[str]) -> None: ...
    def set_attachments(self, labels: list[str]) -> None: ...
    def set_letterheads(self, labels: list[str], selected: int) -> None: ...
    def set_summary(self, text: str) -> None: ...


def dispatch_doc_call(adapter: Any, action: str, args: dict, act_styles: bool = False) -> dict:
    """Map a wire doc_call onto the adapter and wrap the result as the core expects.

    ``act_styles`` (design §5.3) is forwarded only to ``insert_markdown``: it is the caller's
    decision (a drafting insertion vs. an ordinary one), never something the wire args carry.
    """
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
                                       args.get("bookmark"), args.get("author"),
                                       act_styles=act_styles)
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
        # ``fields``/``notes``/``answers_draft`` are what the lawyer typed and has not sent
        # yet: it is state like the rest (design §6.2), kept here so a panel rebuilt by a
        # deck switch gets it back through ``replay_drafting``.
        self.draft_view: dict = {
            "templates": [], "query": None, "template": None, "fields": {}, "notes": "",
            "answers_draft": {}, "reference": None, "questions": [], "partitions": [],
            "open_placeholders": [], "started": False, "done": False, "stopped": None,
            "base_errore": None, "step": 1, "log": [], "expected_partitions": [],
            "attachments": [], "letterheads": [], "letterhead": None,
        }
        # The committed set of case documents (design §4): what the core last confirmed
        # through a `set_attachments` final. ``_attachments_pending`` is the set sent and not
        # yet answered (committed on the final, discarded on error or exit); the whole set is
        # resent on every add/remove, never a delta.
        self._attachment_texts: list[dict] = []
        self._attachments_pending: list[dict] | None = None
        self._attachments_request_id: str | None = None
        self._attachments_id_pending = False
        # The last rendered end-of-drafting summary (design §3.4), kept for replay_drafting.
        self._summary_text: str = ""
        # True while a draft (start/answer/continue) request is queued or in flight: drives
        # the "Redazione in corso…" status independently of draft_view["started"], which
        # tracks the guided flow itself rather than a single request.
        self._draft_request = False
        # The id of the in-flight `draft` start request, so an error that kills it can undo
        # the "started" the panel committed to (a start is the one draft request whose
        # failure means no drafting ever began). ``_draft_start_pending`` covers the window
        # where the start is queued behind the hello and has no id yet: ``_send_payload``
        # assigns it one request later.
        self._draft_start_request_id: str | None = None
        self._draft_start_pending = False
        # Whether the reference act the lawyer chose was cut by MAX_REFERENCE_CHARS before
        # it was sent: the core only ever sees the trimmed text, so its own `troncato` says
        # nothing about this cut (I2).
        self._reference_truncated = False
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
        self.replay_drafting(view)
        self._set_busy(self.state in ("starting", "busy"))
        view.set_consent(self.consent_summary)
        view.set_usage(self.usage_text)
        buffered, self._buffer = self._buffer, []
        for ev in buffered:
            ui_post(ev)

    def replay_drafting(self, view: View) -> None:
        """Show ``view`` the whole guided-drafting state the session kept (spec §5.1).

        The one replay path: ``bind`` calls it for a freshly bound view, and a Redazione or
        Domande panel rebuilt on its own (deck switch, collapse and expand) calls it for
        itself. The eight calls are the six that describe the drafting plus the two that
        give back what the lawyer had typed and not sent; each panel ignores the calls whose
        controls belong to the other one, so both kinds can go through the same method.

        ``set_field_values`` must follow ``set_template`` and ``set_answer_values`` must
        follow ``set_questions``: those two clear the rows (another act, other values) and
        decide which names the rows carry, so the stored values are written back after them.
        ``set_step`` is last: every other call may belong to the step being left, and the
        panel toggles visibility on ``set_step``.
        """
        draft = self.draft_view
        view.set_templates(self._template_labels(), None)
        view.set_template(draft["template"])
        view.set_field_values(draft["fields"], draft["notes"])
        view.set_reference(render_reference(draft["reference"]), bool(draft["reference"]))
        view.set_partitions(render_partitions(draft["partitions"], draft["open_placeholders"]))
        view.set_draft_status(render_draft_status(self._status_view()), draft["started"])
        view.set_questions(draft["questions"])
        view.set_answer_values(draft["answers_draft"])
        view.set_attachments(render_attachments(draft["attachments"]))
        view.set_letterheads(*self._letterhead_selection())
        view.set_log(draft["log"])
        view.set_expected_partitions(render_expected_partitions(
            draft["expected_partitions"], draft["partitions"]))
        view.set_summary(self._summary_text)
        view.set_step(draft["step"])

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
        """Forward a reference file to the core; the panel already read it from disk.

        Whether the text was cut here is remembered: the core sees only what it was sent, so
        its own ``troncato`` cannot report this cut (I2).
        """
        self._reference_truncated = len(text) > MAX_REFERENCE_CHARS
        self.run_command("set_reference", {"name": name, "text": text[:MAX_REFERENCE_CHARS]})

    def clear_reference(self) -> None:
        self._reference_truncated = False
        self.run_command("set_reference", {"text": ""})

    def draft_start(self, tipo_atto: str, fields: dict[str, str], notes: str) -> None:
        if not tipo_atto:
            self._refuse_draft("Scegli prima un tipo di atto")
            return
        template = self.draft_view.get("template") or {}
        # Only the fields the Redazione panel actually offers (its first FIELD_ROWS rows)
        # are validated: a template with more mandatory fields than rows would otherwise
        # dead-end on data the lawyer was never shown. The model asks for the rest through
        # ``chiedi_dati``, and the panel names them in its notes line.
        missing = [c["nome"] for c in template.get("campi", [])[:FIELD_ROWS]
                  if c.get("obbligatorio") and not (fields.get(c["nome"]) or "").strip()]
        if missing:
            self._refuse_draft(f"Compila i campi obbligatori: {', '.join(missing)}")
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
        # The id the core will answer for: _on_error undoes the "started" below when this
        # very request fails (M5). A start queued behind the hello has no id yet, and
        # _send_payload fills it in when the hello is answered.
        self._draft_start_request_id = self.request_id
        self._draft_start_pending = self.request_id is None
        self.draft_view["fields"], self.draft_view["notes"] = fields, notes
        self.draft_view["started"] = True
        self._draft_request = True
        # The log is reset for the new drafting before anything can write to it (F4): a
        # letterhead failure logged by _apply_letterhead below must survive, not be wiped by
        # this reset.
        self.draft_view["log"] = []
        self.view.set_log([])
        # design §5.3: the letterhead is applied before the base enters the document; a
        # failure is logged, never raised (the drafting still starts on a plain document).
        self._apply_letterhead()
        self._log(f"Avvio della redazione: {tipo_atto}")
        routing = template.get("routing") or {}
        expected = (["Base"] if routing.get("tipo") == "tool_diretto" else []) + list(
            EXPECTED_PARTITIONS)
        self.draft_view["expected_partitions"] = expected
        self.view.set_expected_partitions(render_expected_partitions(
            expected, self.draft_view["partitions"]))
        self._set_step(3)

    def draft_answer(self, answers: dict[str, str]) -> None:
        if not self.draft_view["questions"]:
            self._refuse_draft("Nessuna domanda in sospeso")
            return
        if not self.run_command("draft", {"action": "answer", "answers": answers},
                                label=f"Tu: risposte a {len(answers)} domande"):
            return
        # the answers are on their way: the Domande panel starts a fresh round (I5)
        self.draft_view["answers_draft"] = {}
        self._draft_request = True
        self._set_step(3)
        self._log("Risposte inviate")

    def draft_continue(self, message: str = "") -> None:
        if not self.draft_view["started"]:
            self._refuse_draft("Nessuna redazione in corso")
            return
        message = message.strip()
        if not self.run_command(
                "draft", {"action": "continue", "message": message},
                label=f"Tu: continua{': ' + message if message else ''}"):
            return
        self._draft_request = True
        self._set_step(3)
        self._log(f"Riprendo: {message or 'continua'}")

    def new_drafting(self) -> None:
        """Back to step 1 for another act (design §3.4): attachments and letterhead stay."""
        if self._draft_request:
            self._refuse_draft("Attendi la fine del turno o premi Annulla")
            return
        self.draft_view.update(
            answers_draft={}, questions=[], partitions=[], open_placeholders=[],
            started=False, done=False, stopped=None, base_errore=None, log=[],
            expected_partitions=[])
        self._summary_text = ""
        self.view.set_questions([])
        self.view.set_answer_values({})
        self.view.set_partitions([])
        self.view.set_log([])
        self.view.set_expected_partitions([])
        self.view.set_summary("")
        self._set_step(1)

    def verify_act(self) -> None:
        self.run_command("verify_citations", {"scope": "document"},
                         label="Tu: verifica citazioni dell'atto")

    # --- drafting workbench: case documents (design §4) -----------------------
    def add_attachment(self, name: str, text: str, kind: str) -> bool:
        if self.state == "starting":
            # The single ``pending`` slot would drop one of two attachment requests queued
            # behind the hello (F6): refuse instead of silently losing one.
            self._refuse_draft("Attendi l'avvio del core")
            return False
        if len(self._attachment_texts) >= MAX_ATTACHMENTS:
            self._refuse_draft("Allegati: al massimo 12 documenti")
            return False
        trimmed = text[:MAX_ATTACHMENT_CHARS]
        troncato = len(text) > MAX_ATTACHMENT_CHARS
        total = sum(len(a["text"]) for a in self._attachment_texts) + len(trimmed)
        if total > MAX_ATTACHMENTS_CHARS:
            self._refuse_draft("Allegati: al massimo 300.000 caratteri in totale")
            return False
        new = {"name": name, "text": trimmed, "kind": kind, "troncato": troncato}
        pending = [*self._attachment_texts, new]
        return self._send_attachments(pending, label=f"Tu: allegato {name}")

    def remove_attachment(self, index: int) -> bool:
        if self.state == "starting":
            self._refuse_draft("Attendi l'avvio del core")
            return False
        if not (0 <= index < len(self._attachment_texts)):
            return False
        name = self._attachment_texts[index]["name"]
        pending = [a for i, a in enumerate(self._attachment_texts) if i != index]
        return self._send_attachments(pending, label=f"Tu: tolgo l'allegato {name}")

    def _send_attachments(self, pending: list[dict], label: str) -> bool:
        documenti = [{"name": a["name"], "text": a["text"], "kind": a["kind"]} for a in pending]
        if not self.run_command("set_attachments", {"documenti": documenti}, label):
            return False
        self._attachments_pending = pending
        self._attachments_request_id = self.request_id
        self._attachments_id_pending = self.request_id is None
        return True

    # --- drafting workbench: letterhead (design §5.2, §5.3) --------------------
    def set_letterheads(self, entries: list[dict]) -> None:
        self.draft_view["letterheads"] = entries
        current = self.draft_view.get("letterhead")
        if current is None or not any(e["name"] == current for e in entries):
            self.draft_view["letterhead"] = letterheads.initial_choice(
                entries, letterheads.load_index())
        labels, selected = self._letterhead_selection()
        self.view.set_letterheads(labels, selected)

    def choose_letterhead(self, index: int) -> None:
        entries = self.draft_view["letterheads"]
        if not (0 <= index <= len(entries)):
            return       # a ListBox reports -1 with no selection: not a valid row
        name = None if index == 0 else entries[index - 1]["name"]
        self.draft_view["letterhead"] = name
        with suppress(OSError):
            letterheads.remember_choice(name)

    def letterhead_path(self) -> str | None:
        name = self.draft_view.get("letterhead")
        if name is None:
            return None
        entry = next((e for e in self.draft_view["letterheads"] if e["name"] == name), None)
        return entry["path"] if entry else None

    def _letterhead_selection(self) -> tuple[list[str], int]:
        entries = self.draft_view["letterheads"]
        selected = 0
        name = self.draft_view.get("letterhead")
        if name is not None:
            for i, e in enumerate(entries):
                if e["name"] == name:
                    selected = i + 1
                    break
        return render_letterhead_labels(entries), selected

    def _apply_letterhead(self) -> None:
        path = self.letterhead_path()
        url = "file://" + urllib.parse.quote(path) if path else None
        try:
            self.adapter.apply_letterhead(url)
        except Exception as e:
            line = f"Carta intestata non applicata: {e}"
            self._log(line)
            self._append(line)

    def goto_partition(self, index: int) -> None:
        partitions = self.draft_view["partitions"]
        if not (0 <= index < len(partitions)):
            return
        try:
            self.adapter.goto(partitions[index]["from_id"])
        except Exception as e:  # navigation is best effort, as in select_citation
            self.view.set_status(f"Posizione non raggiungibile: {e}")

    def goto_expected(self, index: int) -> None:
        """A row of the Expected checklist names an expected section, not a position: resolve
        it to the first inserted partition whose title matches, the same rule
        ``render_expected_partitions`` uses to mark the row found, then jump there as
        ``goto_partition`` would. No match (the section is not inserted yet, or the index is
        out of range) is a no-op.
        """
        expected = self.draft_view["expected_partitions"]
        if not (0 <= index < len(expected)):
            return
        key = expected[index].lower()[:5]
        for i, p in enumerate(self.draft_view["partitions"]):
            if key in (p.get("titolo") or "").lower():
                self.goto_partition(i)
                return

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
        return self._send_payload(payload_factory, label)

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
        self._forget_draft_start()
        self._attachments_pending = None
        self._forget_attachments_request()

    # --- events from the core (UI thread) -----------------------------------
    def handle_event(self, ev: dict) -> None:
        kind = ev.get("kind")
        if kind == "exit":
            was_active = self.state in ("starting", "busy")
            self.bridge = None
            self.state, self.pending, self.pending_label, self.request_id = (
                "stopped", None, None, None)
            was_draft, self._draft_request = self._draft_request, False
            self._forget_draft_start()
            self._attachments_pending = None
            self._forget_attachments_request()
            if was_draft:      # same as _on_error: no drafting is running any more
                self._log("Il core si è chiuso")
                self._refresh_draft_status()
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
            queued_draft = self._draft_request
            if not self._send_payload(payload_factory, label) and queued_draft:
                # The draft request was taken while the core was still starting, so the
                # Redazione panel already shows it as under way; this first write after the
                # hello found a dead pipe, and no final, error or exit will ever follow to
                # clear it (M4).
                self._abandon_draft_request()
        else:
            self._set_busy(False)

    def _on_status(self, msg: dict) -> None:
        self.view.set_status(msg.get("text", ""))
        if self._draft_request:
            self._log(msg.get("text", ""))

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
        action, args = msg["action"], msg.get("args") or {}
        try:
            reply.update(ok=True, result=dispatch_doc_call(self.adapter, action, args,
                                                           act_styles=self._draft_request))
        except Exception as e:
            reply.update(ok=False, error=f"{type(e).__name__}: {e}"
                         if not isinstance(e, DocumentActionError) else str(e))
        succeeded = reply["ok"]
        # The reply goes out before the drafting log line (F5): a dead panel control (a
        # closed/rebuilding Redazione deck) must never keep the core waiting on this reply.
        self.bridge.send(reply)
        if succeeded and self._draft_request:
            with suppress(Exception):
                if action == "insert_markdown":
                    self._log(render_log_insert(args["markdown"]))
                elif action == "replace_text":
                    self._log(f"Sostituito: «{args['query']}»")

    def _on_final(self, msg: dict) -> None:
        self.state, self.request_id = "ready", None
        self._draft_request = False
        self._forget_draft_start()          # the start was answered: nothing left to undo
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
            # Another act, other fields: the panel's ``set_template`` clears the field rows,
            # and the stored copy goes with them, so a rebuild after this never puts the
            # previous template's values into the new template's rows (I5). The notes box is
            # free text about the case, not about the act: the panel keeps it (browsing the
            # catalogue fires a template_info on every selection), and so does the session.
            self.draft_view["fields"] = {}
            self.view.set_template(summary)
            # The status keeps the drafting's own "started": looking at another template
            # mid-drafting must not hide "Continua la redazione" (I4).
            self._refresh_draft_status()
            self._append(render_template_notes(summary))
        elif "riferimento" in summary and not isinstance(summary.get("riferimento"), str):
            # A dict-or-None value is the new set_reference final; a plain string is the
            # older insert_norm final, which also happens to use the "riferimento" key and
            # is handled further down, unchanged.
            ref = summary["riferimento"]
            if ref:
                # the core reports only its own truncation; ours happened before the send
                ref = {**ref, "troncato": bool(ref.get("troncato") or self._reference_truncated)}
            self.draft_view["reference"] = ref
            self.view.set_reference(render_reference(ref), bool(ref))
            self._append(msg["text"])
        elif ("allegati" in summary and msg.get("request_id") == self._attachments_request_id
              and "partizioni" not in summary and "usage_totals" not in summary):
            # set_attachments' Final (design §4.3): the pending set the panel sent is what
            # was actually stored; an empty ``allegati`` (the last one removed) clears both.
            # The core puts "allegati" in EVERY draft-turn Final too, so the request_id (and,
            # as a belt, the absence of "partizioni"/"usage_totals") is what tells the two
            # finals apart: a draft turn must still reach _merge_draft_turn below (F1).
            allegati = summary["allegati"] or []
            pending = self._attachments_pending or []
            self._attachment_texts = pending
            merged = []
            for i, a in enumerate(allegati):
                local_troncato = pending[i]["troncato"] if i < len(pending) else False
                merged.append({**a, "troncato": bool(a.get("troncato") or local_troncato)})
            self.draft_view["attachments"] = merged
            self.view.set_attachments(render_attachments(merged))
            self._append(msg["text"])
            self._attachments_pending = None
            self._forget_attachments_request()
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

        and the Redazione/Domande panels. ``base_errore`` (wire contract addition) is stored
        like the rest of the state, so the status line it produces survives a panel rebuild
        (``render_draft_status`` reads it from the view).
        """
        self.draft_view["questions"] = summary.get("domande") or []
        self.draft_view["partitions"] = summary.get("partizioni") or []
        self.draft_view["open_placeholders"] = summary.get("segnaposto_aperti") or []
        self.draft_view["done"] = summary.get("completata", False)
        self.draft_view["started"] = True
        self.draft_view["stopped"] = summary.get("stopped")
        self.draft_view["base_errore"] = summary.get("base_errore")
        # the panel's set_questions empties the answer rows of the previous round: the
        # stored copy a rebuild would replay goes with them (I5)
        self.draft_view["answers_draft"] = {}
        self.view.set_questions(self.draft_view["questions"])
        self.view.set_answer_values({})
        self.view.set_partitions(render_partitions(self.draft_view["partitions"],
                                                    self.draft_view["open_placeholders"]))
        self.view.set_expected_partitions(render_expected_partitions(
            self.draft_view["expected_partitions"], self.draft_view["partitions"]))
        questions = self.draft_view["questions"]
        self._set_step(2 if questions else 4)
        if not questions:
            summary_with_attachments = summary if "allegati" in summary else {
                **summary, "allegati": self.draft_view["attachments"]}
            self._summary_text = render_summary(summary_with_attachments)
            self.view.set_summary(self._summary_text)
        if self.draft_view["base_errore"]:
            self._append(render_base_error(self.draft_view["base_errore"]))
        if self.draft_view["done"] and summary.get("riepilogo"):
            self._append(render_riepilogo(summary["riepilogo"]))

    def _on_error(self, msg: dict) -> None:
        # A start that fails is a drafting that never began: nothing was inserted, no turn
        # can be continued, so the "started" the panel committed to has to go (M5).
        failed_start = (self._draft_start_request_id is not None
                        and msg.get("request_id") in (self._draft_start_request_id, None))
        failed_attachments = (self._attachments_request_id is not None
                              and msg.get("request_id") in (self._attachments_request_id, None))
        was_draft = False
        if self.state == "busy" and msg.get("request_id") in (self.request_id, None):
            self.state, self.request_id = "ready", None
            was_draft, self._draft_request = self._draft_request, False
            self._set_busy(False)
            self.view.set_status("Pronto")
        self.view.set_progress(0, None)
        self._flush_stream()
        self._clear_pending_consent()
        self._append(render_error(msg.get("code", "?"), msg.get("message", ""), self.config_path))
        if failed_attachments:
            self._attachments_pending = None
            self._forget_attachments_request()
        if was_draft:
            self._log(f"Errore: {msg.get('message', '')}")
        if failed_start:
            self._forget_draft_start()
            self._abandon_draft_request()
        elif was_draft:
            # the turn is over, however badly: the Redazione line must stop claiming that a
            # drafting is running (only _set_busy(True) refreshes it, and this is the way out)
            self._refresh_draft_status()

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
                      label: str | None = None) -> bool:
        """Send the payload to an already-connected core; return whether it was accepted.

        Everything here (``request_id``, the busy state, the "Tu:" label) is committed only
        after ``_send`` actually succeeds: a dead pipe on a core that was ready a moment ago
        (``_send``'s failure path already calls ``shutdown()``) must leave nothing behind for
        a caller that mutates its own state on success — such as the three draft methods,
        via ``_submit``'s return value — to roll back.
        """
        self._n += 1
        request_id = f"r{self._n}"
        if not self._send(payload_factory(request_id)):
            return False
        self.request_id = request_id
        if self._draft_start_pending:       # a start queued behind the hello: this is its id
            self._draft_start_request_id, self._draft_start_pending = request_id, False
        if self._attachments_id_pending:    # same rule, for a set_attachments queued the same way
            self._attachments_request_id, self._attachments_id_pending = request_id, False
        self.state = "busy"
        self._set_busy(True)
        self.view.set_status("Invio della richiesta...")
        if label is not None:
            self._append(label)
        return True

    def _flush_stream(self) -> None:
        if self._streamed:
            self.transcript.append(self._stream_buffer)
        self._streamed = False
        self._stream_buffer = ""

    def _set_busy(self, busy: bool) -> None:
        self.view.set_busy(busy)
        if busy and self._draft_request:
            self._refresh_draft_status()

    def _refuse_draft(self, message: str) -> None:
        """Refuse a drafting action: the reason belongs next to the button that was pressed.

        The Azioni status line alone is not enough (M3): Redazione and Domande are panels of
        their own, and the lawyer who pressed "Avvia redazione" may not even have Azioni open.
        """
        self.view.set_status(message)
        self.view.set_draft_status(message, self.draft_view["started"])

    def _abandon_draft_request(self) -> None:
        """Undo a draft request the core will never answer (M4, M5).

        ``started`` is dropped only while the document holds no partition: once the core has
        inserted something, the drafting is real whatever happened to this one request, and
        "Continua la redazione" is the way back into it.
        """
        self._draft_request = False
        if not self.draft_view["partitions"]:
            self.draft_view["started"] = False
            self._set_step(1)
        else:
            self._refresh_draft_status()

    def _forget_draft_start(self) -> None:
        self._draft_start_request_id, self._draft_start_pending = None, False

    def _forget_attachments_request(self) -> None:
        self._attachments_request_id, self._attachments_id_pending = None, False

    def _set_step(self, step: int) -> None:
        self.draft_view["step"] = step
        self.view.set_step(step)
        self._refresh_draft_status()

    def _log(self, line: str) -> None:
        log = self.draft_view["log"]
        log.append(line)
        if len(log) > MAX_LOG_LINES:
            del log[: len(log) - MAX_LOG_LINES]
        self.view.append_log(line)

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
