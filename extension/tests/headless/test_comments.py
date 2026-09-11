# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import pytest

from tests.headless.conftest import run_probe

pytestmark = pytest.mark.headless

AUTHOR = "LibreLex · verifica"


def test_exact_found_footnote_and_paragraph_start(soffice):
    out = run_probe(soffice, "comments_anchor", f'''
    def probe(ctx, out):
        doc = fixture_doc(ctx)
        a = DocumentAdapter(ctx, doc)
        doc.RecordChanges = True
        p0 = a.read_paragraphs(0, 1)[0]["text"]
        s = p0.index("art. 2043 c.c.")
        out["exact"] = a.add_comment("p:0", s, s + 14, "art. 2043 c.c.", {AUTHOR!r}, "commento uno")
        out["found"] = a.add_comment("p:0", 0, 5, "Cass. n. 12345/2024", {AUTHOR!r}, "commento due")
        out["fn"] = a.add_comment(
            "fn:1/p:0", 5, 33, "Cass. sez. III n. 12345/2024", {AUTHOR!r}, "in nota")
        out["cell"] = a.add_comment("t:0/c:B2/p:0", 13, 24, "art. 1 c.p.", {AUTHOR!r}, "in cella")
        out["lost"] = a.add_comment("p:2", 0, 3, "testo che non esiste", {AUTHOR!r}, "perso")
        out["annotations"] = annotations(doc)
        out["p0_after"] = a.read_paragraphs(0, 1)[0]["text"]
        out["redlines"] = redlines(doc)
        out["record"] = doc.RecordChanges
        doc.close(True)
    ''')
    assert (out["exact"], out["found"], out["fn"], out["cell"], out["lost"]) == (
        "exact", "found", "exact", "exact", "paragraph_start")
    anchors = {c["content"]: c["anchor"] for c in out["annotations"]}
    assert anchors["commento uno"] == "art. 2043 c.c."
    assert anchors["commento due"] == "Cass. n. 12345/2024"
    assert anchors["in nota"] == "Cass. sez. III n. 12345/2024"
    assert anchors["in cella"] == "art. 1 c.p."
    lost = [c for c in out["annotations"] if c["content"].endswith("perso")][0]
    assert lost["content"].startswith("[Posizione esatta non trovata nel paragrafo] ")
    assert all(c["author"] == AUTHOR for c in out["annotations"]) and len(out["annotations"]) == 5
    assert out["p0_after"].startswith("Primo paragrafo con art. 2043 c.c.")   # text intact
    assert out["redlines"] == [] and out["record"] is True


def test_anchor_survives_footnote_label_drift(soffice):
    out = run_probe(soffice, "comments_drift", f'''
    def probe(ctx, out):
        doc = new_doc(ctx)
        text = doc.Text
        cur = text.createTextCursor()
        for i in range(10):                        # ten footnotes: the last label is "10" (2 chars)
            text.insertString(cur, "x", False)
            fn = doc.createInstance("com.sun.star.text.Footnote")
            text.insertTextContent(cur, fn, False)
            fn.setString("nota %d" % (i + 1))
        text.insertString(cur, " poi art. 2043 c.c. fine", False)
        a = DocumentAdapter(ctx, doc)
        p = a.read_paragraphs(0, 1)[0]["text"]
        s = p.index("art. 2043 c.c.")
        out["string_offset"] = s
        out["anchored"] = a.add_comment("p:0", s, s + 14, "art. 2043 c.c.", {AUTHOR!r}, "drift")
        out["annotations"] = annotations(doc)
        doc.close(True)
    ''')
    assert out["anchored"] == "exact"
    assert out["annotations"] == [
        {"author": AUTHOR, "content": "drift", "anchor": "art. 2043 c.c."}]


def test_remove_comments_by_author_only(soffice):
    out = run_probe(soffice, "comments_remove", f'''
    def probe(ctx, out):
        doc = fixture_doc(ctx)
        a = DocumentAdapter(ctx, doc)
        a.add_comment("p:0", 20, 34, "art. 2043 c.c.", {AUTHOR!r}, "mio")
        a.add_comment("p:0", 20, 34, "art. 2043 c.c.", "Avv. Rossi", "suo")
        a.add_comment("fn:1/p:0", 5, 33, "Cass. sez. III n. 12345/2024", {AUTHOR!r}, "mio in nota")
        out["removed"] = a.remove_comments({AUTHOR!r})
        out["left"] = annotations(doc)
        out["removed_again"] = a.remove_comments({AUTHOR!r})
        out["undo_title"] = doc.getUndoManager().getCurrentUndoActionTitle()
        doc.close(True)
    ''')
    assert out["removed"] == 2 and out["removed_again"] == 0
    assert out["left"] == [{"author": "Avv. Rossi", "content": "suo", "anchor": "art. 2043 c.c."}]
    assert out["undo_title"] == "LibreLex: rimuovi commenti"
