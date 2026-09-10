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
    ("C.d.S. n. 10/2020", "Cons. Stato n. 10/2020"),
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
