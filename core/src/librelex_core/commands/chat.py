# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Free chat over the agent loop (spec §6.3, profile "chat")."""
from __future__ import annotations

from librelex_core import protocol as p
from librelex_core.agent.loop import AgentDeps, Emit, TurnOutcome, run_turn_with
from librelex_core.agent.state import DocSession

PROFILE = "chat"
UNDO_LABEL = "LibreLex: chat"


def chat_message(message: str, context: p.DocContext) -> str:
    """The user message, prefixed by one context line when the panel reports a selection.

    Only the title and the presence of a selection travel: no document text is sent here
    (that needs the model to call a read tool, and consent, spec §8.2).
    """
    if not context.has_selection:
        return message
    return f"[Documento: {context.title or 'senza titolo'}; selezione presente]\n{message}"


async def run_chat(session: DocSession, message: str, context: p.DocContext, deps: AgentDeps,
                   emit: Emit, request_id: str) -> TurnOutcome:
    return await run_turn_with(deps, session, chat_message(message, context), PROFILE, emit,
                               request_id, UNDO_LABEL)
