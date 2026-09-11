# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
from librelex_core.citations.extractor import Citation
from librelex_core.citations.verifier import verify, verify_citations
from librelex_core.mcp.client import LegalToolsClient
from tests.conftest import make_fake_legal_server


async def test_batches_of_20_and_progress():
    server, calls = make_fake_legal_server()
    refs = [f"art. {i} c.c." for i in range(1, 46)]  # 45 refs → 3 batches
    seen = []

    async def progress(done, total):
        seen.append((done, total))

    async with LegalToolsClient(server) as tools:
        verdicts = await verify_citations(refs, tools, progress=progress)
    assert len(verdicts) == 45 and all(v.verdetto == "verificata" for v in verdicts.values())
    assert [len(b) for b in calls["verifica"]] == [20, 20, 5]
    assert seen[-1] == (45, 45)


async def test_retry_once_on_non_verificata():
    server, calls = make_fake_legal_server(fail_first={"Cass. n. 1/2024"})
    async with LegalToolsClient(server) as tools:
        verdicts = await verify_citations(["art. 2043 c.c.", "Cass. n. 1/2024"], tools)
    assert verdicts["Cass. n. 1/2024"].verdetto == "verificata"
    assert calls["verifica"] == [["art. 2043 c.c.", "Cass. n. 1/2024"], ["Cass. n. 1/2024"]]


async def test_verdicts_pass_through():
    server, _ = make_fake_legal_server(verdicts={
        "Cass. n. 99999/2024": ("inesistente", "non trovata negli archivi"),
        "art. 13 co. 7 D.Lgs. 196/2003": ("metadati discordanti", "comma non riscontrato"),
    })
    async with LegalToolsClient(server) as tools:
        v = await verify_citations(["Cass. n. 99999/2024", "art. 13 co. 7 D.Lgs. 196/2003"], tools)
    assert v["Cass. n. 99999/2024"].verdetto == "inesistente"
    assert v["art. 13 co. 7 D.Lgs. 196/2003"].nota == "comma non riscontrato"


async def test_verify_splits_verifiable_and_others():
    server, calls = make_fake_legal_server()
    cits = [
        Citation("norma", "p:0", 0, 5, "art. 2043 c.c.", "art. 2043 c.c.", verifiable=True),
        Citation("sentenza", "p:0", 6, 9, "Corte cost. n. 1/2000", "Corte cost. n. 1/2000",
                 court="corte_costituzionale", verifiable=False),
        Citation("norma", "p:1", 0, 6, "art. 5", None, verifiable=False),
        Citation("norma", "p:2", 0, 5, "art. 2043 c.c.", "art. 2043 c.c.", verifiable=True),
    ]
    async with LegalToolsClient(server) as tools:
        report = await verify(cits, tools)
    assert list(report.verdicts) == ["art. 2043 c.c."]          # deduplicated
    assert report.unverified_courts == ["Corte cost. n. 1/2000"]
    assert report.unparsed == ["art. 5"]
    assert calls["verifica"] == [["art. 2043 c.c."]]
