# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""librelex-core stdio server (spec §4.2, §4.3, §6.8)."""
from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from pydantic import ValidationError

from librelex_core import PROTOCOL_VERSION, __version__
from librelex_core import protocol as p
from librelex_core.agent.loop import AgentDeps, TurnOutcome
from librelex_core.agent.registry import ToolRegistry
from librelex_core.agent.state import DocSession, LimitReached, check_ceiling
from librelex_core.commands.chat import PROFILE as CHAT_PROFILE
from librelex_core.commands.chat import run_chat
from librelex_core.commands.insert_norm import UnparsedReference, run_insert_norm
from librelex_core.commands.list_citations import run_list_citations
from librelex_core.commands.research import PROFILE as RESEARCH_PROFILE
from librelex_core.commands.research import run_research
from librelex_core.commands.show_text import TextUnavailable, run_show_text
from librelex_core.commands.verify_document import run_verify
from librelex_core.config import Config, load_config
from librelex_core.document import BridgeDocument, DocumentError
from librelex_core.llm.client import LLMClient, LLMError
from librelex_core.mcp.client import IncompatibleServer, LegalToolsClient, ToolSpec

# Commands that need a live mcp-legal-it connection; list_citations is a local,
# deterministic pipeline and must keep working even against an incompatible server.
NEEDS_TOOLS = ("verify_citations", "insert_norm", "show_text")
# Model-driven commands still to come (spec §6.3).
NOT_IMPLEMENTED = ("draft", "review")
NO_LEGAL_TOOLS_STATUS = "mcp-legal-it non disponibile: rispondo senza strumenti giuridici"


class LineTransport(Protocol):
    async def readline(self) -> str | None: ...
    async def write(self, line: str) -> None: ...


class MemoryTransport:
    def __init__(self, inbox: asyncio.Queue[str | None], outbox: asyncio.Queue[str]):
        self.inbox, self.outbox = inbox, outbox

    async def readline(self) -> str | None:
        return await self.inbox.get()

    async def write(self, line: str) -> None:
        await self.outbox.put(line)


class StdioTransport:
    def __init__(self) -> None:
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def _open(self) -> None:
        loop = asyncio.get_running_loop()
        self._reader = asyncio.StreamReader()
        await loop.connect_read_pipe(
            lambda: asyncio.StreamReaderProtocol(self._reader), sys.stdin)
        transport, protocol = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout)
        self._writer = asyncio.StreamWriter(transport, protocol, None, loop)

    async def readline(self) -> str | None:
        if self._reader is None:
            await self._open()
        data = await self._reader.readline()  # type: ignore[union-attr]
        return data.decode("utf-8") if data else None

    async def write(self, line: str) -> None:
        if self._writer is None:
            await self._open()
        self._writer.write(line.encode("utf-8"))  # type: ignore[union-attr]
        await self._writer.drain()  # type: ignore[union-attr]


class _Request:
    def __init__(self, task: asyncio.Task[Any], doc: BridgeDocument):
        self.task, self.doc = task, doc


