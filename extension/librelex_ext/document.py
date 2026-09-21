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
import shutil
import tempfile
from contextlib import contextmanager, suppress
from datetime import datetime
from urllib.parse import unquote

import uno
from com.sun.star.beans import PropertyValue
from com.sun.star.text.ControlCharacter import PARAGRAPH_BREAK

from librelex_ext import DocumentActionError
from librelex_ext import styles as act_styles_module
from librelex_ext.pdftext import rebuild_lines

PARAGRAPH = "com.sun.star.text.Paragraph"
TABLE = "com.sun.star.text.TextTable"
ANNOTATION = "com.sun.star.text.TextField.Annotation"
PROFILE_NODE = "/org.openoffice.UserProfile/Data"

__all__ = ["DocumentActionError", "DocumentAdapter", "has_markdown_filter", "lo_version",
           "make_letterhead", "read_document", "read_reference"]


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

    def _live_hits(self, query: str, paragraph_id: str | None,
                   first_paragraph_only: bool = False) -> list[tuple[Entry, list[int]]]:
        """Offsets of every *live* `query` occurrence, grouped by paragraph, in document order.

        Shared by `find_text` and `replace_text`: text covered by a pending `Delete` redline
        is not live text for any caller (the core's open-placeholder rescan and the verify
        pipeline's comment anchoring included), because `para.getString()` still returns it
        until the change is accepted (see `_deleted_spans`). A hit overlapping one of its
        paragraph's deleted spans is therefore skipped. The spans are computed once per call.
        `first_paragraph_only` stops at the first paragraph with a hit (replace_text's
        `all=False`); an unknown `paragraph_id` raises as `_entry` does.
        """
        entries = [self._entry(paragraph_id)] if paragraph_id else self._index()
        deleted = self._deleted_spans()
        groups: list[tuple[Entry, list[int]]] = []
        for e in entries:
            text, pos, hits = e.para.getString(), 0, []
            spans = deleted.get(e.id, [])
            while (pos := text.find(query, pos)) != -1:
                end = pos + len(query)
                if not any(pos < d_end and end > d_start for d_start, d_end in spans):
                    hits.append(pos)
                pos = end
            if hits:
                groups.append((e, hits))
                if first_paragraph_only:
                    break
        return groups

    def find_text(self, query: str, paragraph_id=None) -> list[dict]:
        if not query:
            return []
        return [{"anchor": {"paragraph_id": e.id, "start": pos, "end": pos + len(query)},
                 "text": query}
                for e, hits in self._live_hits(query, paragraph_id) for pos in hits]

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

    # --- act styles (design §5.1, §5.3) ---------------------------------------
    @staticmethod
    def _convert_style_property(name: str, value):
        """A `styles.style_properties` value converted to what UNO expects for `name`."""
        if name == "ParaAdjust":
            return uno.Enum("com.sun.star.style.ParagraphAdjust", value)
        if name == "ParaLineSpacing":
            mode, height = value
            ls = uno.createUnoStruct("com.sun.star.style.LineSpacing")
            ls.Mode, ls.Height = 0, height     # 0 = PROP, whatever `mode` spells
            return ls
        return value

    def ensure_act_styles(self) -> list[str]:
        """Create every `styles.ACT_STYLES` name missing from the document (design §5.1, §6).

        A style already present (created by an earlier call, or adjusted by the lawyer in a
        letterhead template) is left untouched. Returns the names actually created.
        """
        family = self.doc.getStyleFamilies().getByName("ParagraphStyles")
        created = []
        for name in act_styles_module.ACT_STYLES:
            if family.hasByName(name):
                continue
            style = self.doc.createInstance("com.sun.star.style.ParagraphStyle")
            family.insertByName(name, style)
            style.ParentStyle = "Standard"
            for prop_name, value in act_styles_module.style_properties(name).items():
                setattr(style, prop_name, self._convert_style_property(prop_name, value))
            created.append(name)
        return created

    @staticmethod
    def _origin_of(para) -> str:
        """One of `styles.ORIGINS`, from the paragraph style and list state (design §5.3)."""
        style_name = para.ParaStyleName
        if style_name.startswith("Heading "):
            try:
                level = int(style_name[len("Heading "):])
            except ValueError:
                level = 1
            return f"heading{min(level, 3)}"
        if para.NumberingIsNumber or para.ListLabelString:
            return "list"
        if style_name == "Quotations":
            return "quote"
        return "body"

    def _apply_act_styles(self, container, paras: list, author) -> None:
        """Restyle every paragraph of `paras` (freshly inserted) to its LibreLex act style.

        Must run inside the caller's `_identity(author)` context (`_insert_block` holds it for
        the whole call): the literal text inserted below (a list prefix, a restored `* * * *
        *` separator) is then signed as that same tracked insertion, not the user's own.

        Every list item's prefix is read from `ListLabelString` in one pass over all of
        `paras` before any paragraph's numbering is touched: on 26.8 clearing one paragraph's
        `NumberingRules` reflows the whole list, so a later paragraph's own `ListLabelString`
        would otherwise already have shifted (item 2 reading "1." once item 1 lost its number)
        by the time it is its own turn.

        Deviation from the design: the Markdown filter renders a `* * * * *` line as an empty
        `Horizontal Line`-styled paragraph (a border, no text), not literal text, so it cannot
        reach `act_style_for` at all; the literal text is restored here before the pattern
        match, the same way a list item's numbering is turned back into literal text, and for
        the same reason (the act must survive copy and paste into other tools).
        """
        total = len(paras)
        origins = [self._origin_of(p) for p in paras]
        prefixes = {i: act_styles_module.list_prefix(p.ListLabelString)
                   for i, p in enumerate(paras) if origins[i] == "list"}
        for i, para in enumerate(paras):
            if para.ParaStyleName == "Horizontal Line" and not para.getString():
                with self._recording(True):
                    cur = container.createTextCursorByRange(para.getStart())
                    container.insertString(cur, "* * * * *", False)
                para.ParaStyleName = "LibreLex Separatore"
                continue
            origin = origins[i]
            if origin == "list":
                with self._recording(True):
                    cur = container.createTextCursorByRange(para.getStart())
                    container.insertString(cur, prefixes[i], False)
                with suppress(Exception):
                    para.setPropertyToDefault("NumberingRules")
                with suppress(Exception):
                    para.NumberingStyleName = ""
            style = act_styles_module.act_style_for(para.getString(), origin, total - 1 - i)
            para.ParaStyleName = style

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
            # Cleanup must never replace the real exception: if os.open/write failed the
            # file may not exist, and a FileNotFoundError here would mask the cause.
            with suppress(OSError):
                os.unlink(path)
            with suppress(OSError):
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

    def _insert_block(self, cur, container, markdown, bookmark, author,
                      act_styles=False) -> tuple[int, int]:
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
                if act_styles:
                    self.ensure_act_styles()
                    self._apply_act_styles(container, paras[i0:last + 1], author)
                if bookmark:
                    self._add_bookmark(container, paras[i0], paras[last], bookmark)
        return i0, last

    def insert_markdown(self, where: str, markdown: str, undo_label: str,
                        bookmark=None, author=None, act_styles=False) -> dict:
        cur, container = self._target(where)
        prefix = self._prefix_for(container, cur)
        with self._undo(undo_label):
            i0, last = self._insert_block(cur, container, markdown, bookmark, author, act_styles)
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

    def _deleted_spans(self) -> dict[str, list[tuple[int, int]]]:
        """Paragraph-local [start, end) offsets of every `Delete` redline, keyed by paragraph id.

        Observed on 26.8: `entry.para.getString()` still includes the text of a `Delete`
        redline (it is only struck through, not removed, until the change is accepted), so
        a later `replace_text` call scanning the same paragraph would re-match text an
        earlier call had already replaced. Matches that fall inside one of these spans are
        excluded from the scan of `_live_hits`, which both `find_text` and `replace_text` go
        through.

        A `Delete` redline can cross a paragraph boundary (e.g. `replace_selection` over a
        multi-paragraph selection, still deleted-but-visible the same way): `RedlineStart`
        and `RedlineEnd` then sit in two different paragraphs, so each end is resolved to
        its own paragraph separately (`_entry_at`, not the other end's `entry`, which
        `_offset_in_paragraph` would silently measure against the wrong paragraph and
        return a bogus offset for). The start paragraph is covered from its offset to its
        end, the end paragraph from its start to its offset, and every paragraph strictly
        between the two (by index order) is covered in full. Redlines that resolve (partly)
        outside the index are skipped.

        Cost: O(redlines x paragraphs), since resolving each redline's paragraph(s) walks
        the whole index again (`_entry_at`); fine for realistic documents.
        """
        spans: dict[str, list[tuple[int, int]]] = {}
        enum = self.doc.Redlines.createEnumeration()
        if not enum.hasMoreElements():
            return spans       # no tracked change at all: skip the index walk entirely
        entries = self._index()
        by_id = {en.id: i for i, en in enumerate(entries)}
        while enum.hasMoreElements():
            r = enum.nextElement()
            if r.RedlineType != "Delete":
                continue
            e_start = self._entry_at(r.RedlineStart)
            e_end = self._entry_at(r.RedlineEnd)
            if e_start is None or e_end is None:
                continue           # redline lives (partly) outside the indexed text
            i0, i1 = by_id.get(e_start.id), by_id.get(e_end.id)
            if i0 is None or i1 is None:
                continue
            if i0 == i1:
                start = self._offset_in_paragraph(e_start, r.RedlineStart)
                end = self._offset_in_paragraph(e_end, r.RedlineEnd)
                spans.setdefault(e_start.id, []).append((start, end))
                continue
            lo, hi = min(i0, i1), max(i0, i1)
            start = self._offset_in_paragraph(e_start, r.RedlineStart)
            spans.setdefault(e_start.id, []).append((start, len(e_start.para.getString())))
            end = self._offset_in_paragraph(e_end, r.RedlineEnd)
            spans.setdefault(e_end.id, []).append((0, end))
            for mid in entries[lo + 1:hi]:
                spans.setdefault(mid.id, []).append((0, len(mid.para.getString())))
        return spans

    def replace_text(self, query: str, replacement: str, undo_label: str,
                     paragraph_id: str | None = None, all: bool = False) -> dict:
        """Replace one or every occurrence of `query` as a tracked deletion plus insertion.

        Occurrences are located first, exactly as `find_text` does (both go through
        `_live_hits`: the index, `para.getString().find`, and the same skipping of any match
        that falls inside a pre-existing `Delete` redline); each paragraph's own
        hits are then replaced from the last offset to the first, so the offsets already
        computed for the earlier hits of that paragraph stay valid while the later ones are
        rewritten. `all=False` (the default) replaces only the first occurrence found, in
        document order (or the first occurrence of `paragraph_id`, when given). Every
        replacement runs inside one undo context named `undo_label`, signed "LibreLex" (spec
        §5.4 item 3) with change tracking forced on, so it lands as one `Delete` redline for
        the old text plus one `Insert` redline for the new text. Anchors carry the original
        `start` and `end = start + len(replacement)`; with `all=True`, the anchors reported
        for occurrences after the first *within the same paragraph* are computed on the
        pre-replacement text and are therefore approximate once an earlier hit in that same
        paragraph has changed its length (the replacements themselves stay correct: they are
        applied right-to-left precisely so each cursor position is still valid when used).
        An empty `query` is a no-op; an unknown `paragraph_id` raises as `_entry` does.
        """
        if not query:
            return {"count": 0, "anchors": []}
        groups = self._live_hits(query, paragraph_id, first_paragraph_only=not all)
        if not all and groups:
            groups = [(groups[0][0], groups[0][1][:1])]
        if not groups:
            return {"count": 0, "anchors": []}

        anchors: list[dict] = []
        with self._undo(undo_label):
            with self._identity("LibreLex"), self._recording(True):
                for e, hits in groups:
                    group_anchors = []
                    for start in reversed(hits):
                        cursor = e.container.createTextCursorByRange(e.para.getStart())
                        cursor.goRight(start, False)
                        cursor.goRight(len(query), True)
                        cursor.setString(replacement)
                        group_anchors.append({"paragraph_id": e.id, "start": start,
                                              "end": start + len(replacement)})
                    anchors.extend(reversed(group_anchors))
        return {"count": len(anchors), "anchors": anchors}

    # --- comments (spec §5.5) --------------------------------------------------
    @staticmethod
    def _now_struct():
        n = datetime.now()
        dt = uno.createUnoStruct("com.sun.star.util.DateTime")
        dt.Year, dt.Month, dt.Day = n.year, n.month, n.day
        dt.Hours, dt.Minutes, dt.Seconds, dt.NanoSeconds = n.hour, n.minute, n.second, 0
        dt.IsUTC = False
        return dt

    def _make_annotation(self, author: str, content: str):
        ann = self.doc.createInstance("com.sun.star.text.textfield.Annotation")
        ann.Author = author
        ann.Content = content
        ann.DateTimeValue = self._now_struct()
        return ann

    @staticmethod
    def _dispose_quietly(field) -> None:
        try:
            field.dispose()
        except Exception:
            pass

    def _search_in_paragraph(self, entry: Entry, needle: str):
        """Range of `needle` inside entry.para found by Writer itself, or None."""
        try:
            sd = self.doc.createSearchDescriptor()
            sd.SearchString = needle
            sd.SearchCaseSensitive = True
            sd.SearchRegularExpression = False
            found = self.doc.findNext(entry.para.getStart(), sd)
            if found is None:
                return None
            # accept only a hit that starts inside this paragraph
            if entry.container.compareRegionStarts(found.getStart(), entry.para.getEnd()) < 0:
                return None
            if entry.container.compareRegionStarts(entry.para.getStart(), found.getStart()) < 0:
                return None
            return found
        except Exception:
            return None

    def _range_for(self, entry: Entry, start: int, end: int, expected: str):
        """Cursor spanning `expected` in entry.para, via offsets first, then Writer's search."""
        cur = entry.container.createTextCursorByRange(entry.para.getStart())
        cur.goRight(start, False)
        cur.goRight(end - start, True)
        if cur.getString() == expected:
            return cur
        found = self._search_in_paragraph(entry, expected)
        if found is not None:
            return entry.container.createTextCursorByRange(found)
        return None

    def add_comment(self, paragraph_id: str, start: int, end: int, expected_text: str,
                    author: str, text: str) -> str:
        entry = self._entry(paragraph_id)
        s = entry.para.getString()
        anchored = "exact"
        if not (0 <= start < end <= len(s) and s[start:end] == expected_text):
            pos = s.find(expected_text) if expected_text else -1
            if pos != -1:
                start, end, anchored = pos, pos + len(expected_text), "found"
            else:
                anchored = "paragraph_start"
        with self._undo("LibreLex: commento"), self._recording(False):
            if anchored != "paragraph_start":
                cur = self._range_for(entry, start, end, expected_text)
                if cur is not None:
                    ann = self._make_annotation(author, text)
                    try:
                        entry.container.insertTextContent(cur, ann, True)
                        anchor = ann.getAnchor()
                        ok = anchor is not None and anchor.getString() == expected_text
                    except Exception:
                        ok = False
                    if ok:
                        return anchored
                    self._dispose_quietly(ann)            # orphan rule (spec §5.5)
                anchored = "paragraph_start"
            ann = self._make_annotation(
                author, "[Posizione esatta non trovata nel paragrafo] " + text)
            cur = entry.container.createTextCursorByRange(entry.para.getStart())
            try:
                entry.container.insertTextContent(cur, ann, False)
            except Exception as e:
                self._dispose_quietly(ann)
                raise DocumentActionError(f"commento rifiutato da Writer: {e}") from e
        return anchored

    def remove_comments(self, author: str) -> int:
        targets = []
        enum = self.doc.getTextFields().createEnumeration()
        while enum.hasMoreElements():
            f = enum.nextElement()
            if f.supportsService(ANNOTATION) and f.Author == author:
                targets.append(f)
        with self._undo("LibreLex: rimuovi commenti"), self._recording(False):
            for f in targets:
                f.dispose()
        return len(targets)

    # --- letterhead (design §5.2, §5.3) ---------------------------------------
    def _odt_copy_of(self, url: str, tmpdir: str):
        """A same-content `.odt` copy of `url`, opened hidden/read-only/macro-free (design §6).

        Deviation from the brief: `loadStylesFromURL` called directly on a `.docx` source
        does not carry the header, the footer or their images on 26.8 (probed: the same call
        on an `.odt` source does), presumably because a foreign format's page setup lives in
        the document body, not in a style resource the loader can read on its own. Every
        source is therefore normalised to `.odt` first through an ordinary hidden load and
        `storeToURL`, and `loadStylesFromURL` always reads that copy; the odt copy lives in
        `tmpdir` (0700, spec §8.4), which the caller removes.
        """
        desktop = self.ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.frame.Desktop", self.ctx)
        source = desktop.loadComponentFromURL(
            url, "_blank", 0, (prop("Hidden", True), prop("ReadOnly", True),
                               prop("MacroExecutionMode", 0), prop("UpdateDocMode", 0)))
        if source is None:
            raise DocumentActionError("impossibile aprire il file")
        try:
            copy_path = os.path.join(tmpdir, "letterhead.odt")
            source.storeToURL(uno.systemPathToFileUrl(copy_path), (prop("FilterName", "writer8"),))
        finally:
            with suppress(Exception):
                source.close(True)
        return copy_path

    def apply_letterhead(self, url: str | None) -> dict:
        """Bring a letterhead template's page style into the document, then the act styles.

        Two `loadStylesFromURL` calls, in this order: the first brings only the page and
        frame styles (`LoadTextStyles` False), so the document's own paragraph styles are
        never touched, even with `OverwriteStyles` True; the second brings the template's own
        text styles (`LibreLex` included) without overwriting anything (`OverwriteStyles`
        False), so a lawyer's own adjustment already in the document survives, and a
        `LibreLex` style the template itself adjusted comes in as the template has it. With
        `url` None (no letterhead chosen), only `ensure_act_styles()` runs.
        """
        loaded = False
        page_style = "Standard"
        if url:
            name = unquote(url.rsplit("/", 1)[-1])
            tmpdir = tempfile.mkdtemp(prefix="librelex-letterhead-")          # 0700 (spec §8.4)
            try:
                copy_path = self._odt_copy_of(url, tmpdir)
                copy_url = uno.systemPathToFileUrl(copy_path)
                loader = self.doc.getStyleFamilies()
                loader.loadStylesFromURL(copy_url, (
                    prop("LoadPageStyles", True), prop("LoadFrameStyles", True),
                    prop("LoadTextStyles", False), prop("LoadNumberingStyles", False),
                    prop("OverwriteStyles", True)))
                loader.loadStylesFromURL(copy_url, (
                    prop("LoadPageStyles", False), prop("LoadFrameStyles", False),
                    prop("LoadTextStyles", True), prop("LoadNumberingStyles", False),
                    prop("OverwriteStyles", False)))
                with suppress(Exception):
                    page_style = self.doc.getCurrentController().getViewCursor().PageStyleName
                if page_style != "Standard":
                    with suppress(Exception):
                        standard = (self.doc.getStyleFamilies().getByName("PageStyles")
                                   .getByName("Standard"))
                        if standard.HeaderIsOn:
                            cursor = self.doc.Text.createTextCursorByRange(self.doc.Text.Start)
                            cursor.PageDescName = "Standard"
            except Exception as e:
                raise DocumentActionError(f"carta intestata non applicabile: {name}") from e
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)
            loaded = True
        return {"letterhead": loaded, "created": self.ensure_act_styles(),
                "page_style": page_style}


