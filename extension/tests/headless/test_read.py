# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tests.headless.conftest import EXT_DIR, run_probe

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


OOR = "{http://openoffice.org/2001/registry}"


def sidebar_panel_urls() -> list[str]:
    """The resource URLs the sidebar asks the factory for, straight from ``Sidebar.xcu``."""
    root = ET.parse(EXT_DIR / "Sidebar.xcu").getroot()   # only the root element is oor-prefixed
    return [prop.find("value").text.strip() for prop in root.iter("prop")
            if prop.get(f"{OOR}name") == "ImplementationURL"]


def test_panel_module_imports_inside_libreoffice(soffice):
    """Every registered panel URL must map onto a layout kind the factory can build."""
    urls = sidebar_panel_urls()
    out = run_probe(soffice, "panel_import", f'''
    def probe(ctx, out):
        from librelex_ext import layout, panel, registry, views
        out["xdl"] = panel.XDL_URL
        out["factory"] = type(panel.PanelFactory(ctx)).__name__
        out["kinds"] = [views.panel_kind(u) for u in {urls!r}]
        out["layout_kinds"] = sorted(layout.KINDS)
        registry.ensure_terminate_listener(ctx)
        out["pkg"] = str(panel.package_dir(ctx))
    ''')
    assert len(urls) == 3
    assert out["xdl"] == "vnd.sun.star.extension://org.librelex.extension/dialogs/panel.xdl"
    assert out["factory"] == "PanelFactory" and out["pkg"].endswith("/extension")
    assert sorted(out["kinds"]) == out["layout_kinds"]
    assert out["layout_kinds"] == ["Actions", "Answers", "Citations"]


def test_minimal_width_follows_the_layout_minimum(soffice):
    """Whole-branch review, minor 3: a deck narrower than the layout clips its right column.

    Uses the frame's container window, which implements XUnitConversion exactly like the
    XDL container window does, so the appfont conversion is the real one.
    """
    out = run_probe(soffice, "panel_minimal_width", '''
    def probe(ctx, out):
        from com.sun.star.awt import Size
        from com.sun.star.util.MeasureUnit import APPFONT

        from librelex_ext import layout, panel

        doc = new_doc(ctx)
        frame = doc.getCurrentController().getFrame()
        url = "private:resource/toolpanel/LibreLexPanelFactory/Actions"
        p = panel.Panel(ctx, frame, None, url, "Actions")
        p.window = frame.getContainerWindow()
        out["minimal"] = p.getMinimalWidth()
        out["expected"] = p.window.convertSizeToPixel(Size(layout.MIN_WIDTH, 0), APPFONT).Width
        p.window = None                   # no peer yet: the fallback must still be sane
        out["fallback"] = p.getMinimalWidth()
        doc.close(False)
    ''')
    assert out["minimal"] == out["expected"]
    assert out["minimal"] >= 240          # never narrower than the constant it replaces
    assert out["fallback"] == 280


