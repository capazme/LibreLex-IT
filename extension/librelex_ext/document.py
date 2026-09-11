# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Document adapter: the nine document actions of spec §5.3 on one Writer model, over UNO.

Runs on the UI thread. Imports nothing from the package so the headless test macros can
import it alone. Ids (spec §5.3): p:<i> body paragraphs (tables not counted),
fn:<n>/p:<i> footnote paragraphs (n = 1-based footnote number in document order),
t:<t>/c:<cell>/p:<i> table-cell paragraphs.
"""
from __future__ import annotations

import os  # noqa: F401  (used by the writing half, Tasks 7-8)
import re  # noqa: F401  (used by the writing half, Tasks 7-8)
import tempfile  # noqa: F401  (used by the writing half, Tasks 7-8)
from contextlib import contextmanager  # noqa: F401  (used by the writing half, Tasks 7-8)
from datetime import datetime  # noqa: F401  (used by the writing half, Tasks 7-8)

import uno  # noqa: F401  (used by the writing half, Tasks 7-8)
from com.sun.star.beans import PropertyValue
from com.sun.star.text.ControlCharacter import (  # noqa: F401  (writing half, Tasks 7-8)
    PARAGRAPH_BREAK,
)

PARAGRAPH = "com.sun.star.text.Paragraph"
TABLE = "com.sun.star.text.TextTable"
ANNOTATION = "com.sun.star.text.TextField.Annotation"
PROFILE_NODE = "/org.openoffice.UserProfile/Data"


class DocumentActionError(Exception):
    """Reported to the core as doc_result ok=false."""


def prop(name, value):
    p = PropertyValue()
    p.Name, p.Value = name, value
    return p


def _config_access(ctx, nodepath, update=False):
    provider = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.configuration.ConfigurationProvider", ctx)
    service = ("com.sun.star.configuration.ConfigurationUpdateAccess" if update
               else "com.sun.star.configuration.ConfigurationAccess")
    return provider.createInstanceWithArguments(service, (prop("nodepath", nodepath),))


def lo_version(ctx) -> str:
    try:
        return str(_config_access(ctx, "/org.openoffice.Setup/Product").getByName(
            "ooSetupVersionAboutBox"))
    except Exception:
        return ""


def has_markdown_filter(ctx) -> bool:
    try:
        ff = ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.document.FilterFactory", ctx)
        return bool(ff.hasByName("Markdown") or ff.hasByName("Markdown (Writer)"))
    except Exception:
        return False


class Entry:
    __slots__ = ("id", "para", "container", "kind", "style", "body_index")

    def __init__(self, id, para, container, kind, body_index):
        self.id, self.para, self.container = id, para, container
        self.kind, self.body_index = kind, body_index
        self.style = para.ParaStyleName

    def as_dict(self) -> dict:
        return {"id": self.id, "text": self.para.getString(), "style": self.style,
                "kind": self.kind}


def _paragraphs_of(container) -> list:
    """Paragraph elements of an XText, tables skipped."""
    out = []
    enum = container.createEnumeration()
    while enum.hasMoreElements():
        el = enum.nextElement()
        if el.supportsService(PARAGRAPH):
            out.append(el)
    return out


class DocumentAdapter:
    def __init__(self, ctx, model):
        self.ctx = ctx
        self.doc = model

    # --- indexing ------------------------------------------------------------
    def _index(self) -> list[Entry]:
        entries: list[Entry] = []
        body = self.doc.getText()
        p_i = fn_n = t_i = 0
        enum = body.createEnumeration()
        while enum.hasMoreElements():
            el = enum.nextElement()
            if el.supportsService(PARAGRAPH):
                entries.append(Entry(f"p:{p_i}", el, body, "body", p_i))
                portions = el.createEnumeration()
                while portions.hasMoreElements():
                    por = portions.nextElement()
                    if por.TextPortionType == "Footnote":
                        fn_n += 1
                        fn = por.Footnote
                        for j, fp in enumerate(_paragraphs_of(fn)):
                            entries.append(Entry(f"fn:{fn_n}/p:{j}", fp, fn, "footnote", p_i))
                p_i += 1
            elif el.supportsService(TABLE):
                for name in el.getCellNames():
                    cell = el.getCellByName(name)
                    for j, cp in enumerate(_paragraphs_of(cell)):
                        entries.append(
                            Entry(f"t:{t_i}/c:{name}/p:{j}", cp, cell, "table_cell", p_i))
                t_i += 1
        return entries

    def _entry(self, paragraph_id: str) -> Entry:
        for e in self._index():
            if e.id == paragraph_id:
                return e
        raise DocumentActionError(f"paragrafo non trovato: {paragraph_id}")

    def _entry_at(self, rng) -> Entry | None:
        """The paragraph containing the start of `rng`, or None if it is outside the index.

        Observed on 26.8: `compareRegionStarts` does *not* raise when the two ranges live in
        different XTexts (a footnote paragraph compares as "before" any body range), while
        `compareRegionEnds` does raise. So containers are matched first by identity, which
        pyuno resolves correctly on XText proxies, and only then compared.
        """
        try:
            text = rng.getText()
        except Exception:
            text = None
        for e in self._index():
            if text is not None and not (e.container == text):
                continue
            try:
                starts = e.container.compareRegionStarts(e.para.getStart(), rng.getStart())
                ends = e.container.compareRegionEnds(e.para.getEnd(), rng.getStart())
            except Exception:
                continue           # rng lives in another XText (footnote, cell, body)
            if starts >= 0 and ends <= 0:   # paragraph starts at or before rng and ends after
                return e
        return None

    @staticmethod
    def _offset_in_paragraph(entry: Entry, rng) -> int:
        cur = entry.container.createTextCursorByRange(rng.getStart())
        cur.gotoStartOfParagraph(True)
        return len(cur.getString())

    def _prefix_for(self, container, sample_range) -> str:
        """Id prefix ("p:", "fn:1/p:", "t:0/c:A1/p:") of the XText holding sample_range.

        `container` is the XText the caller already has at hand; the prefix is derived from
        `sample_range`, which carries the same XText and, unlike it, a position inside it.
        """
        e = self._entry_at(sample_range)
        if e is None:
            raise DocumentActionError("posizione fuori dal testo del documento")
        return e.id.rsplit(":", 1)[0] + ":"

    def _view_cursor(self):
        controller = self.doc.getCurrentController()
        if controller is None:
            raise DocumentActionError("documento senza vista")
        return controller.getViewCursor()

    def _first_selection_range(self):
        """The selected text range, or None.

        Observed on 26.8: `getCurrentSelection()` returns None on a hidden document (the
        headless probes), where the view cursor alone carries the selection; fall back to it.
        A non-text selection (image, shape) counts as no selection.
        """
        try:
            sel = self.doc.getCurrentSelection()
        except Exception:
            sel = None
        if sel is None:
            try:
                return self._view_cursor()
            except DocumentActionError:
                return None
        try:
            if not sel.supportsService("com.sun.star.text.TextRanges") or sel.getCount() == 0:
                return None
        except Exception:
            return None
        return sel.getByIndex(0)

    # --- reading actions -----------------------------------------------------
    def get_document_info(self) -> dict:
        entries = self._index()
        sel = self.read_selection()
        cursor = None
        try:
            e = self._entry_at(self._view_cursor().getStart())
            cursor = e.id if e else None
        except DocumentActionError:
            pass
        return {"title": self.doc.getTitle() or "", "url": self.doc.getURL() or "",
                "paragraph_count": sum(1 for e in entries if e.kind == "body"),
                "has_selection": bool(sel["text"]), "cursor_paragraph": cursor,
                "lo_version": lo_version(self.ctx),
                "has_markdown_filter": has_markdown_filter(self.ctx)}

    def read_selection(self) -> dict:
        rng = self._first_selection_range()
        if rng is None:
            return {"text": "", "anchor": None}
        text = rng.getString()
        if not text:
            return {"text": "", "anchor": None}
        entry = self._entry_at(rng)
        if entry is None:
            return {"text": text, "anchor": None}
        start = self._offset_in_paragraph(entry, rng)
        return {"text": text, "anchor": {"paragraph_id": entry.id, "start": start,
                                         "end": start + len(text)}}

    def read_paragraphs(self, from_=None, to=None) -> list[dict]:
        lo = int(from_) if from_ is not None else 0
        hi = int(to) if to is not None else None
        out = []
        for e in self._index():
            if e.body_index < lo or (hi is not None and e.body_index >= hi):
                continue
            out.append(e.as_dict())
        return out

    def find_text(self, query: str, paragraph_id=None) -> list[dict]:
        if not query:
            return []
        entries = [self._entry(paragraph_id)] if paragraph_id else self._index()
        out = []
        for e in entries:
            text, pos = e.para.getString(), 0
            while (pos := text.find(query, pos)) != -1:
                out.append({"anchor": {"paragraph_id": e.id, "start": pos,
                                       "end": pos + len(query)}, "text": query})
                pos += len(query)
        return out

    def goto(self, paragraph_id: str) -> None:
        entry = self._entry(paragraph_id)
        self._view_cursor().gotoRange(entry.para.getStart(), False)
