# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
from librelex_core import protocol as p
from librelex_core.commands.verify_document import COMMENT_AUTHOR, run_verify
from librelex_core.document import FakeDocument
from librelex_core.mcp.client import LegalToolsClient
from tests.conftest import make_fake_legal_server

TEXT = [
    "Premesso l'art. 7, ai sensi dell'art. 2043 c.c. e di Cass. sez. III n. 12345/2024 "
    "il danno va risarcito.",
    "Come ribadito da Cass. n. 99999/2024 e dall'art. 13 co. 7 D.Lgs. 196/2003; "
    "vedi anche art. 2043 c.c.",
    "Sul punto Corte cost. n. 1/2000.",
]
VERDICTS = {
    "Cass. n. 99999/2024": (
        "inesistente", "Decisione n. 99999/2024 non trovata negli archivi della Cassazione."
    ),
    "art. 13 co. 7 D.Lgs. 196/2003": (
        "metadati discordanti", "Comma/lettera citato non riscontrato."
    ),
}


async def _run(doc, scope="document"):
    server, calls = make_fake_legal_server(verdicts=VERDICTS)
    events = []

    async def emit(msg):
        events.append(msg)

    async with LegalToolsClient(server) as tools:
        summary = await run_verify(doc, tools, scope, emit, request_id="r1")
    return summary, events, calls


async def test_comments_only_on_problems_and_summary():
    doc = FakeDocument(TEXT, footnotes={0: "Cfr. Cass. n. 777/2023."})
    summary, events, calls = await _run(doc)
    authors = {c["author"] for c in doc.comments}
    assert authors == {COMMENT_AUTHOR}
    flagged = sorted((c["paragraph_id"], c["start"]) for c in doc.comments)
    assert flagged == [("p:1", 17), ("p:1", 44)]
    assert all(c["anchored"] == "exact" for c in doc.comments)
    assert "non risulta nelle fonti ufficiali" in doc.comments[0]["text"]
    assert summary["citazioni_totali"] == 8 and summary["citazioni_uniche"] == 6
    assert summary["per_verdetto"] == {"verificata": 3, "inesistente": 1, "metadati discordanti": 1}
    assert summary["da_controllare_a_mano"] == ["Corte cost. n. 1/2000"]
    assert summary["non_interpretabili"] == ["art. 7"]
    assert summary["commenti_inseriti"] == 2
    assert [m.text for m in events if isinstance(m, p.Status)][0].startswith("Leggo")
    assert any(isinstance(m, p.Progress) and m.done == m.total == 5 for m in events)
    assert sorted(calls["verifica"][0]) == sorted([
        "art. 2043 c.c.", "Cass. sez. III n. 12345/2024", "Cass. n. 777/2023",
        "Cass. n. 99999/2024", "art. 13 co. 7 D.Lgs. 196/2003",
    ])


async def test_rerun_is_idempotent():
    doc = FakeDocument(TEXT)
    await _run(doc)
    await _run(doc)
    assert len(doc.comments) == 2


async def test_selection_scope():
    doc = FakeDocument(TEXT, selection=(1, 0, len(TEXT[1])))
    summary, _, calls = await _run(doc, scope="selection")
    assert summary["scope"] == "selection" and summary["citazioni_totali"] == 3
    assert "art. 2043 c.c." in calls["verifica"][0]


async def test_selection_reads_once():
    doc = FakeDocument(TEXT, selection=(1, 0, len(TEXT[1])))
    calls: list[int] = []
    orig = doc.read_selection

    async def spy():
        calls.append(1)
        return await orig()

    doc.read_selection = spy
    await _run(doc, scope="selection")
    assert len(calls) == 1


async def test_summary_lists_unverifiable_and_retry():
    server, calls = make_fake_legal_server(verdicts={
        "Cass. n. 5000/2015": ("non verificabile", "fuori archivio"),
        "art. 2043 c.c.": ("non verificata", "fonte irraggiungibile"),
    })
    doc = FakeDocument(["Cass. n. 5000/2015 e art. 2043 c.c."])
    events = []

    async def emit(msg):
        events.append(msg)

    async with LegalToolsClient(server) as tools:
        summary = await run_verify(doc, tools, "document", emit, request_id="r1")

    assert summary["non_verificabili"] == ["Cass. n. 5000/2015"]
    assert summary["da_riprovare"] == ["art. 2043 c.c."]
    assert doc.comments == []
    assert summary["per_verdetto"] == {"non verificabile": 1, "non verificata": 1}


async def test_footnotes_can_be_excluded():
    doc = FakeDocument(TEXT[:1], footnotes={0: "Cass. n. 777/2023"})
    server, calls = make_fake_legal_server()

    async def emit(msg):
        pass

    async with LegalToolsClient(server) as tools:
        await run_verify(doc, tools, "document", emit, "r", include_footnotes=False)
    assert "Cass. n. 777/2023" not in calls["verifica"][0]
