# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Tool profiles per command (spec §6.3)."""
from __future__ import annotations

from dataclasses import dataclass

from librelex_core.mcp.client import ALLOWLIST

CALCULATORS = ("interessi_legali", "interessi_mora", "rivalutazione_monetaria",
               "contributo_unificato", "parcella_avvocato_civile", "termini_processuali_civili",
               "scadenza_processuale", "calcolo_tempo_trascorso")
CASE_LAW = ("cerca_giurisprudenza", "cerca_giurisprudenza_unificata", "leggi_sentenza",
            "giurisprudenza_su_norma", "orientamento_su_norma",
            "cerca_giurisprudenza_amministrativa", "leggi_provvedimento_amm",
            "cerca_giurisprudenza_cgue", "leggi_sentenza_cgue",
            "cerca_pronuncia_costituzionale", "leggi_pronuncia_costituzionale")
ALL_DOCUMENT = ("get_document_info", "read_selection", "read_paragraphs", "find_text",
                "insert_markdown", "replace_selection", "add_comment", "goto")


@dataclass(frozen=True)
class Profile:
    legal: tuple[str, ...]
    document: tuple[str, ...]


PROFILES: dict[str, Profile] = {
    "chat": Profile(tuple(sorted(ALLOWLIST)), ALL_DOCUMENT),
    "research": Profile(CASE_LAW + ("cite_law",),
                        ("read_selection", "read_paragraphs", "insert_markdown")),
    "draft": Profile(("genera_modello_atto", "lista_categorie_atti", "cite_law", "fetch_act_index",
                      "verifica_citazioni") + CALCULATORS,
                     ("read_paragraphs", "insert_markdown")),
    "review": Profile(("cite_law", "verifica_citazioni") + CALCULATORS,
                      ("read_selection", "replace_selection", "add_comment")),
}
