# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Document adapter: the nine document actions of spec §5.3 on one Writer model, over UNO.

Runs on the UI thread. The only thing it imports from the package is the shared
``DocumentActionError`` of ``librelex_ext/__init__.py`` (stdlib only, and already executed
whenever this module is imported), so the headless test macros still import it alone.
Ids (spec §5.3): p:<i> body paragraphs (tables not counted),
fn:<n>/p:<i> footnote paragraphs (n = 1-based footnote number in document order),
t:<t>/c:<cell>/p:<i> table-cell paragraphs.
"""
from __future__ import annotations

import os
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime  # noqa: F401  (used by the comment actions, Task 8)

import uno
from com.sun.star.beans import PropertyValue
from com.sun.star.text.ControlCharacter import PARAGRAPH_BREAK

from librelex_ext import DocumentActionError

PARAGRAPH = "com.sun.star.text.Paragraph"
TABLE = "com.sun.star.text.TextTable"
ANNOTATION = "com.sun.star.text.TextField.Annotation"
PROFILE_NODE = "/org.openoffice.UserProfile/Data"

__all__ = ["DocumentActionError", "DocumentAdapter", "has_markdown_filter", "lo_version"]


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

    # --- context managers ----------------------------------------------------
    def _profile_access(self, update: bool):
        return _config_access(self.ctx, PROFILE_NODE, update=update)

    @contextmanager
    def _identity(self, author):
        """Temporarily sign tracked changes as `author` (spec §5.4 item 3); None = user identity."""
        if not author:
            yield
            return
        acc = self._profile_access(update=True)
        original = (acc.getPropertyValue("givenname"), acc.getPropertyValue("sn"))
        acc.setPropertyValue("givenname", author)
        acc.setPropertyValue("sn", "")
        acc.commitChanges()
        try:
            yield
        finally:
            acc.setPropertyValue("givenname", original[0])
            acc.setPropertyValue("sn", original[1])
            acc.commitChanges()

    @contextmanager
    def _undo(self, label: str):
        um = self.doc.getUndoManager()
        um.enterUndoContext(label)
        try:
            yield
        finally:
            um.leaveUndoContext()

    @contextmanager
    def _recording(self, on: bool):
        before = self.doc.RecordChanges
        self.doc.RecordChanges = on
        try:
            yield
        finally:
            self.doc.RecordChanges = before

    # --- writing actions -----------------------------------------------------
    def _target(self, where: str):
        """(collapsed cursor, container XText) for `cursor` | `end` | `after:<id>`."""
        if where == "cursor":
            vc = self._view_cursor()
            container = vc.getText()
            return container.createTextCursorByRange(vc.getStart()), container
        if where == "end":
            container = self.doc.getText()
            cur = container.createTextCursor()
            cur.gotoEnd(False)
            return cur, container
        if where.startswith("after:"):
            e = self._entry(where[len("after:"):])
            return e.container.createTextCursorByRange(e.para.getEnd()), e.container
        raise DocumentActionError(f"destinazione sconosciuta: {where}")

    @staticmethod
    def _prepare_empty_paragraph(cur, container) -> None:
        """Leave `cur` at the start of an empty paragraph (spec §5.4 item 1).

        Observed on 26.8: inserted into an empty paragraph the Markdown filter *keeps* the
        style of its own first paragraph (`Heading 1`, `Quotations`) and overwrites the empty
        one, so no style is lost; mid-paragraph the first Markdown paragraph would instead
        merge into the cursor paragraph and inherit its style. This settles the open point of
        spec §5.4 item 6. The filter also always leaves one trailing empty paragraph, which
        `_insert_block` removes with recording off.
        """
        if not cur.isStartOfParagraph():
            container.insertControlCharacter(cur, PARAGRAPH_BREAK, False)
        if not cur.isEndOfParagraph():           # remainder text: push it to the next paragraph
            container.insertControlCharacter(cur, PARAGRAPH_BREAK, False)
            cur.goLeft(1, False)

    @staticmethod
    def _para_index(container, cur) -> int:
        paras = _paragraphs_of(container)
        best = 0
        for i, p in enumerate(paras):
            if container.compareRegionStarts(p.getStart(), cur.getStart()) >= 0:
                best = i
        return best

    @staticmethod
    def _insert_markdown_file(cur, markdown: str) -> None:
        if not markdown.endswith("\n"):
            markdown += "\n"        # the filter then always adds one trailing empty paragraph
        tmpdir = tempfile.mkdtemp(prefix="librelex-")          # 0700 (spec §8.4)
        path = os.path.join(tmpdir, "insert.md")
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(markdown)
            cur.insertDocumentFromURL(uno.systemPathToFileUrl(path),
                                      (prop("FilterName", "Markdown"),))
        finally:
            try:
                os.unlink(path)
            finally:
                os.rmdir(tmpdir)

    @staticmethod
    def _remove_empty_paragraph(container, para) -> None:
        """Delete `para` (empty) by removing the paragraph break that precedes it."""
        c = container.createTextCursorByRange(para.getStart())
        c.goLeft(1, True)
        c.setString("")

    @staticmethod
    def _fix_first_style(para, markdown: str) -> None:
        """Re-apply the heading/quote style of the first Markdown paragraph.

        A no-op on 26.8 (see `_prepare_empty_paragraph`): kept as the guard for the merge
        case, where the style of the first inserted paragraph is the one thing that is lost.
        """
        first = next((ln for ln in markdown.splitlines() if ln.strip()), "")
        m = re.match(r"^(#{1,6})\s+", first)
        if m:
            want = f"Heading {len(m.group(1))}"
        elif first.startswith(">"):
            want = "Quotations"
        else:
            return
        if para.ParaStyleName != want:
            para.ParaStyleName = want

    def _unique_bookmark(self, name: str) -> str:
        marks = self.doc.getBookmarks()
        if not marks.hasByName(name):
            return name
        k = 2
        while marks.hasByName(f"{name}_{k}"):
            k += 1
        return f"{name}_{k}"

    def _add_bookmark(self, container, first, last, name: str) -> None:
        bm = self.doc.createInstance("com.sun.star.text.Bookmark")
        bm.setName(self._unique_bookmark(name))
        c = container.createTextCursorByRange(first.getStart())
        c.gotoRange(last.getEnd(), True)
        container.insertTextContent(c, bm, True)

    def _insert_block(self, cur, container, markdown, bookmark, author) -> tuple[int, int]:
        """Shared by insert_markdown and replace_selection; caller holds the undo context."""
        with self._identity(author):
            with self._recording(True):
                self._prepare_empty_paragraph(cur, container)
                i0 = self._para_index(container, cur)
                n0 = len(_paragraphs_of(container))
                self._insert_markdown_file(cur, markdown)
            with self._recording(False):          # cleanup must not become Delete/Format redlines
                paras = _paragraphs_of(container)
                last = i0 + (len(paras) - n0)
                if last > i0 and paras[last].getString() == "":
                    self._remove_empty_paragraph(container, paras[last])
                    last -= 1
                    paras = _paragraphs_of(container)
                self._fix_first_style(paras[i0], markdown)
                if bookmark:
                    self._add_bookmark(container, paras[i0], paras[last], bookmark)
        return i0, last

    def insert_markdown(self, where: str, markdown: str, undo_label: str,
                        bookmark=None, author=None) -> dict:
        cur, container = self._target(where)
        prefix = self._prefix_for(container, cur)
        with self._undo(undo_label):
            i0, last = self._insert_block(cur, container, markdown, bookmark, author)
        return {"from_id": f"{prefix}{i0}", "to_id": f"{prefix}{last}"}

    def replace_selection(self, markdown: str, undo_label: str) -> dict:
        rng = self._first_selection_range()
        if rng is None or not rng.getString():
            raise DocumentActionError("nessuna selezione da sostituire")
        container = rng.getText()
        prefix = self._prefix_for(container, rng)
        with self._undo(undo_label):
            with self._identity("LibreLex"), self._recording(True):
                cur = container.createTextCursorByRange(rng)
                cur.setString("")     # tracked deletion (spec §5.3: deletion + insertion)
                cur.collapseToEnd()
            i0, last = self._insert_block(cur, container, markdown, None, "LibreLex")
        return {"from_id": f"{prefix}{i0}", "to_id": f"{prefix}{last}"}
