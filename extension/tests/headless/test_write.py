# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import pytest

from tests.headless.conftest import run_probe

pytestmark = pytest.mark.headless

MD = ("**Art. 2043 c.c.**\n\n"
      "> Qualunque fatto doloso o colposo.\n> Secondo comma.\n\n"
      "*Testo vigente al 7 settembre 2026, fonte Normattiva, https://x*\n")


def test_insert_at_cursor_end_of_paragraph_is_one_tracked_insert_with_author(soffice):
    out = run_probe(soffice, "write_cursor", f'''
    def probe(ctx, out):
        doc = fixture_doc(ctx)
        a = DocumentAdapter(ctx, doc)
        acc = a._profile_access(update=False)
        out["identity_before"] = [acc.getPropertyValue("givenname"),
                                  acc.getPropertyValue("sn")]
        vc = doc.getCurrentController().getViewCursor()
        a.goto("p:0")
        cur = doc.Text.createTextCursor(); cur.gotoStart(False); cur.gotoEndOfParagraph(False)
        vc.gotoRange(cur, False)
        out["record_before"] = doc.RecordChanges
        out["result"] = a.insert_markdown("cursor", {MD!r},
                                          "LibreLex: inserisci art. 2043 c.c.",
                                          bookmark="LibreLex.norma.test", author="LibreLex")
        out["record_after"] = doc.RecordChanges
        out["paragraphs"] = paragraph_texts(doc.Text)
        out["redlines"] = redlines(doc)
        out["bookmarks"] = list(doc.Bookmarks.getElementNames())
        bm = doc.Bookmarks.getByName("LibreLex.norma.test")
        out["bookmark_text"] = bm.getAnchor().getString()
        out["undo_title"] = doc.getUndoManager().getCurrentUndoActionTitle()
        acc = a._profile_access(update=False)
        out["identity_after"] = [acc.getPropertyValue("givenname"),
                                 acc.getPropertyValue("sn")]
        out["all"] = [p["id"] for p in a.read_paragraphs(None, None)]
        doc.close(True)
    ''')
    assert out["result"] == {"from_id": "p:1", "to_id": "p:3"}
    paras = out["paragraphs"]
    assert paras[0][1].startswith("Primo paragrafo")
    assert paras[1][1] == "Art. 2043 c.c." and paras[2][0] == "Quotations"
    assert paras[2][1] == "Qualunque fatto doloso o colposo. Secondo comma." or \
        paras[2][1].startswith("Qualunque fatto doloso o colposo.")
    assert paras[3][1].startswith("Testo vigente al 7 settembre 2026")
    assert paras[4][1].startswith("Secondo paragrafo")          # no stray empty paragraph
    assert out["redlines"] and all(t == "Insert" and a == "LibreLex" for t, a in out["redlines"])
    assert out["record_before"] is False and out["record_after"] is False
    assert out["identity_after"] == out["identity_before"]
    assert "LibreLex.norma.test" in out["bookmarks"]
    assert out["bookmark_text"].startswith("Art. 2043 c.c.")
    assert "Testo vigente" in out["bookmark_text"]
    assert out["undo_title"] == "LibreLex: inserisci art. 2043 c.c."
    assert out["all"][:5] == ["p:0", "p:1", "p:2", "p:3", "p:4"]


def test_insert_mid_paragraph_heading_style_and_end_and_no_author(soffice):
    out = run_probe(soffice, "write_variants", '''
    def probe(ctx, out):
        doc = fixture_doc(ctx)
        a = DocumentAdapter(ctx, doc)
        vc = doc.getCurrentController().getViewCursor()
        a.goto("p:0")
        vc.goRight(6, False)                     # inside "Primo |paragrafo ..."
        doc.RecordChanges = True                  # already on: must stay on afterwards
        out["mid"] = a.insert_markdown("cursor", "# Titolo\\n\\nCorpo.\\n",
                                       "LibreLex: test", None, None)
        out["record_after"] = doc.RecordChanges
        out["paragraphs"] = paragraph_texts(doc.Text)
        out["redline_authors"] = sorted(set(a for _, a in redlines(doc)))
        doc.RecordChanges = False
        out["end"] = a.insert_markdown("end", "Coda.\\n", "LibreLex: coda",
                                       "LibreLex.norma.test", "LibreLex")
        out["end2"] = a.insert_markdown("end", "Coda2.\\n", "LibreLex: coda",
                                        "LibreLex.norma.test", "LibreLex")
        out["bookmarks"] = sorted(doc.Bookmarks.getElementNames())
        out["tail"] = paragraph_texts(doc.Text)[-3:]
        out["after"] = a.insert_markdown("after:p:0", "Dopo.\\n", "LibreLex: dopo", None, None)
        out["p1"] = paragraph_texts(doc.Text)[1][1]
        doc.close(True)
    ''')
    assert out["mid"] == {"from_id": "p:1", "to_id": "p:2"}
    paras = out["paragraphs"]
    assert paras[0][1] == "Primo "
    assert paras[1] == ["Heading 1", "Titolo"] and paras[2][1] == "Corpo."
    assert paras[3][1].startswith("paragrafo con art. 2043")
    assert out["record_after"] is True
    # author=None keeps the user identity
    assert out["redline_authors"] != ["LibreLex"]
    assert out["end"]["from_id"] == out["end"]["to_id"]
    assert out["end2"]["from_id"] != out["end"]["from_id"]
    assert out["bookmarks"] == ["LibreLex.norma.test", "LibreLex.norma.test_2"]
    assert [t for _, t in out["tail"]][-2:] == ["Coda.", "Coda2."]
    assert out["after"] == {"from_id": "p:1", "to_id": "p:1"} and out["p1"] == "Dopo."


def test_insert_inside_footnote_and_replace_selection(soffice):
    out = run_probe(soffice, "write_footnote_replace", '''
    def probe(ctx, out):
        doc = fixture_doc(ctx)
        a = DocumentAdapter(ctx, doc)
        a.goto("fn:1/p:0")
        vc = doc.getCurrentController().getViewCursor()
        vc.gotoEnd(False) if hasattr(vc, "gotoEnd") else vc.goRight(34, False)
        out["fn"] = a.insert_markdown("cursor", "Nota aggiunta.\\n", "LibreLex: nota",
                                      None, "LibreLex")
        out["fn_paras"] = [p for p in a.read_paragraphs(None, None) if p["id"].startswith("fn:")]
        a.goto("p:2")
        vc = doc.getCurrentController().getViewCursor()
        vc.goRight(16, True)                     # select "Terzo paragrafo."
        out["sel"] = a.read_selection()["text"]
        out["rep"] = a.replace_selection("Paragrafo riscritto.\\n", "LibreLex: riscrivi")
        out["redlines"] = redlines(doc)
        out["tail"] = paragraph_texts(doc.Text)[-2:]
        doc.close(True)
    ''')
    assert out["fn"] == {"from_id": "fn:1/p:1", "to_id": "fn:1/p:1"}
    assert [p["text"] for p in out["fn_paras"]] == ["Cfr. Cass. sez. III n. 12345/2024.",
                                                    "Nota aggiunta."]
    assert out["sel"] == "Terzo paragrafo."
    assert out["rep"]["from_id"] == "p:3" and out["rep"]["to_id"] == "p:3"
    kinds = sorted(set(t for t, _ in out["redlines"]))
    assert kinds == ["Delete", "Insert"] and all(a == "LibreLex" for _, a in out["redlines"])
    assert out["tail"][-1][1] == "Paragrafo riscritto."
