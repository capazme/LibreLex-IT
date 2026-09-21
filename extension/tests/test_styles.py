# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
from librelex_ext.styles import ACT_STYLES, COMMON, act_style_for, list_prefix, style_properties


def test_ten_styles_with_the_canon_on_top_of_the_common_font():
    assert len(ACT_STYLES) == 10 and all(n.startswith("LibreLex ") for n in ACT_STYLES)
    corpo = style_properties("LibreLex Corpo")
    assert corpo["CharFontName"] == "Times New Roman" and corpo["CharHeight"] == 12.0
    assert corpo["ParaLineSpacing"] == ("PROP", 150) and corpo["ParaAdjust"] == "BLOCK"
    assert style_properties("LibreLex Punto")["ParaFirstLineIndent"] == -500
    assert style_properties("LibreLex Citazione")["CharHeight"] == 11.0
    assert style_properties("LibreLex Sezione")["ParaTopMargin"] == 300
    assert COMMON["ParaFirstLineIndent"] == 0


def test_act_style_for_follows_the_pattern_order():
    cases = [
        ("TRIBUNALE DI MILANO", "heading1", 9, "LibreLex Intestazione"),
        ("ATTO DI CITAZIONE", "heading2", 9, "LibreLex Titolo atto"),
        ("PREMESSO CHE", "heading3", 9, "LibreLex Sezione"),
        ("* * * * *", "body", 9, "LibreLex Separatore"),
        ("***", "body", 9, "LibreLex Separatore"),
        ("contro", "body", 9, "LibreLex Contro"),
        ("CONTRO", "list", 9, "LibreLex Contro"),
        ("- ricorrente -", "body", 9, "LibreLex Ruolo parte"),
        ("- opponente -", "list", 9, "LibreLex Ruolo parte"),
        ("il credito è certo", "list", 9, "LibreLex Punto"),
        ("Art. 633 c.p.c.: ...", "quote", 9, "LibreLex Citazione"),
        ("Avv. Mario Rossi", "body", 9, "LibreLex Corpo"),
        ("[Luogo], [Data]", "body", 9, "LibreLex Firma"),
        ("Milano, 3 marzo 2026", "body", 1, "LibreLex Firma"),
        ("Milano, 3 marzo 2026", "body", 5, "LibreLex Corpo"),
        ("Il sottoscritto espone quanto segue.", "body", 0, "LibreLex Corpo"),
        ("- un trattino lungo che non è un ruolo di parte perché supera i quaranta -",
         "body", 9, "LibreLex Corpo"),
    ]
    for text, origin, from_end, want in cases:
        assert act_style_for(text, origin, from_end) == want, (text, origin)


def test_list_prefix_keeps_numbers_and_dashes_everything_else():
    assert list_prefix("1.") == "1. " and list_prefix("12)") == "12. "
    assert list_prefix("•") == "- " and list_prefix("") == "- "
