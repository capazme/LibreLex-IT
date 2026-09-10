# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import pytest

from librelex_core.citations.norms import expand_year, extract_norms

CASES = [
    ("Ai sensi dell'art. 2043 c.c. il danno", ["art. 2043 c.c."]),
    ("ex artt. 1218 c.c.", ["art. 1218 c.c."]),
    ("l'art. 13, comma 7, del d.lgs. 196/2003 prevede", ["art. 13 co. 7 D.Lgs. 196/2003"]),
    ("art. 5 del D.Lgs. n. 231/2001", ["art. 5 D.Lgs. 231/2001"]),
    ("l'articolo 2-bis della legge 241/1990", ["art. 2-bis L. 241/1990"]),
    ("art. 6 GDPR e art. 4 n. 11 GDPR", ["art. 6 GDPR", "art. 4 GDPR"]),
    ("art. 13 regolamento (UE) 2016/679", ["art. 13 regolamento UE 2016/679"]),
    ("art. 111 Cost.", ["art. 111 Cost."]),
    ("art. 700 c.p.c. e art. 575 c.p.", ["art. 700 c.p.c.", "art. 575 c.p."]),
    ("vedi D.Lgs. 196/2003, art. 3 e art. 4", ["art. 3 D.Lgs. 196/2003", "art. 4 D.Lgs. 196/2003"]),
    ("art. 2 del D.L. 76/20", ["art. 2 D.L. 76/2020"]),
    ("art. 1 co. 2 lett. b) codice del consumo", ["art. 1 co. 2 codice del consumo"]),
]


@pytest.mark.parametrize("text,expected", CASES)
def test_canonical_forms(text, expected):
    got = [c.canonical() for c in extract_norms(text) if c.canonical()]
    assert got == expected


def test_offsets_map_back_to_text():
    text = "Come da art. 2043 c.c. e da art. 13 co. 7 del d.lgs. 196/2003."
    for c in extract_norms(text):
        assert text[c.start:c.end] == c.display_text


def test_no_overlaps_and_sorted():
    text = "art. 5 del d.lgs. 196/2003 e d.lgs. 196/2003 art. 6"
    cs = extract_norms(text)
    assert [c.start for c in cs] == sorted(c.start for c in cs)
    for a, b in zip(cs, cs[1:], strict=False):
        assert a.end <= b.start


def test_bare_article_without_context_has_no_canonical():
    cs = extract_norms("Si veda l'art. 5.")
    assert len(cs) == 1 and cs[0].article == "5" and cs[0].act is None and cs[0].canonical() is None


def test_standalone_act_without_article():
    cs = extract_norms("in forza del D.Lgs. 231/2001")
    assert cs[0].article is None and cs[0].act.label == "D.Lgs." and cs[0].canonical() is None


def test_dlgs_number_is_not_treated_as_article():
    cs = extract_norms("D.Lgs. 196/2003")
    assert len(cs) == 1 and cs[0].number == "196" and cs[0].year == "2003"


def test_expand_year():
    assert expand_year("20") == "2020"
    assert expand_year("98") == "1998"
    assert expand_year("2003") == "2003"


def test_huge_text_is_ignored():
    assert extract_norms("art. 1 c.c. " * 60_000) == []
