# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import asyncio

import pytest

from librelex_core import protocol as p
from librelex_core.document import BridgeDocument, DocumentError, FakeDocument


async def test_fake_read_paragraphs_with_footnotes():
    doc = FakeDocument(["Primo art. 2043 c.c.", "Secondo"], footnotes={0: "Cass. n. 1/2024"})
    paras = await doc.read_paragraphs()
    assert [x.id for x in paras] == ["p:0", "fn:1/p:0", "p:1"]
    assert paras[1].kind == "footnote" and paras[1].text == "Cass. n. 1/2024"
    assert (await doc.info()).paragraph_count == 2


async def test_fake_selection_and_find():
    doc = FakeDocument(["abc art. 5 c.p. def"], selection=(0, 4, 15))
    sel = await doc.read_selection()
    assert sel.text == "art. 5 c.p." and sel.anchor.start == 4
    occ = await doc.find_text("c.p.")
    assert (occ[0].anchor.paragraph_id == "p:0" and occ[0].anchor.start == 11
            and occ[0].text == "c.p.")


async def test_fake_add_comment_anchoring():
    doc = FakeDocument(["Vedi art. 2043 c.c. qui."])
    exact = await doc.add_comment("p:0", 5, 19, "art. 2043 c.c.", "LibreLex · verifica", "x")
    assert exact.anchored == "exact"
    found = await doc.add_comment("p:0", 0, 3, "art. 2043 c.c.", "LibreLex · verifica", "y")
    assert found.anchored == "found" and doc.comments[-1]["start"] == 5
    start = await doc.add_comment("p:0", 0, 3, "non presente", "LibreLex · verifica", "z")
    assert start.anchored == "paragraph_start" and doc.comments[-1]["start"] == 0
    assert await doc.remove_comments("LibreLex · verifica") == 3 and doc.comments == []


async def test_fake_insert_records_bookmark():
    doc = FakeDocument(["a"])
    rng = await doc.insert_markdown(
        "cursor", "# T\n\ntesto", "LibreLex: test", bookmark="LibreLex.norma.x"
    )
    assert rng.from_id == "p:1" and "LibreLex.norma.x" in doc.bookmarks
    assert doc.inserts[0]["markdown"].startswith("# T")


async def test_bridge_roundtrip():
    sent: list[p.DocCall] = []

    async def send(call: p.DocCall) -> None:
        sent.append(call)

    doc = BridgeDocument(send, request_id="r9", timeout_s=1)
    task = asyncio.create_task(doc.read_paragraphs(0, 1))
    await asyncio.sleep(0)
    call = sent[0]
    assert (call.action == "read_paragraphs" and call.args == {"from_": 0, "to": 1}
            and call.request_id == "r9")
    doc.resolve(p.DocResult(
        id="r9", call_id=call.call_id, ok=True,
        result={"paragraphs": [{"id": "p:0", "text": "x", "style": "", "kind": "body"}]},
    ))
    paras = await task
    assert paras[0].text == "x"


async def test_bridge_error_and_timeout():
    async def send(call: p.DocCall) -> None:
        pass

    doc = BridgeDocument(send, request_id="r", timeout_s=0.05)
    with pytest.raises(DocumentError, match="timeout"):
        await doc.info()
    task = asyncio.create_task(doc.remove_comments("a"))
    await asyncio.sleep(0)
    call_id = next(iter(doc.pending))
    doc.resolve(p.DocResult(id="r", call_id=call_id, ok=False, error="no doc"))
    with pytest.raises(DocumentError, match="no doc"):
        await task
