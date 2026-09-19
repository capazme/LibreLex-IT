# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Tool profiles per command (spec §6.3)."""
from __future__ import annotations

from dataclasses import dataclass

from librelex_core.mcp.client import ALLOWLIST

CALCULATORS = ("interessi_legali", "interessi_mora", "rivalutazione_monetaria",
               "contributo_unificato", "parcella_avvocato_civile", "termini_processuali_civili",
               "scadenza_processuale", "calcolo_tempo_trascorso")
GENERATORS = ("decreto_ingiuntivo", "atto_di_precetto", "sollecito_pagamento",
              "procura_alle_liti", "relata_notifica_pec", "attestazione_conformita",
              "sfratto_morosita", "nota_precisazione_credito", "dichiarazione_553_cpc")
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
                      "verifica_citazioni") + GENERATORS + CALCULATORS,
                     ("read_paragraphs", "insert_markdown")),
    "review": Profile(("cite_law", "verifica_citazioni") + CALCULATORS,
                      ("read_selection", "replace_selection", "add_comment")),
}
