# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""The agent loop (spec §6.4): stream, run the tools, ground every write.

Legal tools of the same assistant message run concurrently (government sources are slow),
document and internal tools run sequentially afterwards in call order. Every tool failure
comes back to the model as an ``ERRORE: ...`` string: the only exceptions that leave this
module are ``LLMError`` (mapped to an ``error`` message by the caller) and
``asyncio.CancelledError``.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from librelex_core import protocol as p
from librelex_core.agent.grounding import Grounding, comment_problems, verify_unseen
from librelex_core.agent.internal_tools import run_internal_tool
from librelex_core.agent.profiles import GROUNDING_SOURCES
from librelex_core.agent.prompt import SYSTEM_PROMPT, wrap_data
from librelex_core.agent.registry import ToolRegistry
from librelex_core.agent.state import DocSession
from librelex_core.citations.verifier import RETRYABLE as UNVERIFIED_VERDICT
from librelex_core.citations.verifier import Verdict
from librelex_core.config import LimitsConfig
from librelex_core.document import DocumentClient, DocumentError
from librelex_core.llm.client import ToolCallRequest
from librelex_core.mcp.client import LegalToolsClient, ToolError
from librelex_core.protocol import Usage

Emit = Callable[[Any], Awaitable[None]]
Consent = Callable[[p.ConsentSummary], Awaitable[str]]

BAD_ARGUMENTS = "ERRORE: argomenti non validi"
UNKNOWN_TOOL = "ERRORE: strumento non disponibile in questo profilo"
CONSENT_DENIED = "ERRORE: invio del testo del documento non autorizzato dall'utente"
NO_LEGAL_TOOLS = "ERRORE: mcp-legal-it non disponibile"

READ_TOOLS = ("read_selection", "read_paragraphs", "find_text")
WRITE_TOOLS = ("insert_markdown", "replace_selection")
WRITE_AUTHOR = "LibreLex"


@dataclass
class AgentDeps:
    """Everything a model turn needs besides the session and the user message.

    Built once per request by the caller (``main.py`` or the dev CLI) and passed down to
    the commands, so ``run_chat``/``run_research`` only carry what is specific to them.
    """

    llm: Any
    tools: LegalToolsClient | None
    doc: DocumentClient
    registry: ToolRegistry
    limits: LimitsConfig
    consent: Consent
    endpoint_host: str
    model: str
    zdr: bool


@dataclass
class TurnOutcome:
    text: str = ""
    usage: Usage = field(default_factory=Usage)
    stopped: str | None = None
    inserted: list[dict] = field(default_factory=list)
    flagged: list[str] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)
    tool_calls: int = 0


def _add_usage(a: Usage, b: Usage) -> Usage:
    if a.cost_usd is None and b.cost_usd is None:
        cost = None
    else:
        cost = (a.cost_usd or 0.0) + (b.cost_usd or 0.0)
    return Usage(input_tokens=a.input_tokens + b.input_tokens,
                 output_tokens=a.output_tokens + b.output_tokens, cost_usd=cost)


def _as_json(value: Any) -> str:
    if isinstance(value, BaseModel):
        data: Any = value.model_dump()
    elif isinstance(value, list):
        data = [x.model_dump() if isinstance(x, BaseModel) else x for x in value]
    else:
        data = value
    return json.dumps(data, ensure_ascii=False)


def _unverified_text(refs: list[str]) -> str:
    """Wording of the unverified-references signal, shared by the tool result and the Status."""
    what = ("1 riferimento non verificato" if len(refs) == 1
            else f"{len(refs)} riferimenti non verificati")
    return f"{what} (fonte non disponibile): {', '.join(refs)}."


def _characters(value: Any) -> int:
    """Characters of document text carried by a read result (what consent is asked for)."""
    items = value if isinstance(value, list) else [value]
    return sum(len(getattr(x, "text", "") or "") for x in items)


