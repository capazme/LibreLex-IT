# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Which paragraphs a command works on (spec §7.1 step 1, §7.3)."""
from __future__ import annotations

from librelex_core.document import DocumentClient, Paragraph


async def paragraphs_for_scope(
    doc: DocumentClient, scope: str, include_footnotes: bool
) -> tuple[list[Paragraph], int]:
    """Return the paragraphs to extract from and the offset to add to citation spans.

    Reads the selection exactly once: text and anchor offset come from the same
    `read_selection()` call, so a selection change between reads can never desync them.
    """
    if scope == "selection":
        sel = await doc.read_selection()
        if not sel.text or sel.anchor is None:
            return [], 0
        return [Paragraph(id=sel.anchor.paragraph_id, text=sel.text)], sel.anchor.start
    paras = await doc.read_paragraphs()
    return [x for x in paras if include_footnotes or x.kind != "footnote"], 0
