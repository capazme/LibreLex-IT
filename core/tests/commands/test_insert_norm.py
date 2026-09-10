# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
from datetime import date

import pytest

from librelex_core.commands.insert_norm import (
    UnparsedReference,
    bookmark_name,
    format_norm_markdown,
    parse_reference,
    run_insert_norm,
)
from librelex_core.document import FakeDocument
from librelex_core.mcp.client import LegalToolsClient
from tests.conftest import ARTICLE_2043, make_fake_legal_server


def test_parse_reference():
    assert parse_reference("art. 2043 c.c.") == "art. 2043 c.c."
    assert (parse_reference("  Art. 13, comma 7, d.lgs. 196/2003 ")
            == "art. 13 co. 7 D.Lgs. 196/2003")
    with pytest.raises(UnparsedReference, match="non interpretabile"):
        parse_reference("qualcosa di vago")
    with pytest.raises(UnparsedReference, match="un solo riferimento"):
        parse_reference("art. 1 c.c. e art. 2 c.c.")


def test_bookmark_name():
    url = "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:regio.decreto:1942-03-16;262:2~art2043"
    assert bookmark_name(url).startswith("LibreLex.norma.https_www_normattiva_it")
    assert len(bookmark_name("x" * 500)) <= len("LibreLex.norma.") + 80


def test_format_markdown():
    md = format_norm_markdown(ARTICLE_2043, date(2026, 9, 7))
    assert md.startswith("**Art. 2043 c.c.**\n\n> Qualunque fatto doloso")
    assert md.rstrip().endswith("*Testo vigente al 7 settembre 2026, fonte Normattiva, "
                                + ARTICLE_2043["url"] + "*")


async def test_run_insert_norm_from_argument():
    doc = FakeDocument(["testo"])
    server, calls = make_fake_legal_server()
    events = []

    async def emit(m):
        events.append(m)

    async with LegalToolsClient(server) as tools:
        out = await run_insert_norm(doc, tools, "art. 2043 c.c.", emit, "r1")
    assert calls["cite"] == ["art. 2043 c.c."]
    assert doc.inserts[0]["where"] == "cursor"
    assert doc.inserts[0]["undo_label"] == "LibreLex: inserisci art. 2043 c.c."
    assert doc.inserts[0]["bookmark"] == out["bookmark"] and out["bookmark"] in doc.bookmarks
    assert out["inserted"] == {"from_id": "p:1", "to_id": "p:3"}


async def test_run_insert_norm_from_selection():
    doc = FakeDocument(["vedi art. 2043 c.c. qui"], selection=(0, 5, 19))
    server, calls = make_fake_legal_server()

    async def emit(m):
        pass

    async with LegalToolsClient(server) as tools:
        await run_insert_norm(doc, tools, None, emit, "r1")
    assert calls["cite"] == ["art. 2043 c.c."]


async def test_run_insert_norm_unknown_act_raises():
    doc = FakeDocument(["x"])
    server, _ = make_fake_legal_server(articles={})

    async def emit(m):
        pass

    async with LegalToolsClient(server) as tools:
        with pytest.raises(UnparsedReference, match="non riconosciuto"):
            await run_insert_norm(doc, tools, "art. 2043 c.c.", emit, "r1")
    assert doc.inserts == []
