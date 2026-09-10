# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import pytest

from librelex_core.citations.judgments import extract_judgments

CASES = [
    ("Cass. civ., sez. III, 12 marzo 2024, n. 12345", "Cass. sez. III n. 12345/2024"),
    ("Cass. 12345/2024", "Cass. n. 12345/2024"),
    ("Cass. n. 999 del 2021", "Cass. n. 999/2021"),
    ("Cassazione, Sezioni Unite, n. 8053/2014", "Cass. sez. un. n. 8053/2014"),
    ("Cass. SS.UU. 1234/2020", "Cass. sez. un. n. 1234/2020"),
    ("Cass. sez. lav. n. 100/2023", "Cass. sez. lav. n. 100/2023"),
    ("Cass. pen., sez. V, n. 4321/2022", "Cass. sez. V n. 4321/2022"),
    ("Corte cost. n. 170/1984", "Corte cost. n. 170/1984"),
    ("Corte costituzionale, sentenza n. 269 del 2017", "Corte cost. n. 269/2017"),
    ("Cons. Stato, sez. VI, n. 2345/2021", "Cons. Stato sez. VI n. 2345/2021"),
    ("Cons. St. n. 10/2020", "Cons. Stato n. 10/2020"),
    ("TAR Lazio, sez. II, n. 5678/2023", "TAR Lazio n. 5678/2023"),
    ("T.A.R. Lombardia Milano n. 12/2022", "TAR Lombardia Milano n. 12/2022"),
    ("CGUE, 13 maggio 2014, causa C-131/12", "CGUE causa C-131/12"),
    ("Corte di Giustizia UE, C-311/18", "CGUE causa C-311/18"),
]


@pytest.mark.parametrize("text,expected", CASES)
def test_canonical(text, expected):
    cs = extract_judgments(text)
    assert [c.canonical() for c in cs] == [expected]


def test_offsets_and_court():
    text = "Vedi Cass. sez. III n. 12345/2024 e Corte cost. n. 1/2000."
    cs = extract_judgments(text)
    assert [c.court for c in cs] == ["cassazione", "corte_costituzionale"]
    for c in cs:
        assert text[c.start:c.end] == c.display_text
    assert cs[0].verifiable_v1 and not cs[1].verifiable_v1


def test_norm_numbers_are_not_judgments():
    assert extract_judgments("art. 5 D.Lgs. 196/2003 e legge 241/1990") == []


def test_bare_cds_is_not_consiglio_di_stato():
    # "c.d.s." is Italian legal shorthand for "codice della strada" (Highway Code), not
    # "Consiglio di Stato". Matching it as a court swallowed the real norm citation
    # "art. 5 c.d.s." because extract_all lets judgments win every overlap (finding 5).
    assert extract_judgments("Violazione dell'art. 5 c.d.s. n. 285/1992") == []


@pytest.mark.parametrize("text,expected", [
    ("Cass., sentenza 12 gennaio 2022, n. 987", "Cass. n. 987/2022"),
    ("Cass. pen. Sez. III, sentenza 12 gennaio 2022 n. 987", "Cass. sez. III n. 987/2022"),
])
def test_cassazione_tipo_before_date_is_matched(text, expected):
    # "sentenza/ordinanza <data> n. <numero>" is the standard order in Italian briefs;
    # the original _SEZ + _DATE + _TIPO + _NUM ordering silently dropped it (finding 6).
    cs = extract_judgments(text)
    assert [c.canonical() for c in cs] == [expected]
