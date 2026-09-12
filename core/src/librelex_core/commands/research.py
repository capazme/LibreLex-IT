# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Case-law research over the agent loop (spec §6.3, profile "research").

The prompt fixes the procedure (search, read, then write) so the decisions that reach the
document have been read with a tool: grounding on write (spec §6.6) flags the others.
"""
from __future__ import annotations

from librelex_core.agent.loop import AgentDeps, Emit, TurnOutcome, run_turn_with
from librelex_core.agent.state import DocSession

PROFILE = "research"
UNDO_LABEL = "LibreLex: ricerca giurisprudenziale"

_SELECTION_QUESTION = ("la domanda è il testo selezionato nel documento: "
                       "leggilo con read_selection")
_PROCEDURE = (
    "Procedi così: (1) se serve contesto, leggi il documento con read_selection o "
    "read_paragraphs; (2) cerca i precedenti pertinenti con cerca_giurisprudenza, "
    "giurisprudenza_su_norma o cerca_pronuncia_costituzionale, usando pochi termini chiave e i "
    "filtri; (3) leggi con leggi_sentenza (o leggi_pronuncia_costituzionale) le decisioni più "
    "pertinenti, al massimo tre; (4) inserisci al cursore con insert_markdown un testo così "
    "strutturato: un titolo \"Precedenti\", poi per ogni decisione un paragrafo con estremi "
    "completi (autorità, sezione, tipo, data, numero/anno), la massima tra virgolette e una riga "
    "sulla pertinenza; (5) rispondi in chat con due righe di sintesi. Non inserire nel documento "
    "decisioni che non hai letto con uno strumento."
)


def research_prompt(question: str | None) -> str:
    """User message of a research turn; without a question the selection is the question."""
    return (f"Ricerca giurisprudenziale.\n"
            f"Domanda: {question or _SELECTION_QUESTION}\n"
            f"{_PROCEDURE}")


async def run_research(session: DocSession, question: str | None, deps: AgentDeps, emit: Emit,
                       request_id: str) -> TurnOutcome:
    return await run_turn_with(deps, session, research_prompt(question), PROFILE, emit,
                               request_id, UNDO_LABEL)
