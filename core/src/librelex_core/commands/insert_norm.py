# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Deterministic pipeline: insert the current text of a norm at the cursor (spec §7.2, §5.6)."""
from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any

from librelex_core import protocol as p
from librelex_core.citations.norms import extract_norms
from librelex_core.document import DocumentClient
from librelex_core.mcp.client import LegalToolsClient

MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
          "settembre", "ottobre", "novembre", "dicembre"]
_HEADING_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?art(?:\.|icolo)?\s*\d+(?:\s*-?\s*(?:bis|ter|quater|quinquies|sexies|"
    r"septies|octies|novies|decies))?\.?\s*(?:[-–—:(]\s*(?P<rubrica>[^)]+?)\)?)?\s*$",
    re.IGNORECASE,
)


def source_label(fonte: str) -> str:
    """Human label of the JSON `fonte` field ("normattiva", "normattiva-akn", "eurlex", ...)."""
    f = (fonte or "").lower()
    if f.startswith("normattiva"):
        return "Normattiva"
    if f.startswith("eur"):
        return "EUR-Lex"
    return "fonte ufficiale"


def split_heading(testo: str) -> tuple[str | None, str]:
    """Strip the server's leading heading line(s) ("### Art. 2043", "Art. 2043.") and return
    (rubrica, remaining text). The rubrica, when the heading carries one, goes into the
    bold title instead of the blockquote (spec §7.2 item 3)."""
    lines = testo.splitlines()
    rubrica: str | None = None
    while lines and (m := _HEADING_RE.match(lines[0])):
        rubrica = rubrica or ((m.group("rubrica") or "").strip() or None)
        lines.pop(0)
    while lines and not lines[0].strip():
        lines.pop(0)
    return rubrica, "\n".join(lines)


class UnparsedReference(Exception):
    """The reference could not be resolved; the core never guesses."""


def parse_reference(text: str) -> str:
    norms = [n for n in extract_norms(text.strip()) if n.canonical()]
    if not norms:
        raise UnparsedReference(f"riferimento non interpretabile: «{text.strip()}». "
                                "Formato atteso: art. <numero> <atto>, es. art. 2043 c.c.")
    if len(norms) > 1:
        raise UnparsedReference("indicare un solo riferimento per volta")
    return norms[0].canonical()  # type: ignore[return-value]


def bookmark_name(source: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", source).strip("_")
    if len(slug) > 80:
        # Keep the tail, not the head: two articles of the same act share a long common
        # URL/URN prefix (host, uri-res path, act identifier), and the article
        # discriminator sits at the very end. Truncating the head produced identical
        # bookmark names for e.g. art. 2043 and art. 2059 c.c. (review finding 7).
        slug = slug[-80:]
    return f"LibreLex.norma.{slug}"


def format_norm_markdown(data: dict[str, Any], today: date) -> str:
    heading = data["riferimento"]
    heading = heading[0].upper() + heading[1:]
    rubrica, body = split_heading(data["testo"])
    if rubrica:
        heading = f"{heading} ({rubrica})"
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    quote = "\n".join(f"> {ln}" for ln in lines) if lines else "> (testo non disponibile)"
    label = source_label(data.get("fonte", ""))
    when = f"{today.day} {MONTHS[today.month - 1]} {today.year}"
    return f"**{heading}**\n\n{quote}\n\n*Testo vigente al {when}, fonte {label}, {data['url']}*\n"


async def run_insert_norm(
    doc: DocumentClient, tools: LegalToolsClient, reference: str | None,
    emit: Callable[[Any], Awaitable[None]], request_id: str,
    author: str | None = "LibreLex",
) -> dict[str, Any]:
    if not reference:
        sel = await doc.read_selection()
        reference = sel.text
        if not reference:
            raise UnparsedReference(
                "nessun riferimento: scrivilo nel pannello o selezionalo nel testo"
            )
    canonical = parse_reference(reference)
    await emit(p.Status(request_id=request_id, text=f"Recupero il testo vigente di {canonical}"))
    raw = await tools.call("cite_law", reference=canonical, formato="json")
    data = json.loads(raw)
    if data.get("errore") or not data.get("testo"):
        raise UnparsedReference(f"{canonical}: {data.get('errore') or 'testo non disponibile'}")
    data["riferimento"] = canonical
    markdown = format_norm_markdown(data, date.today())
    # The urn is the JSON contract's stable, shorter identifier (mcp-legal-it
    # _cite_law_struct); fall back to the url if it is missing.
    bookmark = bookmark_name(data.get("urn") or data["url"])
    inserted = await doc.insert_markdown("cursor", markdown, f"LibreLex: inserisci {canonical}",
                                         bookmark=bookmark, author=author)
    await emit(p.Status(request_id=request_id, text=f"Inserito {canonical} come revisione"))
    return {"riferimento": canonical, "url": data["url"], "bookmark": bookmark,
            "inserted": inserted.model_dump()}