def test_bridge_factory_errors_are_graceful_and_banner_survives_reopen(soffice):
    """Regression test for review findings 1 and 2 on task 9 and for whole-branch I2/m2.

    The three panels of the deck share one Session through ``registry.panel_set_for``;
    stand-ins with the six View methods take the place of the real container windows, so the
    real ``panel.make_session_factory``/registry/Session code path runs against a real Writer
    document without needing the XDL container window.
    """
    config_path = Path(tempfile.mkdtemp(prefix="librelex-cfg-")) / "config.toml"
    out = run_probe(soffice, "panel_uv_and_banner", '''
    def probe(ctx, out):
        import librelex_ext.paths as paths_mod
        from librelex_ext import panel, registry

        paths_mod.find_uv = lambda *a, **k: None  # deterministically "uv not found"

        class FakePanel:
            """One panel of the deck: the six View methods, recording what they receive."""

            def __init__(self):
                self.calls = []
                self.text = ""

            def append(self, text):
                self.calls.append("append")
                self.text = (self.text + "\\n" + text) if self.text else text

            def set_transcript(self, text):
                self.calls.append("set_transcript")
                self.text = text

            def set_status(self, text):
                self.calls.append("set_status")

            def set_busy(self, busy):
                self.calls.append("set_busy")

            def set_citations(self, labels):
                self.calls.append("set_citations")

            def set_progress(self, done, total):
                self.calls.append("set_progress")

        doc = new_doc(ctx)
        factory = panel.make_session_factory(ctx, doc)
        ps = registry.panel_set_for(ctx, doc, factory)
        out["same_panel_set"] = ps is registry.panel_set_for(ctx, doc, factory)

        # what Panel.getRealInterface does when the Risposte and Azioni panels open
        answers, actions = FakePanel(), FakePanel()
        ps.composite.attach("Answers", answers)
        answers.set_transcript("\\n".join(ps.session.transcript))
        ps.composite.attach("Actions", actions)
        actions.set_busy(ps.session.state in ("starting", "busy"))
        out["transcript_1"] = answers.text

        ps.session.run_command("insert_norm", {})   # no uv: must not raise out of run_command
        out["transcript_2"] = answers.text
        out["state_after_run"] = ps.session.state
        out["actions_calls"] = actions.calls

        ps.composite.detach("Answers")              # the Risposte panel is closed
        ps.session.note("mentre il pannello era chiuso")
        answers2 = FakePanel()                      # ... and opened again
        ps.composite.attach("Answers", answers2)
        answers2.set_transcript("\\n".join(ps.session.transcript))
        out["transcript_after_reopen"] = answers2.text
        out["same_session"] = ps.session is registry.session_for(doc, factory)

        def boom(*a, **k):                  # e.g. a config.toml the extension cannot digest
            raise ValueError("config.toml illeggibile")

        paths_mod.bridge_spec = boom
        ps.session.run_command("insert_norm", {})   # must not raise out of run_command either
        out["transcript_3"] = answers2.text
        out["state_3"] = ps.session.state

        # whole-branch m1: an event queued while every panel is closed must still reach the
        # session; a dropped `final` would leave it busy forever.
        ps.composite.detach("Answers")
        ps.composite.detach("Actions")
        ps.session.state, ps.session.request_id = "busy", "r9"
        ps.post({"kind": "message", "msg": {
            "type": "final", "request_id": "r9", "text": "Fatto.", "cancelled": False,
            "usage": None, "summary": {}}})
        ps.notify(None)
        out["queue_empty_after_notify"] = ps.queue.empty()
        out["state_after_notify"] = ps.session.state
        out["transcript_4"] = ps.session.transcript[-1]

        ps.session.shutdown()
        doc.close(False)
    ''', env={"LIBRELEX_CONFIG": str(config_path)})
    assert out["same_panel_set"] is True         # one PanelSet per document
    assert "LibreLex-IT pronto" in out["transcript_1"]
    assert out["state_after_run"] == "stopped"
    assert "Impossibile avviare il core" in out["transcript_2"]
    assert "uv non trovato" in out["transcript_2"]
    assert "append" not in out["actions_calls"]  # the transcript never reaches Azioni
    # the ready banner (finding 2) and the graceful uv error (finding 1) both survive
    # closing and reopening the panel, because both went through Session.transcript
    assert out["transcript_after_reopen"].startswith(out["transcript_2"])
    assert out["transcript_after_reopen"].endswith("mentre il pannello era chiuso")
    assert out["transcript_after_reopen"].count("LibreLex-IT pronto") == 1
    assert out["same_session"] is True          # the real registry.session_for, not a fake
    # whole-branch I2/m2: a non-UvNotFound failure of bridge_spec also becomes a BridgeError
    assert out["state_3"] == "stopped"
    assert "Impossibile avviare il core: config.toml illeggibile" in out["transcript_3"]
    # whole-branch m1: the PanelSet drains its queue into the session with no panel attached
    assert out["queue_empty_after_notify"] is True
    assert out["state_after_notify"] == "ready"
    assert out["transcript_4"] == "Fatto."
