# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""apply_letterhead and make_letterhead (design §5.2, §5.3): the template's page style with
its header image and footer text lands in the document; the act styles are created; the
lawyer's own LibreLex style is kept."""
import pytest

from tests.headless.conftest import run_probe
from tests.headless.test_document import PNG_1PX

pytestmark = pytest.mark.headless

BUILD_SOURCE = '''
    def build_source(ctx, path, png):
        """A letterhead document: header with a logo, footer with the addresses, empty body."""
        import base64
        with open(png, "wb") as f:
            f.write(base64.b64decode({png_b64!r}))
        doc = new_doc(ctx)
        page = doc.StyleFamilies.getByName("PageStyles").getByName("Standard")
        page.HeaderIsOn = True
        page.FooterIsOn = True
        gp = ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.graphic.GraphicProvider", ctx)
        img = doc.createInstance("com.sun.star.text.TextGraphicObject")
        img.Graphic = gp.queryGraphic((prop("URL", uno.systemPathToFileUrl(png)),))
        page.HeaderText.insertTextContent(page.HeaderText.createTextCursor(), img, False)
        page.FooterText.insertString(
            page.FooterText.createTextCursor(), "Via Roma 1, Milano", False)
        family = doc.StyleFamilies.getByName("ParagraphStyles")
        corpo = doc.createInstance("com.sun.star.style.ParagraphStyle")
        family.insertByName("LibreLex Corpo", corpo)
        corpo.CharHeight = 13.0
        url = uno.systemPathToFileUrl(path)
        doc.storeToURL(url, (prop("FilterName", "MS Word 2007 XML"),))
        doc.close(True)
        return url

    def page_facts(doc):
        page = doc.StyleFamilies.getByName("PageStyles").getByName("Standard")
        family = doc.StyleFamilies.getByName("ParagraphStyles")
        return {{"header": page.HeaderIsOn, "footer": page.FooterIsOn,
                 "footer_text": page.FooterText.getString() if page.FooterIsOn else "",
                 "graphics": doc.GraphicObjects.getCount(),
                 "styles": [n for n in family.getElementNames() if n.startswith("LibreLex ")],
                 "corpo_height": family.getByName("LibreLex Corpo").CharHeight
                 if family.hasByName("LibreLex Corpo") else None}}
'''


def test_apply_letterhead_brings_the_page_style_and_keeps_the_templates_own_style(
        soffice, tmp_path):
    src, png = tmp_path / "carta.docx", tmp_path / "logo.png"
    out = run_probe(soffice, "apply_letterhead", BUILD_SOURCE.format(png_b64=PNG_1PX) + f'''
    def probe(ctx, out):
        url = build_source(ctx, {str(src)!r}, {str(png)!r})
        doc = new_doc(ctx)
        doc.Text.insertString(doc.Text.createTextCursor(), "Testo del cliente.", False)
        out["before"] = page_facts(doc)
        out["result"] = DocumentAdapter(ctx, doc).apply_letterhead(url)
        out["after"] = page_facts(doc)
        out["body"] = doc.Text.getString()
        try:
            missing_url = uno.systemPathToFileUrl({str(tmp_path / "manca.docx")!r})
            DocumentAdapter(ctx, doc).apply_letterhead(missing_url)
        except DocumentActionError as e:
            out["error"] = str(e)
        out["none"] = DocumentAdapter(ctx, new_doc(ctx)).apply_letterhead(None)
    ''')
    assert out["before"]["graphics"] == 0 and out["before"]["styles"] == []
    assert out["result"]["letterhead"] is True
    assert "LibreLex Corpo" not in out["result"]["created"] and len(out["result"]["created"]) == 9
    after = out["after"]
    assert after["header"] and after["footer"] and after["footer_text"] == "Via Roma 1, Milano"
    assert after["graphics"] == 1 and len(after["styles"]) == 10
    assert after["corpo_height"] == 13.0                # the template's own style, kept
    assert out["body"] == "Testo del cliente."           # the body is untouched
    assert out["error"] == "carta intestata non applicabile: manca.docx"
    assert out["none"]["letterhead"] is False and len(out["none"]["created"]) == 10


def test_make_letterhead_writes_a_template_with_the_letterhead_and_an_empty_body(soffice, tmp_path):
    src, png = tmp_path / "carta.docx", tmp_path / "logo.png"
    target = tmp_path / "modelli" / "SAPG Legal.ott"
    out = run_probe(soffice, "make_letterhead", BUILD_SOURCE.format(png_b64=PNG_1PX) + f'''
    from librelex_ext.document import make_letterhead

    def probe(ctx, out):
        url = build_source(ctx, {str(src)!r}, {str(png)!r})
        out["path"] = make_letterhead(ctx, url, {str(target)!r})
        desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
        tpl = desktop.loadComponentFromURL(uno.systemPathToFileUrl({str(target)!r}), "_blank", 0,
                                           (prop("Hidden", True), prop("AsTemplate", True)))
        out["facts"] = page_facts(tpl)
        out["body"] = tpl.Text.getString()
        tpl.close(True)
        try:
            make_letterhead(ctx, url, {str(target)!r})
        except DocumentActionError as e:
            out["error"] = str(e)
    ''')
    assert out["path"] == str(target) and target.exists()
    assert target.parent.exists()                        # the missing "modelli" folder is made
    facts = out["facts"]
    assert facts["header"] and facts["footer_text"] == "Via Roma 1, Milano"
    assert facts["graphics"] == 1
    assert len(facts["styles"]) == 10 and out["body"] == ""
    assert out["error"] == "modello già presente: SAPG Legal.ott"
