# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import pytest

from librelex_core.commands.insert_norm import UnparsedReference
from librelex_core.commands.show_text import (
    MAX_TEXT_CHARS,
    TextUnavailable,
    extract_massima,
    parse_any,
    run_show_text,
    section_code,
    truncate,
)
from librelex_core.document import FakeDocument
from librelex_core.mcp.client import LegalToolsClient
from tests.conftest import ARTICLE_2043, make_fake_legal_server


async def _noop(m):
    pass


def test_section_code_and_truncate_and_massima():
    assert section_code(None) == "" and section_code("un.") == "SU"
    assert section_code("lav.") == "L" and section_code("trib.") == "T"
    assert section_code("III") == "3" and section_code("6") == "6" and section_code("VII") == "VII"
    short, cut = truncate("abc")
    assert (short, cut) == ("abc", False)
    long, cut = truncate("x" * (MAX_TEXT_CHARS + 10))
    assert cut is True and len(long) <= MAX_TEXT_CHARS + 10 and long.endswith("[…]")
    assert extract_massima("# T\n\n## Massima\n\nPrima riga.\nSeconda.\n\n## Testo\n\nfatti") == (
        "Prima riga.\nSeconda.")
    assert extract_massima("nessuna intestazione") is None


def test_parse_any_accepts_norms_and_judgments_but_one_at_a_time():
    assert parse_any(" Cass. sez. III n. 12345/2024 ").canonical == "Cass. sez. III n. 12345/2024"
    assert parse_any("art. 2043 c.c.").kind == "norma"
    with pytest.raises(UnparsedReference, match="non interpretabile"):
        parse_any("boh")
    with pytest.raises(UnparsedReference, match="un solo riferimento"):
        parse_any("art. 1 c.c. e art. 2 c.c.")


async def test_norm_text_with_rubrica_from_cite_law():
    server, calls = make_fake_legal_server(articles={"art. 2043 c.c.": {
        **ARTICLE_2043,
        "testo": "### Art. 2043 - Risarcimento per fatto illecito\nQualunque fatto doloso"}})
    async with LegalToolsClient(server) as tools:
        out = await run_show_text(FakeDocument(["x"]), tools, "art. 2043 c.c.", _noop, "r1")
    assert out["tipo"] == "norma" and out["riferimento"] == "art. 2043 c.c."
    assert out["titolo"] == "art. 2043 c.c. (Risarcimento per fatto illecito)"
    assert out["testo"] == "Qualunque fatto doloso" and out["massima"] is None
    assert out["fonte"] == "Normattiva" and out["url"].startswith("https://")
    assert out["troncato"] is False
    assert calls["cite"] == ["art. 2043 c.c."]


async def test_cassazione_massima_and_truncated_text():
    server, calls = make_fake_legal_server()
    async with LegalToolsClient(server) as tools:
        out = await run_show_text(
            FakeDocument(["x"]), tools, "Cass. sez. lav. n. 12345/2024", _noop, "r1")
    assert calls["sentenze"] == [(12345, 2024, "L")]
    assert out["tipo"] == "sentenza" and out["fonte"] == "Italgiure"
    assert out["massima"].startswith("Il datore di lavoro risponde")
    assert out["troncato"] is True and len(out["testo"]) <= MAX_TEXT_CHARS + 10


async def test_selection_fallback_consulta_and_unavailable_courts():
    server, calls = make_fake_legal_server()
    doc = FakeDocument(["vedi Corte cost. n. 1/2020 qui"], selection=(0, 5, 26))
    async with LegalToolsClient(server) as tools:
        out = await run_show_text(doc, tools, None, _noop, "r1")
        assert out["riferimento"] == "Corte cost. n. 1/2020" and calls["consulta"] == [(1, 2020)]
        assert out["fonte"] == "Corte costituzionale"
        with pytest.raises(TextUnavailable, match="non disponibile"):
            await run_show_text(FakeDocument(["x"]), tools, "TAR Lazio n. 100/2023", _noop, "r1")
        with pytest.raises(TextUnavailable, match="Errore"):
            await run_show_text(FakeDocument(["x"]), tools, "Cass. n. 1/2024", _noop, "r1")
        with pytest.raises(UnparsedReference, match="nessun riferimento"):
            await run_show_text(FakeDocument(["x"]), tools, "", _noop, "r1")
