# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Runs both extractors over document paragraphs and yields unified citations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from librelex_core.citations.judgments import extract_judgments
from librelex_core.citations.norms import NormContext, extract_norms
from librelex_core.document import Paragraph


@dataclass
class Citation:
    kind: Literal["norma", "sentenza"]
    paragraph_id: str
    start: int
    end: int
    display_text: str
    canonical: str | None
    court: str | None = None
    verifiable: bool = False
    number: str | None = None
    year: str | None = None
    section: str | None = None


def _mask(text: str, spans: list[tuple[int, int]]) -> str:
    """Blank the given spans, offsets preserved."""
    if not spans:
        return text
    chars = list(text)
    for a, b in spans:
        for i in range(a, b):
            chars[i] = " "
    return "".join(chars)


def extract_all(paragraphs: list[Paragraph]) -> list[Citation]:
    out: list[Citation] = []
    context: NormContext | None = None
    for para in paragraphs:
        judgments = extract_judgments(para.text)
        # The judgment spans are blanked before the norm pass: a court citation is not an
        # act, so what looks like one inside it ("Corte cost. n. 1/2020") must neither be
        # emitted as a norm nor become the act context of the bare articles that follow
        # (task 4 review finding 2; before this, "... Corte cost. n. 1/2020 e art. 5."
        # yielded "art. 5 Cost.").
        masked = _mask(para.text, [(j.start, j.end) for j in judgments])
        norms = extract_norms(masked, context=context)
        items: list[Citation] = []
        for n in norms:
            items.append(Citation("norma", para.id, n.start, n.end, n.display_text, n.canonical(),
                                  verifiable=n.canonical() is not None))
        for j in judgments:
            items.append(
                Citation(
                    "sentenza",
                    para.id,
                    j.start,
                    j.end,
                    j.display_text,
                    j.canonical(),
                    court=j.court,
                    verifiable=j.verifiable_v1,
                    number=j.number,
                    year=j.year,
                    section=j.section,
                )
            )
        items.sort(key=lambda c: c.start)
        out.extend(items)
        if para.kind == "body":
            for n in reversed(norms):
                if n.act is not None:
                    context = (n.act, n.number, n.year)
                    break
    return out


def group_by_canonical(citations: list[Citation]) -> dict[str, list[Citation]]:
    grouped: dict[str, list[Citation]] = {}
    for c in citations:
        if c.canonical:
            grouped.setdefault(c.canonical, []).append(c)
    return grouped
