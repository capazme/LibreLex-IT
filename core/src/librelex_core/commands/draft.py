# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Template-guided drafting over the agent loop (spec §6.3 profile "draft", §6.9).

One procedure prompt serves every turn of a drafting: the session history carries what the
model already found (template, document data, answers of the lawyer), so a later press of
"Redigi da modello" continues the same drafting instead of starting another one. Every
section reaches the document through insert_markdown, hence through grounding on write.
"""
from __future__ import annotations

from librelex_core.agent.loop import AgentDeps, Emit, TurnOutcome, run_turn_with
from librelex_core.agent.state import DocSession

PROFILE = "draft"
UNDO_LABEL = "LibreLex: redazione da modello"

_PROCEDURE = (
    "Procedi così, riprendendo dal punto in cui eri se questa conversazione contiene già una "
    "redazione in corso: (1) individua il modello con genera_modello_atto (tipo_atto=\"cerca\" "
    "con parametri={\"query\": ...} se non conosci l'identificativo, \"catalogo\" per l'elenco "
    "completo) e segui le sue \"istruzioni\": se indica un tool diretto disponibile (per esempio "
    "decreto_ingiuntivo) usalo per la base del testo, altrimenti componi l'atto seguendo i campi "
    "e la struttura indicati; (2) leggi il documento con read_paragraphs per recuperare i dati "
    "già presenti (parti, importi, date, estremi); (3) se mancano campi obbligatori o dati "
    "necessari ai calcoli, chiedili all'utente in chat, tutti insieme e numerati, e fermati senza "
    "scrivere nel documento; (4) quando i dati bastano, calcola gli importi con gli strumenti di "
    "calcolo indicati dal modello (interessi_legali o interessi_mora, rivalutazione_monetaria, "
    "contributo_unificato, parcella_avvocato_civile) e riporta nel testo i risultati con la data "
    "del calcolo; (5) inserisci l'atto nel documento una partizione per volta, ciascuna con una "
    "chiamata a insert_markdown con where=\"end\": intestazione e parti; premesse in fatto; "
    "motivi in diritto, citando le norme solo dopo averle lette con cite_law; conclusioni con le "
    "somme calcolate; elenco dei documenti allegati; lascia tra parentesi quadre i dati che "
    "nessuno ti ha fornito; (6) rispondi in chat con due righe: che cosa hai inserito e che cosa "
    "resta da completare a mano."
)


def draft_prompt(message: str) -> str:
    """User message of a drafting turn: the lawyer's text plus the fixed procedure."""
    return (f"Redazione guidata da modello.\n"
            f"Messaggio dell'utente: {message}\n"
            f"{_PROCEDURE}")


async def run_draft(session: DocSession, message: str, deps: AgentDeps, emit: Emit,
                    request_id: str) -> TurnOutcome:
    return await run_turn_with(deps, session, draft_prompt(message), PROFILE, emit, request_id,
                               UNDO_LABEL)
