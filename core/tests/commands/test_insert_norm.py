# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
from datetime import date

import pytest

from librelex_core.commands.insert_norm import (
    UnparsedReference,
    bookmark_name,
    format_norm_markdown,
    parse_reference,
    run_insert_norm,
    source_label,
    split_heading,
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
    # Truncation keeps the tail (see finding-7 test below), so the article discriminator
    # at the end of the slug must survive, not the host at the start.
    assert bookmark_name(url).endswith("art2043")
    assert len(bookmark_name("x" * 500)) <= len("LibreLex.norma.") + 80


def test_bookmark_name_keeps_the_article_discriminator_when_truncated():
    # art. 2043 and art. 2059 c.c. share the first 80 characters of the slugified URL;
    # truncating the head collides both bookmarks (review finding 7). The article
    # discriminator sits at the end of the URL, so truncation must keep the tail.
    url_2043 = ("https://www.normattiva.it/uri-res/N2Ls?"
                "urn:nir:stato:regio.decreto:1942-03-16;262:2~art2043")
    url_2059 = ("https://www.normattiva.it/uri-res/N2Ls?"
                "urn:nir:stato:regio.decreto:1942-03-16;262:2~art2059")
    assert bookmark_name(url_2043) != bookmark_name(url_2059)


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


async def test_run_insert_norm_bookmarks_differ_for_two_articles_of_the_same_act():
    # End-to-end version of test_bookmark_name_keeps_the_article_discriminator_when_truncated:
    # run_insert_norm must derive the bookmark from data["urn"] (or data["url"]) in a way
    # that survives truncation, otherwise the two documents' bookmarks collide (finding 7).
    prefix = "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:regio.decreto:1942-03-16;262:2"
    urn_2059 = "urn:nir:stato:regio.decreto:1942-03-16;262:2~art2059"
    article_2059 = {**ARTICLE_2043, "riferimento": "art. 2059 c.c.", "articolo": "2059",
                    "url": f"{prefix}~art2059", "urn": urn_2059}
    server, _ = make_fake_legal_server(
        articles={"art. 2043 c.c.": ARTICLE_2043, "art. 2059 c.c.": article_2059})

    async def emit(m):
        pass

    async with LegalToolsClient(server) as tools:
        out_2043 = await run_insert_norm(FakeDocument(["x"]), tools, "art. 2043 c.c.", emit, "r1")
        out_2059 = await run_insert_norm(FakeDocument(["x"]), tools, "art. 2059 c.c.", emit, "r2")
    assert out_2043["bookmark"] != out_2059["bookmark"]


def test_source_label_covers_akn_and_eurlex_variants():
    assert source_label("normattiva") == "Normattiva"
    assert source_label("normattiva-akn") == "Normattiva"
    assert source_label("eurlex") == "EUR-Lex"
    assert source_label("") == "fonte ufficiale"


def test_split_heading_strips_server_headings_and_keeps_rubrica():
    assert split_heading("### Art. 2043 - Risarcimento per fatto illecito\nQualunque fatto") == (
        "Risarcimento per fatto illecito", "Qualunque fatto")
    assert split_heading("Art. 2043.\n\nQualunque fatto") == (None, "Qualunque fatto")
    assert split_heading("Art. 2043 (Risarcimento per fatto illecito)\nQualunque") == (
        "Risarcimento per fatto illecito", "Qualunque")
    assert split_heading("Qualunque fatto") == (None, "Qualunque fatto")


def test_format_markdown_uses_rubrica_and_akn_label():
    data = {**ARTICLE_2043, "fonte": "normattiva-akn",
            "testo": "### Art. 2043 - Risarcimento per fatto illecito\n" + ARTICLE_2043["testo"]}
    md = format_norm_markdown(data, date(2026, 9, 7))
    assert md.startswith(
        "**Art. 2043 c.c. (Risarcimento per fatto illecito)**\n\n> Qualunque fatto")
    assert "### Art." not in md and "fonte Normattiva," in md


async def test_run_insert_norm_unknown_act_raises():
    doc = FakeDocument(["x"])
    server, _ = make_fake_legal_server(articles={})

    async def emit(m):
        pass

    async with LegalToolsClient(server) as tools:
        with pytest.raises(UnparsedReference, match="non riconosciuto"):
            await run_insert_norm(doc, tools, "art. 2043 c.c.", emit, "r1")
    assert doc.inserts == []
