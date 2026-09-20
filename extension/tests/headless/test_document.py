# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""read_document: a similar case or a PDF letterhead source is read through LibreOffice's own
filters in a hidden document and closed right after (design §4.2, §5.2)."""
import pytest

from tests.headless.conftest import run_probe

pytestmark = pytest.mark.headless

SAVE = {"docx": "MS Word 2007 XML", "odt": "writer8", "txt": "Text", "doc": "MS Word 97"}

PNG_1PX = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhf"
           "DwAChwGA60e6kgAAAABJRU5ErkJggg==")


@pytest.mark.parametrize("ext", ["docx", "odt", "txt", "doc"])
def test_read_document_reads_body_paragraphs_and_closes_the_document(soffice, tmp_path, ext):
    path = tmp_path / f"ricorso_rossi.{ext}"
    out = run_probe(soffice, f"document_{ext}", f'''
    from librelex_ext.document import read_document

    def probe(ctx, out):
        doc = new_doc(ctx)
        text = doc.Text
        cur = text.createTextCursor()
        text.insertString(cur, "RICORSO PER DECRETO INGIUNTIVO", False)
        text.insertControlCharacter(cur, PARAGRAPH_BREAK, False)
        text.insertString(cur, "Il ricorrente espone quanto segue.", False)
        url = uno.systemPathToFileUrl({str(path)!r})
        doc.storeToURL(url, (prop("FilterName", {SAVE[ext]!r}),))
        doc.close(True)
        desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
        before = sum(1 for _ in _components(desktop))
        out["ref"] = read_document(ctx, url)
        out["open_after"] = sum(1 for _ in _components(desktop)) - before

    def _components(desktop):
        e = desktop.getComponents().createEnumeration()
        while e.hasMoreElements():
            yield e.nextElement()
    ''')
    ref = out["ref"]
    assert ref["name"] == f"ricorso_rossi.{ext}" and ref["kind"] == "writer"
    assert ref["text"].startswith("RICORSO PER DECRETO INGIUNTIVO")
    assert "Il ricorrente espone quanto segue." in ref["text"]
    assert ref["chars"] == len(ref["text"])
    assert out["open_after"] == 0                 # the hidden document was closed


def test_read_document_reports_a_missing_file(soffice, tmp_path):
    out = run_probe(soffice, "document_missing", f'''
    from librelex_ext.document import DocumentActionError, read_document

    def probe(ctx, out):
        try:
            read_document(ctx, uno.systemPathToFileUrl({str(tmp_path / "manca.docx")!r}))
        except DocumentActionError as e:
            out["error"] = str(e)
    ''')
    assert out["error"].startswith("impossibile aprire il file: manca.docx")


def test_read_document_rebuilds_the_lines_of_a_two_page_pdf_with_a_header_image(soffice, tmp_path):
    pdf = tmp_path / "diffida.pdf"
    png = tmp_path / "logo.png"
    out = run_probe(soffice, "document_pdf", f'''
    import base64
    from com.sun.star.style.BreakType import PAGE_BEFORE
    from librelex_ext.document import read_document

    def probe(ctx, out):
        with open({str(png)!r}, "wb") as f:
            f.write(base64.b64decode({PNG_1PX!r}))
        doc = new_doc(ctx)
        page = doc.StyleFamilies.getByName("PageStyles").getByName("Standard")
        page.HeaderIsOn = True
        gp = ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.graphic.GraphicProvider", ctx)
        graphic = gp.queryGraphic((prop("URL", uno.systemPathToFileUrl({str(png)!r})),))
        img = doc.createInstance("com.sun.star.text.TextGraphicObject")
        img.Graphic = graphic
        header = page.HeaderText
        header.insertTextContent(header.createTextCursor(), img, False)
        text = doc.Text
        cur = text.createTextCursor()
        text.insertString(
            cur, "Il ricorrente espone quanto segue in questa riga giustificata.", False)
        cur.ParaAdjust = 2      # BLOCK: the PDF import then gives one frame per word
        text.insertControlCharacter(cur, PARAGRAPH_BREAK, False)
        text.insertString(cur, "Seconda riga.", False)
        text.insertControlCharacter(cur, PARAGRAPH_BREAK, False)
        cur.BreakType = PAGE_BEFORE
        text.insertString(cur, "Pagina due.", False)
        url = uno.systemPathToFileUrl({str(pdf)!r})
        doc.storeToURL(url, (prop("FilterName", "writer_pdf_Export"),))
        doc.close(True)
        desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
        before = sum(1 for _ in _components(desktop))
        out["doc"] = read_document(ctx, url)
        out["open_after"] = sum(1 for _ in _components(desktop)) - before

    def _components(desktop):
        e = desktop.getComponents().createEnumeration()
        while e.hasMoreElements():
            yield e.nextElement()
    ''')
    d = out["doc"]
    assert d["name"] == "diffida.pdf" and d["kind"] == "pdf" and d["chars"] == len(d["text"])
    lines = d["text"].split("\n")
    assert "Il ricorrente espone quanto segue in questa riga giustificata." in lines, lines
    assert "Seconda riga." in lines and "--- pagina 2 ---" in lines and "Pagina due." in lines
    assert lines.index("--- pagina 2 ---") < lines.index("Pagina due.")
    assert out["open_after"] == 0


def test_read_document_refuses_a_pdf_without_text(soffice, tmp_path):
    pdf = tmp_path / "scansione.pdf"
    out = run_probe(soffice, "document_pdf_empty", f'''
    from librelex_ext.document import DocumentActionError, read_document

    def probe(ctx, out):
        doc = new_doc(ctx)          # empty body: the export carries no text frame at all
        url = uno.systemPathToFileUrl({str(pdf)!r})
        doc.storeToURL(url, (prop("FilterName", "writer_pdf_Export"),))
        doc.close(True)
        try:
            read_document(ctx, url)
        except DocumentActionError as e:
            out["error"] = str(e)
    ''')
    assert out["error"] == "PDF senza testo (scansione): non leggibile: scansione.pdf"
