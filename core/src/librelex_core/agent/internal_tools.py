# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Tools executed inside the core: no network, no document (spec §6.2 item 3)."""
from __future__ import annotations

import json
from datetime import date

from librelex_core.citations.extractor import extract_all
from librelex_core.document import Paragraph

INTERNAL_TOOLS: list[dict] = [
    {"type": "function", "function": {
        "name": "data_odierna", "description": "Data di oggi in formato ISO (AAAA-MM-GG).",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "estrai_citazioni",
        "description": "Estrae le citazioni di norme e sentenze da un testo (estrattore locale, "
                       "senza rete) e restituisce i riferimenti in forma canonica.",
        "parameters": {"type": "object",
                       "properties": {"testo": {"type": "string"}}, "required": ["testo"]}}},
]


def run_internal_tool(name: str, args: dict) -> str:
    if name == "data_odierna":
        return date.today().isoformat()
    if name == "estrai_citazioni":
        cits = extract_all([Paragraph(id="testo", text=str(args.get("testo", "")))])
        return json.dumps([{"citazione": c.canonical, "tipo": c.kind, "verificabile": c.verifiable}
                           for c in cits if c.canonical], ensure_ascii=False)
    raise KeyError(name)
