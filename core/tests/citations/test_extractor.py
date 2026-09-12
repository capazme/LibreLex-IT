# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
from librelex_core.citations.extractor import extract_all, group_by_canonical
from librelex_core.document import Paragraph


def P(i, text, kind="body"):
    return Paragraph(id=f"p:{i}" if kind == "body" else f"fn:{i}/p:0", text=text, kind=kind)


def test_mixed_document():
    paras = [
        P(0, "Ai sensi dell'art. 2043 c.c. e di Cass. sez. III n. 12345/2024."),
        P(1, "Vedi art. 2043 c.c. e Corte cost. n. 1/2000."),
        P(1, "Cfr. Cass. n. 999/2021.", kind="footnote"),
    ]
    cs = extract_all(paras)
    assert [(c.kind, c.paragraph_id, c.canonical) for c in cs] == [
        ("norma", "p:0", "art. 2043 c.c."),
        ("sentenza", "p:0", "Cass. sez. III n. 12345/2024"),
        ("norma", "p:1", "art. 2043 c.c."),
        ("sentenza", "p:1", "Corte cost. n. 1/2000"),
        ("sentenza", "fn:1/p:0", "Cass. n. 999/2021"),
    ]
    assert [c.verifiable for c in cs] == [True, True, True, False, True]
    grouped = group_by_canonical(cs)
    assert list(grouped) == [
        "art. 2043 c.c.",
        "Cass. sez. III n. 12345/2024",
        "Corte cost. n. 1/2000",
        "Cass. n. 999/2021",
    ]
    assert len(grouped["art. 2043 c.c."]) == 2


def test_context_carries_across_body_paragraphs_not_from_footnotes():
    paras = [
        P(0, "Il D.Lgs. 196/2003 dispone."),
        P(1, "L'art. 4 prevede."),
        P(1, "Nota: legge 241/1990.", kind="footnote"),
        P(2, "E l'art. 5 aggiunge."),
    ]
    cs = [c for c in extract_all(paras) if c.kind == "norma" and c.canonical]
    assert [c.canonical for c in cs] == ["art. 4 D.Lgs. 196/2003", "art. 5 D.Lgs. 196/2003"]


def test_bare_cds_does_not_swallow_the_norm():
    # "art. 5 c.d.s. n. 285/1992" is a norm citation (codice della strada); before the
    # fix, judgments matched "c.d.s." as Consiglio di Stato and won the overlap, so the
    # norm was silently dropped (review finding 5).
    paras = [P(0, "Violazione dell'art. 5 c.d.s. n. 285/1992.")]
    cs = extract_all(paras)
    assert [(c.kind, c.canonical) for c in cs] == [("norma", "art. 5 codice della strada")]


def test_offsets_are_paragraph_relative():
    paras = [P(0, "xx art. 1 c.p. yy"), P(1, "Cass. n. 1/2020")]
    cs = extract_all(paras)
    assert paras[0].text[cs[0].start:cs[0].end] == cs[0].display_text
    assert paras[1].text[cs[1].start:cs[1].end] == cs[1].display_text


def test_judgment_fields_are_exposed_on_the_unified_citation():
    from librelex_core.document import Paragraph
    cits = extract_all([Paragraph(id="p:0", text="Cass. sez. lav. n. 123/2021 e art. 2043 c.c.")])
    sent = [c for c in cits if c.kind == "sentenza"][0]
    assert (sent.number, sent.year, sent.section) == ("123", "2021", "lav.")
    norm = [c for c in cits if c.kind == "norma"][0]
    assert (norm.number, norm.year, norm.section) == (None, None, None)


def test_a_judgment_span_never_becomes_the_act_context_of_the_articles_that_follow():
    # "Corte cost. n. 1/2020" is a judgment; the norm pass must not read "cost. n. 1/2020"
    # as the Costituzione and hand it to the bare articles that follow (task 4 finding 2).
    paras = [P(0, "Vedi Corte cost. n. 1/2020 e art. 5."), P(1, "Anche l'art. 6 rileva.")]
    assert [(c.kind, c.canonical) for c in extract_all(paras)] == [
        ("sentenza", "Corte cost. n. 1/2020"), ("norma", None), ("norma", None)]
