# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Deterministic pipeline: show the text of one citation in the panel (spec §7.3 item 2)."""
from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

from librelex_core import protocol as p
from librelex_core.citations.extractor import Citation, extract_all
from librelex_core.commands.insert_norm import UnparsedReference, source_label, split_heading
from librelex_core.document import DocumentClient, Paragraph
from librelex_core.mcp.client import LegalToolsClient, ToolError

MAX_TEXT_CHARS = 6000
_ROMAN = {"I": "1", "II": "2", "III": "3", "IV": "4", "V": "5", "VI": "6"}
_SECTION_CODES = {"un.": "SU", "lav.": "L", "trib.": "T"}
# mcp-legal-it renders a "massima" (headnote) two ways depending on the tool: as its own
# heading with the text on the following lines (cerdef's CTP/CTR reader, and the fake server
# used in tests), or inline after a bold label (corte_cost's pronunce_cost_su_norma). Neither
# leggi_sentenza nor leggi_pronuncia_costituzionale emits one today, so this is best-effort.
_MASSIMA_HEADING = re.compile(r"^\s*#{1,6}\s*massim[ae]\b\s*$", re.IGNORECASE)
_MASSIMA_INLINE = re.compile(r"^\s*\*\*massim[ae]\*\*\s*:\s*(?P<text>.+\S)\s*$", re.IGNORECASE)
_HEADING = re.compile(r"^\s*#{1,6}\s")
_ERROR_PREFIX = re.compile(r"^\s*(?:\*\*)?errore", re.IGNORECASE)


class TextUnavailable(Exception):
    """The source cannot give a text for this reference in this version."""


def section_code(section: str | None) -> str:
    if not section:
        return ""
    if section in _SECTION_CODES:
        return _SECTION_CODES[section]
    return _ROMAN.get(section.upper(), section)


def truncate(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_TEXT_CHARS:
        return text, False
    return text[:MAX_TEXT_CHARS].rstrip() + " […]", True


def extract_massima(text: str) -> str | None:
    """The massima (headnote), inline after "**Massima**:" or in the block under a heading
    that reads "Massima"/"Massime", up to the next heading."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        inline = _MASSIMA_INLINE.match(line)
        if inline:
            return inline.group("text").strip()
        if _MASSIMA_HEADING.match(line):
            block: list[str] = []
            for follow in lines[i + 1:]:
                if _HEADING.match(follow):
                    break
                stripped = follow.strip()
                if stripped:
                    block.append(stripped)
                elif block:
                    break
            return "\n".join(block) if block else None
    return None


def parse_any(text: str) -> Citation:
    cits = [c for c in extract_all([Paragraph(id="ref", text=text.strip())]) if c.canonical]
    if not cits:
        raise UnparsedReference(
            f"riferimento non interpretabile: «{text.strip()}». "
            "Esempi: art. 2043 c.c., Cass. n. 12345/2024, Corte cost. n. 1/2020")
    if len(cits) > 1:
        raise UnparsedReference("indicare un solo riferimento per volta")
    return cits[0]


def _check_tool_text(name: str, text: str) -> str:
    if not text or not text.strip() or _ERROR_PREFIX.match(text.strip()):
        raise TextUnavailable(f"{name}: {text.strip()[:200] or 'risposta vuota'}")
    return text


async def run_show_text(
    doc: DocumentClient, tools: LegalToolsClient, reference: str | None,
    emit: Callable[[Any], Awaitable[None]], request_id: str,
) -> dict[str, Any]:
    if not reference:
        sel = await doc.read_selection()
        reference = sel.text
        if not reference:
            raise UnparsedReference(
                "nessun riferimento: scrivilo nel pannello o selezionalo nel testo")
    cit = parse_any(reference)
    canonical = cit.canonical or ""
    await emit(p.Status(request_id=request_id, text=f"Recupero il testo di {canonical}"))
    try:
        if cit.kind == "norma":
            data = json.loads(await tools.call("cite_law", reference=canonical, formato="json"))
            if data.get("errore") or not data.get("testo"):
                raise TextUnavailable(
                    f"{canonical}: {data.get('errore') or 'testo non disponibile'}")
            rubrica, body = split_heading(data["testo"])
            testo, cut = truncate(body)
            return {"tipo": "norma", "riferimento": canonical,
                    "titolo": f"{canonical} ({rubrica})" if rubrica else canonical,
                    "testo": testo, "massima": None, "fonte": source_label(data.get("fonte", "")),
                    "url": data.get("url", ""), "troncato": cut}
        if cit.court == "cassazione":
            raw = _check_tool_text("leggi_sentenza", await tools.call(
                "leggi_sentenza", numero=int(cit.number or 0), anno=int(cit.year or 0),
                sezione=section_code(cit.section)))
            fonte = "Italgiure"
        elif cit.court == "corte_costituzionale":
            raw = _check_tool_text("leggi_pronuncia_costituzionale", await tools.call(
                "leggi_pronuncia_costituzionale",
                numero=int(cit.number or 0), anno=int(cit.year or 0)))
            fonte = "Corte costituzionale"
        else:
            raise TextUnavailable(
                f"testo non disponibile per {canonical}: in questa versione si leggono norme, "
                "Cassazione e Corte costituzionale (TAR, Consiglio di Stato e CGUE "
                "arrivano con la ricerca)")
    except ToolError as e:
        raise TextUnavailable(str(e)) from e
    testo, cut = truncate(raw)
    return {"tipo": "sentenza", "riferimento": canonical, "titolo": canonical, "testo": testo,
            "massima": extract_massima(raw), "fonte": fonte, "url": "", "troncato": cut}
