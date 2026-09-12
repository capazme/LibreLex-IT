# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
from librelex_core.agent.grounding import Grounding, comment_problems, verify_unseen
from librelex_core.citations.verifier import Verdict
from librelex_core.document import FakeDocument, InsertedRange
from librelex_core.mcp.client import LegalToolsClient
from tests.conftest import make_fake_legal_server


def test_seen_and_unseen_references():
    g = Grounding()
    g.record("Sentenza Cass. sez. III n. 12345/2024 ... art. 2043 c.c.")
    assert g.seen == {"Cass. sez. III n. 12345/2024", "art. 2043 c.c."}
    md = "Come da art. 2043 c.c. e Cass. n. 99999/2024; vedi anche Corte cost. n. 1/2020 e art. 5."
    # Consulta not verifiable, art. 5 no canonical of its own
    assert g.unseen(md) == ["Cass. n. 99999/2024"]


async def test_verify_unseen_and_comment_problems():
    server, calls = make_fake_legal_server(verdicts={"Cass. n. 99999/2024": ("inesistente", "no")})
    async with LegalToolsClient(server) as tools:
        verdicts = await verify_unseen(["Cass. n. 99999/2024", "art. 2043 c.c."], tools)
    assert verdicts["Cass. n. 99999/2024"].verdetto == "inesistente"
    doc = FakeDocument(["intro", "Testo con Cass. n. 99999/2024 e art. 2043 c.c.", "coda"])
    flagged = await comment_problems(doc, InsertedRange(from_id="p:1", to_id="p:1"), verdicts)
    assert flagged == ["Cass. n. 99999/2024"]
    assert len(doc.comments) == 1 and doc.comments[0]["author"] == "LibreLex · verifica"
    assert doc.comments[0]["paragraph_id"] == "p:1" and doc.comments[0]["anchored"] == "exact"
    assert await comment_problems(doc, InsertedRange(from_id="fn:1/p:0", to_id="fn:1/p:0"),
                                  {"x": Verdict("x", "inesistente", "")}) == []