def make_letterhead(ctx, source_url: str, out_path: str) -> str:
    """Build a `.ott` letterhead template from an odt/docx/doc source (design §5.2, §5.4).

    Refuses to overwrite an existing template. The template is built in a fresh hidden Writer
    document, through the same `apply_letterhead` the panel uses, so it carries the source's
    page style (header, footer, any logo) and the `LibreLex` act styles; the body stays empty.
    """
    basename = os.path.basename(out_path)
    if os.path.exists(out_path):
        raise DocumentActionError(f"modello già presente: {basename}")
    os.makedirs(os.path.dirname(out_path) or ".", mode=0o700, exist_ok=True)
    os.chmod(os.path.dirname(out_path) or ".", 0o700)
    desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    doc = desktop.loadComponentFromURL(
        "private:factory/swriter", "_blank", 0, (prop("Hidden", True),))
    try:
        DocumentAdapter(ctx, doc).apply_letterhead(source_url)
        try:
            doc.storeToURL(uno.systemPathToFileUrl(out_path),
                           (prop("FilterName", "writer8_template"),))
        except Exception as e:
            raise DocumentActionError(f"modello non salvato: {basename}") from e
    finally:
        with suppress(Exception):
            doc.close(True)
    return out_path


def _pdf_frames(model) -> list:
    """Every shape of every page of a Draw-imported PDF with non-empty text, as
    `pdftext.Frame` tuples `(page, y, x, height, text)` (design §4.2)."""
    frames = []
    pages = model.DrawPages
    for page_index in range(pages.getCount()):
        page = pages.getByIndex(page_index)
        for shape_index in range(page.getCount()):
            shape = page.getByIndex(shape_index)
            try:
                text = shape.getString()
            except Exception:
                continue
            if not text:
                continue
            pos, size = shape.Position, shape.Size
            frames.append((page_index + 1, pos.Y, pos.X, size.Height, text))
    return frames


