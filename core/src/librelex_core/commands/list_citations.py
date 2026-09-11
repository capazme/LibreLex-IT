# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Deterministic overview: every citation of the document, no network (spec §7.3 item 1)."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Literal

from librelex_core import protocol as p
from librelex_core.citations.extractor import extract_all
from librelex_core.commands.scope import paragraphs_for_scope
from librelex_core.document import DocumentClient


async def run_list_citations(
    doc: DocumentClient, scope: Literal["document", "selection"],
    emit: Callable[[Any], Awaitable[None]], request_id: str, include_footnotes: bool = True,
) -> dict[str, Any]:
    await emit(p.Status(request_id=request_id, text="Leggo il documento"))
    paragraphs, offset = await paragraphs_for_scope(doc, scope, include_footnotes)
    citations = extract_all(paragraphs)
    entries: dict[str, dict[str, Any]] = {}
    unparsed: list[str] = []
    for c in citations:
        c.start += offset
        c.end += offset
        if not c.canonical:
            if c.display_text not in unparsed:
                unparsed.append(c.display_text)
            continue
        entry = entries.setdefault(c.canonical, {
            "citazione": c.canonical, "tipo": c.kind, "corte": c.court,
            "verificabile": c.verifiable, "occorrenze": []})
        entry["occorrenze"].append({"paragraph_id": c.paragraph_id, "start": c.start, "end": c.end})
    await emit(p.Status(
        request_id=request_id,
        text=f"Trovate {len(entries)} citazioni ({len(citations)} occorrenze)"))
    return {"scope": scope, "citazioni_totali": len(citations), "citazioni_uniche": len(entries),
            "citazioni": list(entries.values()), "non_interpretabili": unparsed}
