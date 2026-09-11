# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
from librelex_core import protocol as p
from librelex_core.commands.list_citations import run_list_citations
from librelex_core.document import FakeDocument


async def test_lists_unique_citations_with_occurrences_and_unparsed():
    # "art. 5" comes before any act, so it inherits nothing and stays unparsed; the
    # footnote of paragraph 1 gets the fake's id fn:2/p:0.
    doc = FakeDocument(
        ["Si veda l'art. 5.", "Vedi art. 2043 c.c. e Cass. n. 12345/2024.",
         "Ancora art. 2043 c.c."],
        footnotes={1: "Corte cost. n. 1/2020"})
    events = []

    async def emit(m):
        events.append(m)

    out = await run_list_citations(doc, "document", emit, "r1")
    assert out["scope"] == "document"
    assert out["citazioni_totali"] == 5 and out["citazioni_uniche"] == 3
    by = {c["citazione"]: c for c in out["citazioni"]}
    assert list(by) == ["art. 2043 c.c.", "Cass. n. 12345/2024", "Corte cost. n. 1/2020"]
    assert by["art. 2043 c.c."]["tipo"] == "norma" and by["art. 2043 c.c."]["verificabile"] is True
    assert [o["paragraph_id"] for o in by["art. 2043 c.c."]["occorrenze"]] == ["p:1", "p:2"]
    assert by["Cass. n. 12345/2024"]["corte"] == "cassazione"
    assert by["Corte cost. n. 1/2020"]["verificabile"] is False
    assert by["Corte cost. n. 1/2020"]["occorrenze"][0]["paragraph_id"] == "fn:2/p:0"
    assert out["non_interpretabili"] == ["art. 5"]
    assert [m.text for m in events if isinstance(m, p.Status)] == [
        "Leggo il documento", "Trovate 3 citazioni (5 occorrenze)"]


async def test_selection_scope_offsets_and_no_footnotes():
    doc = FakeDocument(["xx art. 2043 c.c. yy"], footnotes={0: "Cass. n. 1/2024"},
                       selection=(0, 3, 17))

    async def emit(m):
        pass

    out = await run_list_citations(doc, "selection", emit, "r1")
    assert out["citazioni"][0]["occorrenze"] == [{"paragraph_id": "p:0", "start": 3, "end": 17}]
    out = await run_list_citations(doc, "document", emit, "r1", include_footnotes=False)
    assert [c["citazione"] for c in out["citazioni"]] == ["art. 2043 c.c."]