def read_document(ctx, url: str) -> dict:
    """Read a file (a lawyer-chosen "similar case", a case attachment, or a letterhead
    source) into a hidden, read-only document opened through LibreOffice's own filters, and
    return its text (design §4.2, §5.2). A `.pdf` goes through the Draw import filter and its
    text frames are rebuilt into reading-order lines (`pdftext.rebuild_lines`); every other
    supported format goes through the Writer model's body/footnote/table-cell text, as before.
    The document is loaded invisibly (`Hidden`) and never edited (`ReadOnly`), and is always
    closed before this function returns, whether the read succeeded or not.

    The file comes from outside the lawyer's own work (a client's act, an attachment), so it
    is loaded with its macros disabled and its links left alone: `MacroExecutionMode` 0 is
    `com.sun.star.document.MacroExecMode.NEVER_EXECUTE` and `UpdateDocMode` 0 is
    `com.sun.star.document.UpdateDocMode.NO_UPDATE` (no linked section, DDE field or database
    lookup is refreshed while we read it).
    """
    name = re.sub(r"[\x00-\x1f\x7f]+", " ", unquote(url.rsplit("/", 1)[-1])).strip()[:120]
    is_pdf = name.lower().endswith(".pdf")
    desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    load_props = [prop("Hidden", True), prop("ReadOnly", True),
                  prop("MacroExecutionMode", 0), prop("UpdateDocMode", 0)]
    if is_pdf:
        load_props.append(prop("FilterName", "draw_pdf_import"))
    try:
        model = desktop.loadComponentFromURL(url, "_blank", 0, tuple(load_props))
    except Exception as e:
        raise DocumentActionError(f"impossibile aprire il file: {name}") from e
    if model is None:
        raise DocumentActionError(f"impossibile aprire il file: {name}")
    try:
        if is_pdf:
            if not hasattr(model, "DrawPages"):
                raise DocumentActionError(f"impossibile aprire il file: {name}")
            text = rebuild_lines(_pdf_frames(model))
            if not text:
                raise DocumentActionError(f"PDF senza testo (scansione): non leggibile: {name}")
            return {"name": name, "text": text, "chars": len(text), "kind": "pdf"}
        if not hasattr(model, "Text"):
            raise DocumentActionError(
                f"formato non supportato (usa odt, docx, doc, rtf, txt o pdf): {name}")
        paragraphs = DocumentAdapter(ctx, model).read_paragraphs()
        text = "\n\n".join(p["text"] for p in paragraphs)
        return {"name": name, "text": text, "chars": len(text), "kind": "writer"}
    finally:
        with suppress(Exception):
            model.close(True)


read_reference = read_document
