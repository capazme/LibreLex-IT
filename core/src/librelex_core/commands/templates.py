# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Catalogue of act templates from mcp-legal-it (design §4.1): what the Redazione panel shows
before any model turn. Deterministic, no LLM."""
from __future__ import annotations

import json
from typing import Any

from librelex_core.mcp.client import LegalToolsClient, ToolSpec

FIELD_TYPES = ("testo", "numero", "data", "sino")


class TemplateNotFound(Exception):
    """The catalogue has no such tipo_atto (the server's message and suggestions)."""


def field_type(name: str, schema: dict | None) -> str:
    # Only a field backed by a schema (a parameter of the routing tool) gets the "data" name
    # heuristic; a field the tool doesn't know about (no direct tool, or resource routing) is
    # always "testo" (design §4.1: "fields without a schema are testo").
    if schema is None:
        return "testo"
    t = schema.get("type")
    types = t if isinstance(t, list) else [t]
    if "boolean" in types:
        return "sino"
    if "integer" in types or "number" in types:
        return "numero"
    return "data" if "data" in name.lower() else "testo"


class TemplateCatalogue:
    def __init__(self, tools: LegalToolsClient):
        self._tools = tools
        self._catalogue: dict | None = None
        self._info: dict[str, dict] = {}

    async def _lookup(self, tipo_atto: str, parametri: dict | None = None) -> dict:
        text = await self._tools.call("genera_modello_atto", tipo_atto=tipo_atto,
                                      parametri=parametri or {})
        return json.loads(text)

    async def list(self, query: str | None = None) -> dict:
        if query:
            data = await self._lookup("cerca", {"query": query})
            hits = [{"tipo_atto": r["tipo_atto"], "descrizione": r["descrizione"],
                     "categoria": r.get("categoria", ""), "tier": r.get("tier", 0)}
                    for r in data.get("risultati", [])]
            return {"modelli": hits, "totale": len(hits), "query": query}
        if self._catalogue is None:
            data = await self._lookup("catalogo")
            models = [{"tipo_atto": e["tipo_atto"], "descrizione": e["descrizione"],
                       "categoria": cat, "tier": e.get("tier", 0)}
                      for cat, entries in data.get("catalogo", {}).items() for e in entries]
            self._catalogue = {"modelli": models, "totale": len(models), "query": None}
        return self._catalogue

    async def info(self, tipo_atto: str, specs: list[ToolSpec]) -> dict:
        if tipo_atto in self._info:
            return self._info[tipo_atto]
        data = await self._lookup(tipo_atto)
        if data.get("errore"):
            hint = data.get("suggerimenti") or []
            names = ", ".join(s.get("tipo_atto", "") for s in hint if isinstance(s, dict))
            raise TemplateNotFound(data["errore"] + (f"; suggerimenti: {names}" if names else ""))
        routing = _routing(data)
        schema_props: dict[str, Any] = {}
        if routing["tool"]:
            spec = next((s for s in specs if s.name == routing["tool"]), None)
            schema_props = (spec.input_schema.get("properties") or {}) if spec else {}
        campi = [_field(n, True, schema_props) for n in data.get("campi_obbligatori", [])]
        campi += [_field(n, False, schema_props) for n in data.get("campi_opzionali", [])]
        info = {
            "tipo_atto": tipo_atto, "descrizione": data.get("descrizione", ""),
            "categoria": data.get("categoria", ""),
            "campi_obbligatori": list(data.get("campi_obbligatori", [])),
            "campi_opzionali": list(data.get("campi_opzionali", [])),
            "tool_calcolo": list(data.get("tool_calcolo", [])),
            "riferimenti_normativi": list(data.get("riferimenti_normativi", [])),
            "avvertenze": list(data.get("avvertenze", [])),
            "istruzioni": data.get("istruzioni", ""), "routing": routing, "campi": campi,
        }
        self._info[tipo_atto] = info
        return info


def _routing(data: dict) -> dict:
    if data.get("tool_diretto"):
        tipo = "tool_enhance" if "disponibile_da_fase" in data else "tool_diretto"
        if data.get("tool_non_ancora_disponibile"):
            tipo = "preventivo_procedura"
        return {"tipo": tipo, "tool": data["tool_diretto"],
                "parametri_fissi": dict(data.get("parametri_fissi") or {}), "resource": None}
    if data.get("resource_modello"):
        return {"tipo": "resource", "tool": None, "parametri_fissi": {},
                "resource": data["resource_modello"]}
    return {"tipo": "sconosciuto", "tool": None, "parametri_fissi": {}, "resource": None}


def _field(name: str, mandatory: bool, props: dict) -> dict:
    schema = props.get(name)
    desc = (schema or {}).get("description") or ""
    return {"nome": name, "tipo": field_type(name, schema), "obbligatorio": mandatory,
            "descrizione": desc[:120]}
