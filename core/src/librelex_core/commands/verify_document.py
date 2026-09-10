# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Deterministic pipeline: verify every citation of the document (spec §7.1, Appendix C)."""
from __future__ import annotations

from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from librelex_core import protocol as p
from librelex_core.citations.extractor import Citation, extract_all
from librelex_core.citations.verifier import Verdict, verify
from librelex_core.document import DocumentClient, Paragraph
from librelex_core.mcp.client import LegalToolsClient

COMMENT_AUTHOR = "LibreLex · verifica"
PROBLEM_VERDICTS = ("inesistente", "non trovata", "metadati discordanti")

Emit = Callable[[Any], Awaitable[None]]


def comment_text(v: Verdict) -> str:
    if v.verdetto in ("inesistente", "non trovata"):
        head = (
            f"Citazione «{v.canonical}» non risulta nelle fonti ufficiali: "
            "controllare gli estremi."
        )
    else:
        head = f"Citazione «{v.canonical}»: metadati discordanti rispetto alla fonte ufficiale."
    tail = f"\n{v.nota}" if v.nota else ""
    return f"{head}{tail}\n(LibreLex verifica esistenza e metadati, non il merito.)"


async def _paragraphs_for_scope(
    doc: DocumentClient, scope: str, include_footnotes: bool
) -> list[Paragraph]:
    if scope == "selection":
        sel = await doc.read_selection()
        if not sel.text or sel.anchor is None:
            return []
        return [Paragraph(id=sel.anchor.paragraph_id, text=sel.text)]
    paras = await doc.read_paragraphs()
    return [x for x in paras if include_footnotes or x.kind != "footnote"]


async def run_verify(
    doc: DocumentClient, tools: LegalToolsClient, scope: Literal["document", "selection"],
    emit: Emit, request_id: str, include_footnotes: bool = True,
) -> dict[str, Any]:
    await emit(p.Status(request_id=request_id, text="Leggo il documento"))
    paragraphs = await _paragraphs_for_scope(doc, scope, include_footnotes)
    offset = 0
    if scope == "selection" and paragraphs:
        sel = await doc.read_selection()
        offset = sel.anchor.start if sel.anchor else 0

    citations: list[Citation] = extract_all(paragraphs)
    for c in citations:
        c.start += offset
        c.end += offset
    await emit(p.Status(
        request_id=request_id,
        text=f"Trovate {len(citations)} citazioni, verifico sulle fonti ufficiali",
    ))

    async def progress(done: int, total: int) -> None:
        await emit(p.Progress(request_id=request_id, done=done, total=total))

    report = await verify(citations, tools, progress=progress)

    await doc.remove_comments(COMMENT_AUTHOR)
    problems: list[dict[str, Any]] = []
    inserted = 0
    for canonical, verdict in report.verdicts.items():
        if verdict.verdetto not in PROBLEM_VERDICTS:
            continue
        occurrences = [c for c in citations if c.canonical == canonical]
        for c in occurrences:
            await doc.add_comment(
                c.paragraph_id, c.start, c.end, c.display_text, COMMENT_AUTHOR,
                comment_text(verdict),
            )
            inserted += 1
        problems.append({
            "citazione": canonical, "verdetto": verdict.verdetto, "nota": verdict.nota,
            "occorrenze": [{"paragraph_id": c.paragraph_id, "start": c.start, "end": c.end}
                           for c in occurrences],
        })

    per_verdetto = Counter(v.verdetto for v in report.verdicts.values())
    summary = {
        "scope": scope,
        "citazioni_totali": len(citations),
        "citazioni_uniche": len({c.canonical for c in citations if c.canonical}),
        "per_verdetto": dict(per_verdetto),
        "problemi": problems,
        "da_controllare_a_mano": report.unverified_courts,
        "non_interpretabili": report.unparsed,
        "commenti_inseriti": inserted,
    }
    await emit(p.Status(
        request_id=request_id,
        text=f"Verifica completata: {inserted} segnalazioni inserite come commenti",
    ))
    return summary
