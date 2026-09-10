# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import asyncio

from librelex_core import PROTOCOL_VERSION, __version__
from librelex_core import protocol as p
from librelex_core.config import Config
from librelex_core.document import FakeDocument
from librelex_core.main import CoreServer, MemoryTransport
from librelex_core.mcp.client import LegalToolsClient
from tests.conftest import make_fake_legal_server


class Harness:
    """Plays the extension: sends lines, answers doc_calls with a FakeDocument."""

    def __init__(self, doc: FakeDocument, server_version="2.14.0", verdicts=None):
        self.doc = doc
        self.inbox: asyncio.Queue[str | None] = asyncio.Queue()
        self.outbox: asyncio.Queue[str] = asyncio.Queue()
        fake, self.calls = make_fake_legal_server(version=server_version, verdicts=verdicts)
        self.server = CoreServer(Config(), tools_factory=lambda: LegalToolsClient(fake))
        self.received: list = []
        self.hold = False  # when True, doc_calls are left unanswered (keeps a request pending)

    async def send(self, msg) -> None:
        await self.inbox.put(p.dump_line(msg))

    async def pump(self, until: type) -> None:
        """Read core messages, serving doc_calls, until a message of type `until` arrives."""
        while True:
            line = await asyncio.wait_for(self.outbox.get(), 5)
            msg = p.parse_core_line(line)
            self.received.append(msg)
            if isinstance(msg, p.DocCall) and not self.hold:
                await self._serve(msg)
            if isinstance(msg, until):
                return

    async def _serve(self, call: p.DocCall) -> None:
        method = {"get_document_info": "info"}.get(call.action, call.action)
        try:
            res = await getattr(self.doc, method)(**call.args)
            if call.action == "read_paragraphs":
                result = {"paragraphs": [x.model_dump() for x in res]}
            elif call.action == "find_text":
                result = {"occurrences": [x.model_dump() for x in res]}
            elif call.action == "remove_comments":
                result = {"count": res}
            elif call.action == "goto":
                result = {}
            else:
                result = res.model_dump()
            await self.send(
                p.DocResult(id=call.request_id, call_id=call.call_id, ok=True, result=result))
        except Exception as e:
            await self.send(
                p.DocResult(id=call.request_id, call_id=call.call_id, ok=False, error=str(e)))

    async def run(self, scenario):
        task = asyncio.create_task(self.server.run(MemoryTransport(self.inbox, self.outbox)))
        try:
            await scenario(self)
        finally:
            await self.send(p.Shutdown())
            await asyncio.wait_for(task, 5)


HELLO = p.Hello(id="h", protocol=PROTOCOL_VERSION, extension_version="0.1.0", lo_version="26.8",
                has_markdown_filter=True)


async def test_hello_then_verify_roundtrip():
    doc = FakeDocument(["Vedi art. 2043 c.c. e Cass. n. 99999/2024."])
    h = Harness(doc, verdicts={"Cass. n. 99999/2024": ("inesistente", "no")})

    async def scenario(h: Harness):
        await h.send(HELLO)
        await h.pump(p.HelloOk)
        ok = h.received[-1]
        assert ok.core_version == __version__
        assert ok.protocol == PROTOCOL_VERSION and ok.warnings == []
        await h.send(
            p.Command(id="r1", doc_id="d1", name="verify_citations", args={"scope": "document"}))
        await h.pump(p.Final)
        final = h.received[-1]
        assert final.request_id == "r1" and final.summary["commenti_inseriti"] == 1
        assert len(doc.comments) == 1

    await h.run(scenario)


async def test_command_before_hello_is_protocol_error():
    h = Harness(FakeDocument(["x"]))

    async def scenario(h: Harness):
        await h.send(p.Command(id="r1", doc_id="d1", name="insert_norm"))
        await h.pump(p.Error)
        assert h.received[-1].code == "protocol"

    await h.run(scenario)


async def test_busy_and_cancel():
    doc = FakeDocument(["art. 2043 c.c."])
    h = Harness(doc)

    async def scenario(h: Harness):
        await h.send(HELLO)
        await h.pump(p.HelloOk)
        h.hold = True                      # leave r1 waiting on its first doc_call
        await h.send(p.Command(id="r1", doc_id="d1", name="verify_citations"))
        await h.pump(p.DocCall)            # r1 is now waiting on the document
        await h.send(p.Command(id="r2", doc_id="d1", name="verify_citations"))
        await h.pump(p.Error)
        assert h.received[-1].code == "busy" and h.received[-1].request_id == "r2"
        await h.send(p.Cancel(id="r1", doc_id="d1"))
        await h.pump(p.Final)
        assert h.received[-1].cancelled is True and h.received[-1].request_id == "r1"

    await h.run(scenario)


async def test_incompatible_server_is_reported():
    h = Harness(FakeDocument(["x"]), server_version="2.13.0")

    async def scenario(h: Harness):
        await h.send(HELLO)
        await h.pump(p.HelloOk)
        await h.send(p.Command(
            id="r1", doc_id="d1", name="insert_norm", args={"reference": "art. 2043 c.c."}))
        await h.pump(p.Error)
        assert h.received[-1].code == "mcp_incompatible" and "2.14.0" in h.received[-1].message

    await h.run(scenario)


async def test_not_implemented_and_unparsed_reference():
    h = Harness(FakeDocument(["x"]))

    async def scenario(h: Harness):
        await h.send(HELLO)
        await h.pump(p.HelloOk)
        await h.send(p.Command(id="r1", doc_id="d1", name="research"))
        await h.pump(p.Error)
        assert h.received[-1].code == "not_implemented"
        await h.send(p.Command(id="r2", doc_id="d1", name="insert_norm", args={"reference": "boh"}))
        await h.pump(p.Error)
        assert h.received[-1].code == "reference_unparsed"

    await h.run(scenario)


async def test_malformed_line_is_reported_not_fatal():
    h = Harness(FakeDocument(["x"]))

    async def scenario(h: Harness):
        await h.inbox.put("this is not json\n")
        await h.pump(p.Error)
        assert h.received[-1].code == "protocol"
        await h.send(HELLO)
        await h.pump(p.HelloOk)

    await h.run(scenario)
