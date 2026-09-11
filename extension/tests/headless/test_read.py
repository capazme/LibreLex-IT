# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import pytest

from tests.headless.conftest import run_probe

pytestmark = pytest.mark.headless


def test_info_paragraphs_footnotes_tables_and_find(soffice):
    out = run_probe(soffice, "read_all", '''
    def probe(ctx, out):
        doc = fixture_doc(ctx)
        a = DocumentAdapter(ctx, doc)
        out["version"] = lo_version(ctx)
        out["markdown"] = has_markdown_filter(ctx)
        out["info"] = a.get_document_info()
        out["all"] = a.read_paragraphs(None, None)
        out["first"] = a.read_paragraphs(0, 1)
        out["find_all"] = a.find_text("art. 1 c.p.", None)
        out["find_in"] = a.find_text("Cass.", "fn:1/p:0")
        out["missing"] = None
        try:
            a.find_text("x", "p:99")
        except DocumentActionError as e:
            out["missing"] = str(e)
        doc.close(True)
    ''')
    assert out["version"].startswith("26.") and out["markdown"] is True
    info = out["info"]
    assert info["paragraph_count"] == 3 and info["has_selection"] is False
    assert info["lo_version"] == out["version"] and info["has_markdown_filter"] is True
    ids = [p["id"] for p in out["all"]]
    assert ids[:3] == ["p:0", "p:1", "fn:1/p:0"]
    assert "t:0/c:A1/p:0" in ids and "t:0/c:B2/p:0" in ids and ids[-1] == "p:2"
    by_id = {p["id"]: p for p in out["all"]}
    assert by_id["p:0"]["text"].startswith("Primo paragrafo") and by_id["p:0"]["kind"] == "body"
    assert by_id["fn:1/p:0"] == {"id": "fn:1/p:0", "text": "Cfr. Cass. sez. III n. 12345/2024.",
                                 "style": by_id["fn:1/p:0"]["style"], "kind": "footnote"}
    assert by_id["t:0/c:B2/p:0"]["kind"] == "table_cell"
    assert by_id["p:2"]["text"] == "Terzo paragrafo."
    assert [p["id"] for p in out["first"]] == ["p:0"]
    assert out["find_all"] == [{"anchor": {"paragraph_id": "t:0/c:B2/p:0", "start": 13, "end": 24},
                                "text": "art. 1 c.p."}]
    assert out["find_in"][0]["anchor"] == {"paragraph_id": "fn:1/p:0", "start": 5, "end": 10}
    assert "p:99" in out["missing"]


def test_selection_and_goto(soffice):
    out = run_probe(soffice, "read_selection", '''
    def probe(ctx, out):
        doc = fixture_doc(ctx)
        a = DocumentAdapter(ctx, doc)
        out["empty"] = a.read_selection()
        a.goto("p:1")
        vc = doc.getCurrentController().getViewCursor()
        vc.goRight(8, False)          # after "Secondo "
        vc.goRight(9, True)           # select "paragrafo"
        out["sel"] = a.read_selection()
        out["info"] = a.get_document_info()
        a.goto("fn:1/p:0")
        out["fn_sel"] = a.read_selection()
        vc = doc.getCurrentController().getViewCursor()
        vc.goRight(4, True)
        out["fn_sel2"] = a.read_selection()
        doc.close(True)
    ''')
    assert out["empty"] == {"text": "", "anchor": None}
    assert out["sel"] == {"text": "paragrafo",
                          "anchor": {"paragraph_id": "p:1", "start": 8, "end": 17}}
    assert out["info"]["has_selection"] is True and out["info"]["cursor_paragraph"] == "p:1"
    assert out["fn_sel"]["text"] == ""
    assert out["fn_sel2"] == {"text": "Cfr.",
                              "anchor": {"paragraph_id": "fn:1/p:0", "start": 0, "end": 4}}
