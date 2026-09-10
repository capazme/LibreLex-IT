# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Document abstraction (spec §5.3): the core never touches UNO, it asks the extension."""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from librelex_core import protocol as p


class DocumentError(Exception):
    """The extension could not perform a document action."""


class Paragraph(BaseModel):
    id: str
    text: str
    style: str = ""
    kind: Literal["body", "footnote", "table_cell"] = "body"


class Anchor(BaseModel):
    paragraph_id: str
    start: int
    end: int


class Selection(BaseModel):
    text: str
    anchor: Anchor | None = None


class DocInfo(BaseModel):
    title: str = ""
    url: str = ""
    paragraph_count: int = 0
    has_selection: bool = False
    cursor_paragraph: str | None = None
    lo_version: str = ""
    has_markdown_filter: bool = True


class InsertedRange(BaseModel):
    from_id: str
    to_id: str


class CommentResult(BaseModel):
    anchored: Literal["exact", "found", "paragraph_start"]


class Occurrence(BaseModel):
    anchor: Anchor
    text: str


class DocumentClient(Protocol):
    async def info(self) -> DocInfo: ...
    async def read_selection(self) -> Selection: ...
    async def read_paragraphs(
        self, from_: int | None = None, to: int | None = None
    ) -> list[Paragraph]: ...
    async def find_text(self, query: str, paragraph_id: str | None = None) -> list[Occurrence]: ...
    async def insert_markdown(
        self, where: str, markdown: str, undo_label: str,
        bookmark: str | None = None, author: str | None = None,
    ) -> InsertedRange: ...
    async def replace_selection(self, markdown: str, undo_label: str) -> InsertedRange: ...
    async def add_comment(
        self, paragraph_id: str, start: int, end: int, expected_text: str,
        author: str, text: str,
    ) -> CommentResult: ...
    async def remove_comments(self, author: str) -> int: ...
    async def goto(self, paragraph_id: str) -> None: ...


# --- in-memory implementation for tests and the dev CLI ----------------------

class FakeDocument:
    def __init__(self, paragraphs: list[str], footnotes: dict[int, str] | None = None,
                 selection: tuple[int, int, int] | None = None, title: str = "fake.odt"):
        self._paragraphs = list(paragraphs)
        self._footnotes = dict(footnotes or {})
        self._selection = selection  # (paragraph index, start, end)
        self.title = title
        self.comments: list[dict[str, Any]] = []
        self.inserts: list[dict[str, Any]] = []
        self.bookmarks: set[str] = set()
        self.visited: list[str] = []

    def _para_text(self, paragraph_id: str) -> str:
        if paragraph_id.startswith("fn:"):
            n = int(paragraph_id.split("/")[0][3:])
            return self._footnotes[n - 1]
        return self._paragraphs[int(paragraph_id.split(":")[1])]

    async def info(self) -> DocInfo:
        return DocInfo(title=self.title, paragraph_count=len(self._paragraphs),
                       has_selection=self._selection is not None,
                       cursor_paragraph=f"p:{self._selection[0]}" if self._selection else "p:0")

    async def read_selection(self) -> Selection:
        if not self._selection:
            return Selection(text="")
        i, s, e = self._selection
        anchor = Anchor(paragraph_id=f"p:{i}", start=s, end=e)
        return Selection(text=self._paragraphs[i][s:e], anchor=anchor)

    async def read_paragraphs(
        self, from_: int | None = None, to: int | None = None
    ) -> list[Paragraph]:
        out: list[Paragraph] = []
        lo, hi = from_ or 0, len(self._paragraphs) if to is None else to
        for i in range(lo, hi):
            out.append(Paragraph(id=f"p:{i}", text=self._paragraphs[i], style="Text body"))
            if i in self._footnotes:
                out.append(
                    Paragraph(id=f"fn:{i + 1}/p:0", text=self._footnotes[i], kind="footnote")
                )
        return out

    async def find_text(self, query: str, paragraph_id: str | None = None) -> list[Occurrence]:
        ids = [paragraph_id] if paragraph_id else [f"p:{i}" for i in range(len(self._paragraphs))]
        out: list[Occurrence] = []
        for pid in ids:
            text, pos = self._para_text(pid), 0
            while (pos := text.find(query, pos)) != -1:
                anchor = Anchor(paragraph_id=pid, start=pos, end=pos + len(query))
                out.append(Occurrence(anchor=anchor, text=query))
                pos += len(query)
        return out

    async def insert_markdown(
        self, where: str, markdown: str, undo_label: str,
        bookmark: str | None = None, author: str | None = None,
    ) -> InsertedRange:
        self.inserts.append({"where": where, "markdown": markdown, "undo_label": undo_label,
                             "bookmark": bookmark, "author": author})
        blocks = [b for b in markdown.split("\n\n") if b.strip()]
        start = len(self._paragraphs)
        self._paragraphs.extend(blocks)
        if bookmark:
            self.bookmarks.add(bookmark)
        return InsertedRange(from_id=f"p:{start}", to_id=f"p:{len(self._paragraphs) - 1}")

    async def replace_selection(self, markdown: str, undo_label: str) -> InsertedRange:
        if not self._selection:
            raise DocumentError("no selection")
        i, s, e = self._selection
        self._paragraphs[i] = self._paragraphs[i][:s] + markdown + self._paragraphs[i][e:]
        self.inserts.append({"where": "selection", "markdown": markdown, "undo_label": undo_label,
                             "bookmark": None, "author": None})
        return InsertedRange(from_id=f"p:{i}", to_id=f"p:{i}")

    async def add_comment(self, paragraph_id: str, start: int, end: int, expected_text: str,
                          author: str, text: str) -> CommentResult:
        para = self._para_text(paragraph_id)
        if para[start:end] == expected_text:
            anchored = "exact"
        elif (pos := para.find(expected_text)) != -1:
            start, end, anchored = pos, pos + len(expected_text), "found"
        else:
            start, end, anchored = 0, 0, "paragraph_start"
        self.comments.append({"paragraph_id": paragraph_id, "start": start, "end": end,
                              "author": author, "text": text, "anchored": anchored})
        return CommentResult(anchored=anchored)

    async def remove_comments(self, author: str) -> int:
        before = len(self.comments)
        self.comments = [c for c in self.comments if c["author"] != author]
        return before - len(self.comments)

    async def goto(self, paragraph_id: str) -> None:
        self.visited.append(paragraph_id)