class CoreServer:
    def __init__(self, config: Config,
                 tools_factory: Callable[[], LegalToolsClient] | None = None,
                 llm_factory: Callable[[], Any] | None = None):
        self.config = config
        self._tools_factory = tools_factory or (
            lambda: LegalToolsClient.from_config(
                config.mcp_legal_it, timeout_s=config.limits.tool_timeout_s))
        self._tools: LegalToolsClient | None = None
        self._tools_lock = asyncio.Lock()
        self._llm_factory = llm_factory or (lambda: LLMClient(config.llm))
        self._llm: Any | None = None
        self._doc_sessions: dict[str, DocSession] = {}   # one session per doc_id (spec §6.8)
        self._transport: LineTransport | None = None
        self._write_lock = asyncio.Lock()
        self._hello_ok = False
        self._protocol_mismatch = False
        self._announced = False
        self._running: dict[str, _Request] = {}     # doc_id → request
        self._by_request: dict[str, _Request] = {}  # request_id → request

    # --- output --------------------------------------------------------------
    async def send(self, msg: Any) -> None:
        assert self._transport is not None
        async with self._write_lock:
            await self._transport.write(p.dump_line(msg))

    # --- tools ---------------------------------------------------------------
    async def _get_tools(self) -> LegalToolsClient:
        # Two documents can each run a command concurrently (the busy rule is per doc_id,
        # spec §5.2), so both could see self._tools is None and race to build a client.
        # The lock (double-checked) makes the lazy init happen at most once; without it
        # the loser's client is never closed (main.py finally only awaits self._tools),
        # leaking a second "uvx ... mcp-legal-it" subprocess in local mode (review finding 3).
        if self._tools is None:
            async with self._tools_lock:
                if self._tools is None:
                    client = self._tools_factory()
                    await client.__aenter__()
                    self._tools = client
        return self._tools

    def _get_llm(self) -> Any:
        """Lazy: an absent or invalid [llm] section must not stop the pipelines that need
        no model, and its LLMError must land on the request that asked for a model turn."""
        if self._llm is None:
            self._llm = self._llm_factory()
        return self._llm

    def _session(self, doc_id: str) -> DocSession:
        session = self._doc_sessions.get(doc_id)
        if session is None:
            session = self._doc_sessions[doc_id] = DocSession(doc_id)
        return session

    async def _announce(self, request_id: str, tools: LegalToolsClient) -> None:
        if not self._announced:
            self._announced = True
            await self.send(p.Status(
                request_id=request_id, text=f"mcp-legal-it {tools.server_version} collegato"))

    async def _agent_deps(self, request_id: str, doc: BridgeDocument, profile: str) -> AgentDeps:
        llm = self._get_llm()          # LLMError from here is reported by _guarded
        tools: LegalToolsClient | None = None
        specs: list[ToolSpec] = []
        try:
            tools = await self._get_tools()
            specs = await tools.tool_specs()
        except Exception:
            # Unreachable or incompatible: a model turn is still worth running, only
            # without legal tools (the panel is told, and the profile keeps the document
            # and internal tools).
            tools = None
            await self.send(p.Status(request_id=request_id, text=NO_LEGAL_TOOLS_STATUS))
        else:
            await self._announce(request_id, tools)
        endpoint = getattr(llm, "endpoint", None)
        host = getattr(endpoint, "host", "") or getattr(llm, "host", "")
        return AgentDeps(llm, tools, doc, ToolRegistry(specs, profile), self.config.limits,
                         doc.ask_consent, host, getattr(llm, "model", self.config.llm.model),
                         self.config.llm.zero_data_retention)

    async def _prepare_turn(self, request_id: str, doc_id: str, doc: BridgeDocument,
                            profile: str) -> tuple[DocSession, AgentDeps]:
        """Session, ceiling check and dependencies shared by chat and research."""
        session = self._session(doc_id)
        check_ceiling(session, self.config.limits.session_token_ceiling)
        return session, await self._agent_deps(request_id, doc, profile)

    async def _send_turn_final(self, request_id: str, session: DocSession,
                               outcome: TurnOutcome) -> None:
        await self.send(p.Final(
            request_id=request_id, text=outcome.text, usage=outcome.usage,
            summary={"stopped": outcome.stopped, "inserted": outcome.inserted,
                     "flagged": outcome.flagged, "tool_calls": outcome.tool_calls,
                     "usage_totals": session.usage.model_dump()}))

    # --- main loop -----------------------------------------------------------
    async def run(self, transport: LineTransport) -> None:
        self._transport = transport
        try:
            while True:
                line = await transport.readline()
                if line is None:
                    break
                if not line.strip():
                    continue
                try:
                    msg = p.parse_extension_line(line)
                except ValidationError as e:
                    detail = e.errors()[0]["msg"]
                    await self.send(
                        p.Error(code="protocol", message=f"messaggio non valido: {detail}"))
                    continue
                if isinstance(msg, p.Shutdown):
                    break
                await self._dispatch(msg)
        finally:
            for req in list(self._by_request.values()):
                req.task.cancel()
            if self._tools is not None:
                await self._tools.__aexit__(None, None, None)
                self._tools = None

    async def _dispatch(self, msg: p.ExtensionMessage) -> None:
        if isinstance(msg, p.Hello):
            warnings: list[str] = []
            if msg.protocol != PROTOCOL_VERSION:
                self._protocol_mismatch = True
                warnings.append(
                    f"protocol {msg.protocol} not supported, core speaks {PROTOCOL_VERSION}")
            if not msg.has_markdown_filter:
                warnings.append(
                    "LibreOffice senza filtro Markdown: l'inserimento di testo non funzionerà")
            self._hello_ok = True
            await self.send(p.HelloOk(core_version=__version__, protocol=PROTOCOL_VERSION,
                                      mcp_server_version=None, warnings=warnings))
            return
        if not self._hello_ok or self._protocol_mismatch:
            await self.send(p.Error(
                request_id=getattr(msg, "id", None), code="protocol",
                message="handshake mancante o versione di protocollo incompatibile"))
            return
        if isinstance(msg, p.DocResult):
            req = self._by_request.get(msg.id)
            if req is not None:
                req.doc.resolve(msg)
            return
        if isinstance(msg, p.ConsentResult):
            req = self._by_request.get(msg.id)
            if req is not None:
                req.doc.resolve_consent(msg)
            return
        if isinstance(msg, p.Cancel):
            req = self._running.get(msg.doc_id)
            if req is not None:
                req.task.cancel()
            return
        if isinstance(msg, p.Chat | p.Command):
            if msg.doc_id in self._running:
                await self.send(p.Error(
                    request_id=msg.id, code="busy",
                    message="un'altra richiesta è in corso su questo documento"))
                return
            doc = BridgeDocument(self.send, request_id=msg.id)
            body = (self._run_chat(msg, doc) if isinstance(msg, p.Chat)
                    else self._run_command(msg, doc))
            task = asyncio.create_task(body)
            req = _Request(task, doc)
            self._running[msg.doc_id] = req
            self._by_request[msg.id] = req
            task.add_done_callback(lambda _t, d=msg.doc_id, r=msg.id: (
                self._running.pop(d, None), self._by_request.pop(r, None)))

    async def _run_chat(self, msg: p.Chat, doc: BridgeDocument) -> None:
        await self._guarded(msg.id, self._chat_body(msg, doc))

    async def _run_command(self, msg: p.Command, doc: BridgeDocument) -> None:
        await self._guarded(msg.id, self._command_body(msg, doc))

    async def _guarded(self, request_id: str, body: Awaitable[None]) -> None:
        """Every failure of a request becomes one message, and never kills the server."""
        try:
            await body
        except asyncio.CancelledError:
            await self.send(p.Final(request_id=request_id, text="Annullato.", cancelled=True))
        except LLMError as e:
            await self.send(p.Error(request_id=request_id, code=e.code, message=str(e)))
        except LimitReached as e:
            await self.send(p.Error(request_id=request_id, code="limit", message=str(e)))
        except UnparsedReference as e:
            await self.send(
                p.Error(request_id=request_id, code="reference_unparsed", message=str(e)))
        except TextUnavailable as e:
            await self.send(p.Error(request_id=request_id, code="text_unavailable",
                                    message=str(e)))
        except DocumentError as e:
            await self.send(p.Error(request_id=request_id, code="document", message=str(e)))
        except Exception as e:  # never let a request kill the server
            await self.send(p.Error(
                request_id=request_id, code="internal", message=f"{type(e).__name__}: {e}"))

    async def _chat_body(self, msg: p.Chat, doc: BridgeDocument) -> None:
        session, deps = await self._prepare_turn(msg.id, msg.doc_id, doc, CHAT_PROFILE)
        outcome = await run_chat(session, msg.message, msg.context, deps, self.send, msg.id)
        await self._send_turn_final(msg.id, session, outcome)

    async def _command_body(self, msg: p.Command, doc: BridgeDocument) -> None:
        async def emit(m: Any) -> None:
            await self.send(m)

        if msg.name in NOT_IMPLEMENTED:
            await self.send(p.Error(
                request_id=msg.id, code="not_implemented",
                message=f"comando {msg.name} non disponibile in questa versione"))
            return
        if msg.name == "research":
            session, deps = await self._prepare_turn(msg.id, msg.doc_id, doc, RESEARCH_PROFILE)
            outcome = await run_research(session, msg.args.get("question"), deps,
                                         self.send, msg.id)
            await self._send_turn_final(msg.id, session, outcome)
            return
        tools: LegalToolsClient | None = None
        if msg.name in NEEDS_TOOLS:
            try:
                tools = await self._get_tools()
            except IncompatibleServer as e:
                await self.send(
                    p.Error(request_id=msg.id, code="mcp_incompatible", message=str(e)))
                return
            except Exception as e:
                await self.send(p.Error(request_id=msg.id, code="mcp_unavailable",
                                        message=f"mcp-legal-it non raggiungibile: {e}"))
                return
            await self._announce(msg.id, tools)
        scope = "selection" if msg.args.get("scope") == "selection" else "document"
        if msg.name == "verify_citations":
            summary = await run_verify(doc, tools, scope, emit, msg.id,
                                       include_footnotes=self.config.document.verify_footnotes)
            text = (f"Verificate {summary['citazioni_uniche']} citazioni, "
                    f"{summary['commenti_inseriti']} segnalazioni inserite.")
            await self.send(p.Final(request_id=msg.id, text=text, summary=summary))
        elif msg.name == "list_citations":
            out = await run_list_citations(
                doc, scope, emit, msg.id,
                include_footnotes=self.config.document.verify_footnotes)
            text = (f"Trovate {out['citazioni_uniche']} citazioni "
                    f"({out['citazioni_totali']} occorrenze).")
            await self.send(p.Final(request_id=msg.id, summary=out, text=text))
        elif msg.name == "show_text":
            out = await run_show_text(doc, tools, msg.args.get("reference"), emit, msg.id)
            await self.send(p.Final(
                request_id=msg.id, text=f"Testo di {out['riferimento']}.", summary=out))
        elif msg.name == "insert_norm":
            author = "LibreLex" if self.config.document.redline_author == "librelex" else None
            out = await run_insert_norm(doc, tools, msg.args.get("reference"), emit, msg.id,
                                        author=author)
            await self.send(p.Final(
                request_id=msg.id, text=f"Inserito {out['riferimento']}.", summary=out))
        else:   # a name accepted by the protocol but not routed here
            await self.send(p.Error(
                request_id=msg.id, code="not_implemented",
                message=f"comando {msg.name} non disponibile in questa versione"))


def main() -> None:
    config = load_config()
    asyncio.run(CoreServer(config).run(StdioTransport()))


if __name__ == "__main__":  # pragma: no cover
    main()
