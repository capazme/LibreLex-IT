# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Routing between one Session and the sidebar panels of its document (no UNO)."""
from __future__ import annotations

from librelex_ext.layout import KINDS

ROUTES = {"append": "Answers", "set_transcript": "Answers", "set_status": "Actions",
          "set_busy": "Actions", "set_progress": "Actions", "set_citations": "Citations"}


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
        self._call("set_busy", busy)

    def set_progress(self, done: int, total) -> None:
        self._call("set_progress", done, total)

    def set_citations(self, labels: list[str]) -> None:
        self._call("set_citations", labels)
