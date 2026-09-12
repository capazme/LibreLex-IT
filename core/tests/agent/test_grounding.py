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
    # Consulta not verifiable; "art. 5" is verified as art. 5 c.c. (the act the model wrote
    # earlier in this same markdown), never as "art. 5 Cost.": that act only looks like one
    # because it sits inside a judgment citation (review finding 2).
    assert g.unseen(md) == ["Cass. n. 99999/2024", "art. 5 c.c."]


def test_bare_articles_chained_to_an_act_of_the_same_markdown_are_verified():
    """Spec §6.6: an invented article cannot reach the document by sharing the act of a
    real one, which is how Italian drafting cites several articles at once."""
    g = Grounding()
    g.record("art. 2043 c.c.")
    assert g.unseen("Ai sensi degli artt. 2043 e 999999 c.c. sorge l'obbligo.") == [
        "art. 999999 c.c."]
    md = "Vale l'art. 2043 c.c.\n\nRileva poi l'art. 999999 dello stesso codice."
    assert g.unseen(md) == ["art. 999999 c.c."]


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
