# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Grounding on write (spec §6.6): nothing reaches the document unverified."""
from __future__ import annotations

from typing import Any

from librelex_core.citations.extractor import Citation, extract_all
from librelex_core.citations.verifier import Verdict, verify_citations
from librelex_core.commands.verify_document import COMMENT_AUTHOR, PROBLEM_VERDICTS, comment_text
from librelex_core.document import DocumentClient, InsertedRange, Paragraph


class Grounding:
    """The canonical references seen in the tool results of the current turn (spec §6.6)."""

    def __init__(self) -> None:
        self.seen: set[str] = set()

    def record(self, text: str) -> None:
        for c in extract_all([Paragraph(id="tool", text=text)]):
            if c.canonical:
                self.seen.add(c.canonical)

    def unseen(self, markdown: str) -> list[str]:
        """Canonical, verifiable references of ``markdown`` never seen in this turn,
        unique and in order of appearance."""
        paras = [Paragraph(id=f"md:{i}", text=line)
                 for i, line in enumerate(markdown.splitlines())]
        out: list[str] = []
        for c in extract_all(paras):
            if (c.canonical and c.verifiable and _self_contained(c)
                    and c.canonical not in self.seen and c.canonical not in out):
                out.append(c.canonical)
        return out


def _self_contained(c: Citation) -> bool:
    """True when the reference carries its own act: a bare "art. 5" whose act comes from
    the surrounding context is a reading of the core, not a reference written by the model,
    so it is not verified on write (the core never guesses what to verify, spec §6.6)."""
    own = extract_all([Paragraph(id="ref", text=c.display_text)])
    return any(x.canonical == c.canonical for x in own)


async def verify_unseen(refs: list[str], tools: Any) -> dict[str, Verdict]:
    if not refs:
        return {}
    if tools is None:
        return {r: Verdict(r, "non verificata", "mcp-legal-it non disponibile") for r in refs}
    return await verify_citations(refs, tools)


def _body_index(paragraph_id: str) -> int | None:
    return int(paragraph_id[2:]) if paragraph_id.startswith("p:") and paragraph_id[2:].isdigit() \
        else None


async def comment_problems(doc: DocumentClient, inserted: InsertedRange,
                           verdicts: dict[str, Verdict]) -> list[str]:
    """Comment every occurrence of a problematic reference inside the inserted range,
    re-reading the text from the document (spec §6.6 item 4); returns the flagged canonicals."""
    problems = {k: v for k, v in verdicts.items() if v.verdetto in PROBLEM_VERDICTS}
    lo, hi = _body_index(inserted.from_id), _body_index(inserted.to_id)
    if not problems or lo is None or hi is None:
        return []
    paragraphs = await doc.read_paragraphs(lo, hi + 1)
    flagged: list[str] = []
    for c in extract_all([x for x in paragraphs if x.kind == "body"]):
        if c.canonical in problems:
            await doc.add_comment(c.paragraph_id, c.start, c.end, c.display_text, COMMENT_AUTHOR,
                                  comment_text(problems[c.canonical]))
            if c.canonical not in flagged:
                flagged.append(c.canonical)
    return flagged
