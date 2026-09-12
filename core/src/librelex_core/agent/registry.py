# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Merges legal, document and internal tools into one OpenAI `tools` array per profile
(spec §6.2). ``ToolRegistry`` is built once per turn from the profile of the active
command: it filters and orders the three sources deterministically so the array is
byte-stable across turns (prompt caching, spec §6.1)."""
from __future__ import annotations

import copy
import tomllib
from pathlib import Path
from typing import Literal

from librelex_core.agent.internal_tools import INTERNAL_TOOLS
from librelex_core.agent.profiles import PROFILES
from librelex_core.mcp.client import ToolSpec

_OVERRIDES_PATH = Path(__file__).with_name("tool_overrides.toml")

# Keys of a JSON Schema object worth sending to the model; everything else (``$schema``,
# ``title``, ``examples``, ``additionalProperties``, pydantic/fastmcp noise, ...) is dropped
# by `compact_schema` (spec §6.2).
_SCHEMA_KEYS = ("type", "properties", "required", "enum", "items", "default", "description")


def compact_schema(schema: dict, max_desc: int = 120) -> dict:
    """A deep copy of `schema` keeping only `_SCHEMA_KEYS`, applied recursively to nested
    `properties`/`items`, with `description` truncated to `max_desc` characters at a word
    boundary (`…`). Cuts per-turn token cost without changing the schema's shape (spec §6.2:
    parameter schemas pass through, only bloat and verbosity are removed)."""
    out: dict = {}
    for key in _SCHEMA_KEYS:
        if key not in schema:
            continue
        value = schema[key]
        if key == "description" and isinstance(value, str):
            out[key] = _truncate(value, max_desc)
        elif key == "properties" and isinstance(value, dict):
            out[key] = {name: compact_schema(sub, max_desc) for name, sub in value.items()}
        elif key == "items" and isinstance(value, dict):
            out[key] = compact_schema(value, max_desc)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _truncate(text: str, max_desc: int) -> str:
    if len(text) <= max_desc:
        return text
    cut = text[:max_desc]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip() + "…"


# The nine document actions of spec §5.3, as OpenAI tool objects. `undo_label`, `bookmark`
# and `author` (where present) are set by the core, not exposed to the model.
DOCUMENT_TOOLS: dict[str, dict] = {
    "get_document_info": {"type": "function", "function": {
        "name": "get_document_info",
        "description": "Informazioni sul documento aperto: titolo, numero di paragrafi, "
                       "presenza di una selezione, paragrafo del cursore.",
        "parameters": {"type": "object", "properties": {}}}},
    "read_selection": {"type": "function", "function": {
        "name": "read_selection",
        "description": "Testo attualmente selezionato dall'utente nel documento, con la sua "
                       "posizione (ancora). Selezione vuota → testo vuoto.",
        "parameters": {"type": "object", "properties": {}}}},
    "read_paragraphs": {"type": "function", "function": {
        "name": "read_paragraphs",
        "description": "Paragrafi del documento in un intervallo di indici (estremi opzionali; "
                       "omessi → tutto il documento), con note e celle di tabella nel range.",
        "parameters": {"type": "object", "properties": {
            "from_": {"type": ["integer", "null"],
                      "description": "Indice del primo paragrafo del corpo (omesso: dall'inizio)."},
            "to": {"type": ["integer", "null"],
                   "description": "Indice successivo all'ultimo paragrafo "
                                  "(omesso: fino alla fine)."},
        }}}},
    "find_text": {"type": "function", "function": {
        "name": "find_text",
        "description": "Cerca un testo nel documento (o in un paragrafo dato) e restituisce le "
                       "occorrenze con la loro posizione: rete di sicurezza per ancorare i "
                       "commenti.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Testo da cercare."},
            "paragraph_id": {"type": ["string", "null"],
                             "description": "Limita la ricerca a questo paragrafo, se indicato."},
        }, "required": ["query"]}}},
    "insert_markdown": {"type": "function", "function": {
        "name": "insert_markdown",
        "description": "Inserisce markdown nel documento come modifica tracciata (revisione), "
                       "senza sostituire nulla. Le citazioni non ancora verificate in questo turno "
                       "vengono controllate prima dell'inserimento (grounding, spec §6.6).",
        "parameters": {"type": "object", "properties": {
            "where": {"type": "string",
                      "description": "Dove inserire: \"cursor\" (al cursore), \"end\" (in fondo "
                                    "al documento) oppure \"after:<id>\" (dopo il paragrafo con "
                                    "quell'id)."},
            "markdown": {"type": "string", "description": "Testo in markdown da inserire."},
        }, "required": ["where", "markdown"]}}},
    "replace_selection": {"type": "function", "function": {
        "name": "replace_selection",
        "description": "Sostituisce la selezione corrente con markdown, come modifica tracciata "
                       "(cancellazione + inserimento). Le citazioni nuove vengono verificate prima "
                       "della sostituzione (grounding, spec §6.6).",
        "parameters": {"type": "object", "properties": {
            "markdown": {"type": "string",
                        "description": "Testo in markdown che sostituisce la selezione."},
        }, "required": ["markdown"]}}},
    "add_comment": {"type": "function", "function": {
        "name": "add_comment",
        "description": "Aggiunge un commento di Writer ancorato a un intervallo di testo di un "
                       "paragrafo, verificato tramite il testo atteso.",
        "parameters": {"type": "object", "properties": {
            "paragraph_id": {"type": "string", "description": "Id del paragrafo da annotare."},
            "start": {"type": "integer", "description": "Offset di inizio dell'intervallo."},
            "end": {"type": "integer", "description": "Offset di fine dell'intervallo."},
            "expected_text": {"type": "string",
                              "description": "Testo atteso nell'intervallo, per verificarne "
                                             "l'ancoraggio."},
            "text": {"type": "string", "description": "Testo del commento."},
        }, "required": ["paragraph_id", "start", "end", "expected_text", "text"]}}},
    "remove_comments": {"type": "function", "function": {
        "name": "remove_comments",
        "description": "Rimuove i commenti di un dato autore, per rilanci idempotenti della "
                       "pipeline di verifica (spec §7.1).",
        "parameters": {"type": "object", "properties": {
            "author": {"type": "string", "description": "Autore dei commenti da rimuovere."},
        }, "required": ["author"]}}},
    "goto": {"type": "function", "function": {
        "name": "goto",
        "description": "Sposta il cursore/la vista sul paragrafo indicato, per la navigazione "
                       "dal pannello.",
        "parameters": {"type": "object", "properties": {
            "paragraph_id": {"type": "string", "description": "Id del paragrafo di destinazione."},
        }, "required": ["paragraph_id"]}}},
}


def load_overrides() -> dict[str, str]:
    """Concise descriptions for the legal tools, keyed by name (spec §6.2)."""
    with _OVERRIDES_PATH.open("rb") as f:
        data = tomllib.load(f)
    return dict(data.get("descriptions", {}))


def concise(spec: ToolSpec, overrides: dict[str, str]) -> str:
    """The override for ``spec.name``, else the first paragraph of the original description,
    capped at 300 characters."""
    override = overrides.get(spec.name)
    if override is not None:
        return override
    first_paragraph = spec.description.split("\n\n", 1)[0].strip()
    return first_paragraph[:300]


class ToolRegistry:
    """The merged `tools` array for one profile (spec §6.2): legal tools of the profile
    (from ``specs``, with concise descriptions), then its document tools, then the internal
    tools, each group sorted by name for a deterministic, byte-stable result."""

    def __init__(self, specs: list[ToolSpec], profile: str):
        self.profile = profile
        chosen = PROFILES[profile]
        overrides = load_overrides()
        by_name = {s.name: s for s in specs}

        legal_names = sorted(n for n in chosen.legal if n in by_name)
        legal_tools = [
            {"type": "function", "function": {
                "name": n,
                "description": concise(by_name[n], overrides),
                "parameters": compact_schema(by_name[n].input_schema),
            }}
            for n in legal_names
        ]

        document_names = sorted(n for n in chosen.document if n in DOCUMENT_TOOLS)
        document_tools = [DOCUMENT_TOOLS[n] for n in document_names]

        internal_tools = sorted(INTERNAL_TOOLS, key=lambda t: t["function"]["name"])
        internal_names = [t["function"]["name"] for t in internal_tools]

        self.tools: list[dict] = legal_tools + document_tools + internal_tools
        self.names: list[str] = legal_names + document_names + internal_names
        self._kinds: dict[str, str] = (
            {n: "legal" for n in legal_names}
            | {n: "document" for n in document_names}
            | {n: "internal" for n in internal_names}
        )

    def kind(self, name: str) -> Literal["legal", "document", "internal"]:
        return self._kinds[name]
