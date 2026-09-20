# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Per-document session state: turn history, context trimming, usage ceiling (spec §6.5, §6.8)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from librelex_core.protocol import Usage

HISTORY_BUDGET_TOKENS = 40_000
INTERRUPTED_TOOL_RESULT = "ERRORE: turno interrotto"
# Guided Drafting design §4.2: an inserted reference act is truncated to this many characters
# before it ever reaches the session (or the model); it never appears in a Status/Log/error.
MAX_REFERENCE_CHARS = 60_000
# Drafting Workbench design §4.2: each case document (attachment) is truncated to this many
# characters, the set is capped at MAX_ATTACHMENTS documents and MAX_ATTACHMENTS_CHARS in
# total; none of it ever appears in a Status/Log/error.
MAX_ATTACHMENT_CHARS = 60_000
MAX_ATTACHMENTS = 12
MAX_ATTACHMENTS_CHARS = 300_000


def attachments_label(attachments: list[dict[str, Any]]) -> str:
    """The names of a set of attachments as one consent line ("Doc. 1 a.pdf; Doc. 2 b.docx"),
    cut at 200 characters with a trailing ellipsis when it does not fit whole."""
    label = "; ".join(f"Doc. {a['n']} {a['name']}" for a in attachments)
    return label if len(label) <= 200 else label[:199] + "…"


def attachments_chars(attachments: list[dict[str, Any]]) -> int:
    """The total character count of a set of attachments, after trimming."""
    return sum(a["chars"] for a in attachments)


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Rough token estimate: 4 characters per token, no tokenizer dependency."""
    return len(json.dumps(messages, ensure_ascii=False)) // 4


class LimitReached(Exception):
    """Raised when a session crosses its configured token ceiling."""


@dataclass
class Turn:
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_names: dict[str, str] = field(default_factory=dict)

    def close_dangling_tool_calls(self) -> list[str]:
        """Answer every ``tool_calls`` of this turn that has no ``tool`` message yet.

        A turn stopped by a timeout or by cancellation while its tools were running keeps
        the assistant message that asked for them and none of the results: providers reject
        such a history on the next turn ("an assistant message with tool_calls must be
        followed by tool messages responding to each tool_call_id"), which would poison
        every later turn of the session. Returns the ids that were closed.
        """
        answered = {m.get("tool_call_id") for m in self.messages if m.get("role") == "tool"}
        out: list[dict[str, Any]] = []
        closed: list[str] = []
        i = 0
        while i < len(self.messages):
            msg = self.messages[i]
            out.append(msg)
            i += 1
            if msg.get("role") != "assistant" or not msg.get("tool_calls"):
                continue
            while i < len(self.messages) and self.messages[i].get("role") == "tool":
                out.append(self.messages[i])
                i += 1
            for call in msg["tool_calls"]:
                call_id = call.get("id", "")
                if call_id in answered:
                    continue
                name = (call.get("function") or {}).get("name")
                if name:
                    self.tool_names.setdefault(call_id, name)
                out.append({"role": "tool", "tool_call_id": call_id,
                            "content": INTERRUPTED_TOOL_RESULT})
                closed.append(call_id)
        self.messages = out
        return closed

    def compacted(self) -> list[dict[str, Any]]:
        """Copy of the turn's messages with tool results replaced by a placeholder."""
        out = []
        for msg in self.messages:
            if msg.get("role") == "tool":
                name = self.tool_names.get(msg.get("tool_call_id", ""), "sconosciuto")
                k = max(1, estimate_tokens([msg]) // 1000)
                out.append({**msg, "content": f"[risultato di {name} omesso, {k}k token]"})
            else:
                out.append(msg)
        return out


@dataclass
class DraftState:
    """Guided drafting state carried across turns of the ``draft`` command (design §4.2).

    ``template`` is the catalogue ``info()`` result the lawyer picked; ``fields`` the values the
    lawyer filled in. ``base`` records a deterministic direct-tool result already inserted into
    the document (its placeholders still to fill via ``replace_text``), or, with
    ``inserted`` false, one that carried no act text and only reaches the model as data;
    ``base_errore`` is why the generator produced nothing at all, for the panel and for the
    user message; ``partitions`` the narrative sections inserted so far, so a later turn can
    resume after the last one.
    """

    tipo_atto: str
    template: dict[str, Any]
    fields: dict[str, str]
    notes: str = ""
    answers: dict[str, str] = field(default_factory=dict)
    base: dict[str, Any] | None = None
    base_errore: str | None = None
    partitions: list[dict[str, Any]] = field(default_factory=list)
    questions: list[dict[str, Any]] = field(default_factory=list)
    done: bool = False
    riepilogo: str = ""


@dataclass
class DocSession:
    doc_id: str
    turns: list[Turn] = field(default_factory=list)
    consent: Literal["none", "document"] = "none"
    usage: Usage = field(default_factory=Usage)
    draft: DraftState | None = None
    # A reference act the lawyer pasted in for style/structure (design §5.2); never sent to the
    # model until reference_consented flips true, and never echoed back in Status/Log/errors.
    reference: dict[str, Any] | None = None
    reference_consented: bool = False
    # A refusal is a decision about the file, not about one tool call: it is remembered until
    # another reference act is loaded, so a model that insists is answered without asking the
    # lawyer again (final review, finding 6).
    reference_denied: bool = False
    # The case documents (Drafting Workbench design §4): facts for the model to draft from,
    # numbered from 1 in the order the panel sent them. Never sent until attachments_consented
    # flips true, and never echoed back in Status/Log/errors (same consent shape as reference).
    attachments: list[dict[str, Any]] = field(default_factory=list)
    attachments_consented: bool = False
    attachments_denied: bool = False

    def begin_turn(self, user_message: str) -> Turn:
        turn = Turn(messages=[{"role": "user", "content": user_message}])
        self.turns.append(turn)
        return turn

    def messages_for_model(self, system_prompt: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        for i, turn in enumerate(self.turns):
            if i == len(self.turns) - 1:
                out.extend(turn.messages)
            else:
                out.extend(turn.compacted())
        return out

    def end_turn(self, usage: Usage) -> None:
        self.usage = Usage(
            input_tokens=self.usage.input_tokens + usage.input_tokens,
            output_tokens=self.usage.output_tokens + usage.output_tokens,
            cost_usd=(self.usage.cost_usd or 0) + (usage.cost_usd or 0)
            if (self.usage.cost_usd is not None or usage.cost_usd is not None) else None,
        )
        while len(self.turns) > 1:
            msgs = self.messages_for_model("")
            if estimate_tokens(msgs) <= HISTORY_BUDGET_TOKENS:
                break
            self.turns.pop(0)

    @property
    def total_tokens(self) -> int:
        return self.usage.input_tokens + self.usage.output_tokens


def check_ceiling(session: DocSession, ceiling: int) -> None:
    """Global Constraints: session_token_ceiling, mirrors the wording of the refused-turn Error."""
    if session.total_tokens >= ceiling:
        raise LimitReached(
            f"Raggiunto il limite di token della sessione ({session.total_tokens}): "
            "chiudi e riapri il documento per continuare"
        )