async def run_turn(
    session: DocSession, user_message: str, profile: str, llm: Any,
    tools: LegalToolsClient | None, doc: DocumentClient, registry: ToolRegistry, emit: Emit,
    request_id: str, limits: LimitsConfig, consent: Consent, endpoint_host: str, model: str,
    zdr: bool, undo_label: str,
) -> TurnOutcome:
    turn = session.begin_turn(user_message)
    grounding = Grounding()
    outcome = TurnOutcome()
    usage = Usage()
    streamed: list[str] = []
    turn_consented = False
    schemas = {t["function"]["name"]: (t["function"].get("parameters") or {})
               for t in registry.tools}

    async def on_delta(piece: str) -> None:
        streamed.append(piece)
        await emit(p.Delta(request_id=request_id, text=piece))

    async def legal_tool(name: str, args: dict) -> str:
        await emit(p.Status(request_id=request_id, text=f"Consulto {name}"))
        if tools is None:
            return NO_LEGAL_TOOLS
        if "formato" in (schemas.get(name, {}).get("properties") or {}):
            # The JSON contract of spec §10: structured output is what grounding reads.
            args = {"formato": "json", **args}
        try:
            text = await tools.call(name, **args)
        except ToolError as e:
            await emit(p.Status(request_id=request_id, text=f"{name}: {e.message}"))
            return f"ERRORE: {e.message}"
        if name in GROUNDING_SOURCES:
            # Everything else in the allowlist (generators, calculators, genera_modello_atto,
            # verifica_citazioni) echoes the model's own parameters and is not a source read
            # (spec §6.6 item 1, final-review finding 1): grounding it would let a reference
            # the model invented pass as "already seen" and skip verification on write.
            grounding.record(text)
        return wrap_data(name, text)

    async def write_tool(name: str, args: dict) -> str:
        """Grounding on write (spec §6.6): verify, then write, then comment the problems."""
        markdown = str(args.get("markdown", ""))
        verdicts: dict[str, Verdict] = {}
        refs = grounding.unseen(markdown)
        if refs:
            await emit(p.Status(
                request_id=request_id,
                text=f"Verifico {len(refs)} riferimenti prima dell'inserimento"))
            verdicts = await verify_unseen(refs, tools)
        if name == "insert_markdown":
            inserted = await doc.insert_markdown(str(args.get("where", "cursor")), markdown,
                                                 undo_label, bookmark=None, author=WRITE_AUTHOR)
        else:
            inserted = await doc.replace_selection(markdown, undo_label)
        # The text is in the document from here on: the write is recorded before anything
        # else can fail, so undo/redline and the panel always know about it (review
        # finding 3), and a comment that cannot be anchored is reported to the model as
        # such instead of looking like a failed insertion.
        outcome.inserted.append(inserted.model_dump())
        # A reference the source could not verify gets no comment and no Status from
        # comment_problems: say it explicitly, to the model and to the panel, so the
        # §6.6 promise does not degrade silently when mcp-legal-it is down (review
        # finding 2).
        unverified = [r for r in refs if r in verdicts
                      and verdicts[r].verdetto == UNVERIFIED_VERDICT]
        note = ""
        if unverified:
            note = " " + _unverified_text(unverified)
            for ref in unverified:
                if ref not in outcome.unverified:
                    outcome.unverified.append(ref)
            await emit(p.Status(request_id=request_id, text=_unverified_text(unverified)))
        try:
            flagged = await comment_problems(doc, inserted, verdicts)
        except DocumentError as e:
            return (f"Inserito nei paragrafi {inserted.from_id}-{inserted.to_id}. "
                    f"ERRORE: commenti di verifica non applicati: {e}" + note)
        for ref in flagged:
            if ref not in outcome.flagged:
                outcome.flagged.append(ref)
        content = f"Inserito nei paragrafi {inserted.from_id}-{inserted.to_id}."
        if flagged:
            content += f" Riferimenti segnalati con un commento: {', '.join(flagged)}."
        return content + note

    async def read_tool(name: str, args: dict) -> str:
        """Consent is asked after the read and before the text enters the messages, so on
        "annulla" nothing has left the machine (spec §8.2)."""
        nonlocal turn_consented
        if name == "read_selection":
            result: Any = await doc.read_selection()
        elif name == "read_paragraphs":
            result = await doc.read_paragraphs(args.get("from_"), args.get("to"))
        else:
            result = await doc.find_text(str(args.get("query", "")), args.get("paragraph_id"))
        chars = _characters(result)
        if chars and session.consent != "document" and not turn_consented:
            decision = await consent(p.ConsentSummary(
                scope="selection" if name == "read_selection" else "paragraphs", chars=chars,
                endpoint_host=endpoint_host, model=model, zdr=zdr))
            if decision == "document":
                session.consent = "document"
            elif decision == "once":
                turn_consented = True
            else:
                return CONSENT_DENIED
        return wrap_data(name, _as_json(result))

    async def document_tool(name: str, args: dict) -> str:
        if name in WRITE_TOOLS:
            return await write_tool(name, args)
        if name in READ_TOOLS:
            return await read_tool(name, args)
        if name == "get_document_info":
            result: Any = await doc.info()
        elif name == "add_comment":
            result = await doc.add_comment(
                str(args.get("paragraph_id", "")), int(args.get("start", 0)),
                int(args.get("end", 0)), str(args.get("expected_text", "")), WRITE_AUTHOR,
                str(args.get("text", "")))
        elif name == "remove_comments":
            result = {"rimossi": await doc.remove_comments(str(args.get("author", "")))}
        else:
            await doc.goto(str(args.get("paragraph_id", "")))
            result = {"ok": True}
        return wrap_data(name, _as_json(result))

    async def execute(call: ToolCallRequest) -> str:
        try:
            args = json.loads(call.arguments or "{}")
        except json.JSONDecodeError:
            return BAD_ARGUMENTS
        if not isinstance(args, dict):
            return BAD_ARGUMENTS
        kind = registry.kind(call.name)
        try:
            if kind == "legal":
                return await legal_tool(call.name, args)
            if kind == "document":
                return await document_tool(call.name, args)
            try:
                return run_internal_tool(call.name, args)
            except KeyError:            # an internal tool listed but no longer implemented
                return UNKNOWN_TOOL
        except DocumentError as e:
            return f"ERRORE: {e}"
        except Exception as e:
            # No tool failure ever breaks the turn: the model reads it and adapts
            # (spec §6.4). Only LLMError and CancelledError leave run_turn.
            return f"ERRORE: {type(e).__name__}: {e}"

    async def run_tool_calls(calls: list[ToolCallRequest]) -> None:
        results: dict[int, str] = {}
        concurrent: list[int] = []
        sequential: list[int] = []
        for i, call in enumerate(calls):
            if call.name not in registry.names:
                results[i] = UNKNOWN_TOOL
            elif registry.kind(call.name) == "legal":
                concurrent.append(i)
            else:
                sequential.append(i)
        if concurrent:
            gathered = await asyncio.gather(*(execute(calls[i]) for i in concurrent))
            results.update(zip(concurrent, gathered, strict=True))
        for i in sequential:
            results[i] = await execute(calls[i])
        for i, call in enumerate(calls):
            turn.tool_names[call.id] = call.name
            turn.messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": results[i]})

    try:
        async with asyncio.timeout(limits.turn_timeout_s):
            for _ in range(limits.max_iterations):
                result = await llm.stream(session.messages_for_model(SYSTEM_PROMPT),
                                          registry.tools, on_delta)
                usage = _add_usage(usage, result.usage)
                message: dict[str, Any] = {"role": "assistant", "content": result.text or None}
                if result.tool_calls:
                    message["tool_calls"] = [
                        {"id": c.id, "type": "function",
                         "function": {"name": c.name, "arguments": c.arguments}}
                        for c in result.tool_calls
                    ]
                turn.messages.append(message)
                if not result.tool_calls:
                    if result.finish_reason == "length":
                        # Truncated by the provider's output cap: the answer is incomplete
                        # and the panel must say so (review finding 5).
                        outcome.stopped = "length"
                    break
                outcome.tool_calls += len(result.tool_calls)
                await run_tool_calls(result.tool_calls)
            else:
                outcome.stopped = "iterations"
    except TimeoutError:
        outcome.stopped = "timeout"
    finally:
        # Cancellation passes through here too: the turn is closed, partial text is kept.
        # A stop between the assistant message and its tool results would leave dangling
        # tool_calls in the history and make every later turn fail (review finding 1).
        turn.close_dangling_tool_calls()
        session.end_turn(usage)
    outcome.text = "".join(streamed)
    outcome.usage = usage
    return outcome


async def run_turn_with(
    deps: AgentDeps, session: DocSession, user_message: str, profile: str, emit: Emit,
    request_id: str, undo_label: str,
) -> TurnOutcome:
    """``run_turn`` with its dependencies bundled in an ``AgentDeps`` (spec §6.4)."""
    return await run_turn(
        session, user_message, profile, deps.llm, deps.tools, deps.doc, deps.registry, emit,
        request_id, deps.limits, deps.consent, deps.endpoint_host, deps.model, deps.zdr,
        undo_label)
