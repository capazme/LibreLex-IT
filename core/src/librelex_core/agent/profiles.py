# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Tool profiles per command (spec §6.3)."""
from __future__ import annotations

from dataclasses import dataclass

from librelex_core.mcp.client import ALLOWLIST, CATALOGUE_CALCULATORS, ROUTING_GENERATORS

# ROUTING_GENERATORS and CATALOGUE_CALCULATORS are re-exported here (tests and the registry
# import them from this module): the tuples themselves live in mcp/client.py to avoid a
# circular import (this module already imports ALLOWLIST from there). ROUTING_GENERATORS:
# every routing.tool of modelli_atti.json (20, alphabetical). CATALOGUE_CALCULATORS: every
# tool_calcolo of modelli_atti.json plus the two of Appendix B the catalogue does not name
# (17, alphabetical), both mcp-legal-it 2026-09-19.

CALCULATORS = ("interessi_legali", "interessi_mora", "rivalutazione_monetaria",
               "contributo_unificato", "parcella_avvocato_civile", "termini_processuali_civili",
               "scadenza_processuale", "calcolo_tempo_trascorso")
CASE_LAW = ("cerca_giurisprudenza", "cerca_giurisprudenza_unificata", "leggi_sentenza",
            "giurisprudenza_su_norma", "orientamento_su_norma",
            "cerca_giurisprudenza_amministrativa", "leggi_provvedimento_amm",
            "cerca_giurisprudenza_cgue", "leggi_sentenza_cgue",
            "cerca_pronuncia_costituzionale", "leggi_pronuncia_costituzionale")
NORM_SOURCES = ("cite_law", "fetch_act_index", "fetch_full_act", "cerca_brocardi")
# Grounding (spec §6.6 item 1) may only come from tools that *read a source*: the norm
# readers and the case-law tools. Everything else in the allowlist (genera_modello_atto,
# lista_categorie_atti, the act generators, the calculators, verifica_citazioni) echoes the
# model's own parameters back in its result, so treating that echo as grounded would let the
# model insert a reference it invented itself without triggering verification on write.
GROUNDING_SOURCES: frozenset[str] = frozenset(NORM_SOURCES + CASE_LAW)
ALL_DOCUMENT = ("get_document_info", "read_selection", "read_paragraphs", "find_text",
                "insert_markdown", "replace_selection", "replace_text", "add_comment", "goto")


@dataclass(frozen=True)
class Profile:
    legal: tuple[str, ...]
    document: tuple[str, ...]


PROFILES: dict[str, Profile] = {
    "chat": Profile(tuple(sorted(ALLOWLIST)), ALL_DOCUMENT),
    "research": Profile(CASE_LAW + ("cite_law",),
                        ("read_selection", "read_paragraphs", "insert_markdown")),
    "draft": Profile(("genera_modello_atto", "lista_categorie_atti", "cite_law", "fetch_act_index",
                      "fetch_full_act", "verifica_citazioni")
                     + ROUTING_GENERATORS + CATALOGUE_CALCULATORS,
                     ("read_paragraphs", "insert_markdown", "replace_text")),
    "review": Profile(("cite_law", "verifica_citazioni") + CALCULATORS,
                      ("read_selection", "replace_selection", "add_comment", "replace_text")),
}
