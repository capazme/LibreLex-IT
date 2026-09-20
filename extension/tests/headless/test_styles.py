# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""The LibreLex act styles: created once, never overwritten, applied by pattern to a
drafting insertion after the Markdown filter (design §5.1, §5.3)."""
import pytest

from tests.headless.conftest import run_probe

pytestmark = pytest.mark.headless

ACT = """# TRIBUNALE DI MILANO

## ATTO DI CITAZIONE

**Alfa S.r.l.**, in persona del legale rappresentante

- attrice -

contro

**Beta S.p.A.**

- convenuta -

### PREMESSO CHE

- il credito è certo, liquido ed esigibile;
- la fattura n. 12 è rimasta insoluta.

1. primo motivo;
2. secondo motivo.

> Art. 633 c.p.c.: su domanda di chi è creditore di una somma liquida.

* * * * *

### CONCLUSIONI

Voglia il Tribunale accogliere la domanda.

Milano, 3 marzo 2026

Avv. Mario Rossi
"""


def test_act_styles_are_created_once_and_applied_by_pattern(soffice):
    out = run_probe(soffice, "act_styles", f'''
    def probe(ctx, out):
        doc = new_doc(ctx)
        adapter = DocumentAdapter(ctx, doc)
        family = doc.StyleFamilies.getByName("ParagraphStyles")
        custom = doc.createInstance("com.sun.star.style.ParagraphStyle")
        family.insertByName("LibreLex Corpo", custom)
        custom.CharHeight = 13.0                     # the lawyer's own adjustment
        out["created"] = adapter.ensure_act_styles()
        out["created_again"] = adapter.ensure_act_styles()
        out["corpo_height"] = family.getByName("LibreLex Corpo").CharHeight
        sezione = family.getByName("LibreLex Sezione")
        # Deviation from the brief: reading ParaAdjust back gives a plain int on 26.8 (only
        # setting it takes a uno.Enum), so no ".value" here.
        out["sezione"] = [sezione.CharFontName, sezione.CharHeight, sezione.CharWeight,
                          sezione.ParaAdjust, sezione.ParaTopMargin,
                          sezione.ParaLineSpacing.Height]
        punto = family.getByName("LibreLex Punto")
        out["punto"] = [punto.ParaLeftMargin, punto.ParaFirstLineIndent]
        res = adapter.insert_markdown("end", {ACT!r}, "LibreLex: atto", "LibreLex.atto.test",
                                      "LibreLex", act_styles=True)
        out["range"] = [res["from_id"], res["to_id"]]
        paras = []
        for style, text in paragraph_texts(doc.Text):
            paras.append([style, text])
        out["paras"] = paras
        out["numbered"] = []
        enum = doc.Text.createEnumeration()
        while enum.hasMoreElements():
            el = enum.nextElement()
            if el.supportsService("com.sun.star.text.Paragraph") and el.ListLabelString:
                out["numbered"].append(el.getString())
        out["redlines"] = redlines(doc)
    ''')
    assert len(out["created"]) == 9 and "LibreLex Corpo" not in out["created"]
    assert out["created_again"] == [] and out["corpo_height"] == 13.0
    assert out["sezione"] == ["Times New Roman", 12.0, 150.0, 3, 300, 150]   # 3 = CENTER
    # Deviation from the brief: Writer stores these margins internally in twips, so 500 (1/100
    # mm) round-trips to 499 through the mm100->twips->mm100 conversion; the value set is
    # still 500, only the readback after a unit round-trip is off by one on 26.8.
    assert out["punto"] == [499, -499]
    by_text = {t: s for s, t in out["paras"] if t}
    expect = {
        "TRIBUNALE DI MILANO": "LibreLex Intestazione",
        "ATTO DI CITAZIONE": "LibreLex Titolo atto",
        "Alfa S.r.l., in persona del legale rappresentante": "LibreLex Corpo",
        "- attrice -": "LibreLex Ruolo parte",
        "contro": "LibreLex Contro",
        "- convenuta -": "LibreLex Ruolo parte",
        "PREMESSO CHE": "LibreLex Sezione",
        "- il credito è certo, liquido ed esigibile;": "LibreLex Punto",
        "- la fattura n. 12 è rimasta insoluta.": "LibreLex Punto",
        "1. primo motivo;": "LibreLex Punto",
        "2. secondo motivo.": "LibreLex Punto",
        "Art. 633 c.p.c.: su domanda di chi è creditore di una somma liquida.":
            "LibreLex Citazione",
        "* * * * *": "LibreLex Separatore",
        "CONCLUSIONI": "LibreLex Sezione",
        "Voglia il Tribunale accogliere la domanda.": "LibreLex Corpo",
        "Milano, 3 marzo 2026": "LibreLex Firma",
        "Avv. Mario Rossi": "LibreLex Firma",
    }
    for text, style in expect.items():
        assert by_text.get(text) == style, (text, by_text.get(text), out["paras"])
    assert out["numbered"] == []                      # the list numbering became literal text
    assert out["redlines"] == [["Insert", "LibreLex"]]  # one tracked insertion, no Format redline
