# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Routing between one Session and the sidebar panels of its document (no UNO)."""
from __future__ import annotations

from librelex_ext.layout import KINDS

# Every view method but the ones in BROADCAST, which every attached panel hears instead of
# just the one it routes to: the controls ``layout.BUSY_DISABLED`` names are spread over
# Azioni and Redazione, and a consent request can land while either panel is the one showing.
ROUTES = {"append": "Answers", "set_transcript": "Answers", "append_stream": "Answers",
          "set_status": "Actions", "set_progress": "Actions",
          "set_usage": "Actions", "set_citations": "Citations",
          "set_templates": "Drafting", "set_template": "Drafting", "set_reference": "Drafting",
          "set_partitions": "Drafting", "set_draft_status": "Drafting",
          "set_field_values": "Drafting", "set_questions": "Drafting",
          "set_answer_values": "Drafting", "set_step": "Drafting", "set_log": "Drafting",
          "append_log": "Drafting", "set_expected_partitions": "Drafting",
          "set_attachments": "Drafting", "set_letterheads": "Drafting",
          "set_summary": "Drafting"}

# methods broadcast to every attached panel instead of routed to one kind
BROADCAST = ("set_busy", "set_consent")


def panel_kind(url: str) -> str:
    """The panel kind at the end of a sidebar resource URL, e.g. ``.../Answers``."""
    kind = url.rsplit("/", 1)[-1]
    if kind not in KINDS:
        raise ValueError(f"unknown panel resource: {url}")
    return kind


class CompositeView:
    """The Session's single View; each call reaches the panel of that kind, if alive."""

    def __init__(self) -> None:
        self.panels: dict[str, object] = {}

    def attach(self, kind: str, panel: object) -> None:
        self.panels[kind] = panel

    def detach(self, kind: str) -> None:
        self.panels.pop(kind, None)

    def _call(self, method: str, *args) -> None:
        if method in BROADCAST:
            for panel in list(self.panels.values()):
                getattr(panel, method)(*args)
            return
        panel = self.panels.get(ROUTES[method])
        if panel is not None:
            getattr(panel, method)(*args)

    def append(self, text: str) -> None:
        self._call("append", text)

    def set_transcript(self, text: str) -> None:
        self._call("set_transcript", text)

    def set_status(self, text: str) -> None:
        self._call("set_status", text)

    def set_busy(self, busy: bool) -> None:
        """Broadcast (see BROADCAST): every attached panel disables its own busy controls."""
        self._call("set_busy", busy)

    def set_progress(self, done: int, total) -> None:
        self._call("set_progress", done, total)

    def set_citations(self, labels: list[str]) -> None:
        self._call("set_citations", labels)

    def append_stream(self, text: str) -> None:
        self._call("append_stream", text)

    def set_usage(self, text: str) -> None:
        self._call("set_usage", text)

    def set_consent(self, summary: dict | None) -> None:
        """Broadcast (see BROADCAST): a consent request can land on either panel."""
        self._call("set_consent", summary)

    def set_templates(self, labels: list[str], selected: int | None) -> None:
        self._call("set_templates", labels, selected)

    def set_template(self, info: dict | None) -> None:
        self._call("set_template", info)

    def set_reference(self, text: str, present: bool) -> None:
        self._call("set_reference", text, present)

    def set_partitions(self, labels: list[str]) -> None:
        self._call("set_partitions", labels)

    def set_draft_status(self, text: str, started: bool) -> None:
        self._call("set_draft_status", text, started)

    def set_questions(self, questions: list[dict]) -> None:
        self._call("set_questions", questions)

    def set_field_values(self, fields: dict, notes: str) -> None:
        self._call("set_field_values", fields, notes)

    def set_answer_values(self, answers: dict) -> None:
        self._call("set_answer_values", answers)

    def set_step(self, step: int) -> None:
        self._call("set_step", step)

    def set_log(self, lines: list[str]) -> None:
        self._call("set_log", lines)

    def append_log(self, line: str) -> None:
        self._call("append_log", line)

    def set_expected_partitions(self, labels: list[str]) -> None:
        self._call("set_expected_partitions", labels)

    def set_attachments(self, labels: list[str]) -> None:
        self._call("set_attachments", labels)

    def set_letterheads(self, labels: list[str], selected: int | None) -> None:
        self._call("set_letterheads", labels, selected)

    def set_summary(self, text: str) -> None:
        self._call("set_summary", text)
