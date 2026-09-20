# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""read_reference: a similar case chosen by the lawyer is read through LibreOffice's own
filters in a hidden document and closed right after (design §5.2)."""
import pytest

from tests.headless.conftest import run_probe

pytestmark = pytest.mark.headless

SAVE = {"docx": "MS Word 2007 XML", "odt": "writer8", "txt": "Text"}


@pytest.mark.parametrize("ext", ["docx", "odt", "txt"])
def test_read_reference_reads_body_paragraphs_and_closes_the_document(soffice, tmp_path, ext):
    path = tmp_path / f"ricorso_rossi.{ext}"
    out = run_probe(soffice, f"reference_{ext}", f'''
    from librelex_ext.document import read_reference

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
        out["ref"] = read_reference(ctx, url)
        out["open_after"] = sum(1 for _ in _components(desktop)) - before

    def _components(desktop):
        e = desktop.getComponents().createEnumeration()
        while e.hasMoreElements():
            yield e.nextElement()
    ''')
    ref = out["ref"]
    assert ref["name"] == f"ricorso_rossi.{ext}"
    assert ref["text"].startswith("RICORSO PER DECRETO INGIUNTIVO")
    assert "Il ricorrente espone quanto segue." in ref["text"]
    assert ref["chars"] == len(ref["text"])
    assert out["open_after"] == 0                 # the hidden document was closed


def test_read_reference_reports_a_missing_file(soffice, tmp_path):
    out = run_probe(soffice, "reference_missing", f'''
    from librelex_ext.document import DocumentActionError, read_reference

    def probe(ctx, out):
        try:
            read_reference(ctx, uno.systemPathToFileUrl({str(tmp_path / "manca.docx")!r}))
        except DocumentActionError as e:
            out["error"] = str(e)
    ''')
    assert out["error"].startswith("impossibile aprire il file: manca.docx")