# --- protocol-backed implementation ------------------------------------------

class BridgeDocument:
    """Turns method calls into doc_call messages and waits for the matching doc_result."""

    def __init__(self, send: Callable[[p.DocCall], Awaitable[None]], request_id: str,
                 timeout_s: float = 120.0):
        self._send = send
        self.request_id = request_id
        self.timeout_s = timeout_s
        self.pending: dict[str, asyncio.Future[dict[str, Any]]] = {}

    def resolve(self, result: p.DocResult) -> None:
        fut = self.pending.pop(result.call_id, None)
        if fut is None or fut.done():
            return
        if result.ok:
            fut.set_result(result.result or {})
        else:
            fut.set_exception(DocumentError(result.error or "unknown document error"))

    async def _call(self, action: str, **args: Any) -> dict[str, Any]:
        call_id = uuid.uuid4().hex[:8]
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self.pending[call_id] = fut
        await self._send(
            p.DocCall(request_id=self.request_id, call_id=call_id, action=action, args=args)
        )
        try:
            return await asyncio.wait_for(fut, self.timeout_s)
        except TimeoutError as e:
            self.pending.pop(call_id, None)
            raise DocumentError(f"timeout waiting for {action}") from e

    async def info(self) -> DocInfo:
        return DocInfo.model_validate(await self._call("get_document_info"))

    async def read_selection(self) -> Selection:
        return Selection.model_validate(await self._call("read_selection"))

    async def read_paragraphs(
        self, from_: int | None = None, to: int | None = None
    ) -> list[Paragraph]:
        res = await self._call("read_paragraphs", from_=from_, to=to)
        return [Paragraph.model_validate(x) for x in res["paragraphs"]]

    async def find_text(self, query: str, paragraph_id: str | None = None) -> list[Occurrence]:
        res = await self._call("find_text", query=query, paragraph_id=paragraph_id)
        return [Occurrence.model_validate(x) for x in res["occurrences"]]

    async def insert_markdown(
        self, where: str, markdown: str, undo_label: str,
        bookmark: str | None = None, author: str | None = None,
    ) -> InsertedRange:
        return InsertedRange.model_validate(await self._call(
            "insert_markdown", where=where, markdown=markdown, undo_label=undo_label,
            bookmark=bookmark, author=author))

    async def replace_selection(self, markdown: str, undo_label: str) -> InsertedRange:
        return InsertedRange.model_validate(await self._call(
            "replace_selection", markdown=markdown, undo_label=undo_label))

    async def add_comment(self, paragraph_id: str, start: int, end: int, expected_text: str,
                          author: str, text: str) -> CommentResult:
        return CommentResult.model_validate(await self._call(
            "add_comment", paragraph_id=paragraph_id, start=start, end=end,
            expected_text=expected_text, author=author, text=text))

    async def remove_comments(self, author: str) -> int:
        return int((await self._call("remove_comments", author=author))["count"])

    async def goto(self, paragraph_id: str) -> None:
        await self._call("goto", paragraph_id=paragraph_id)
