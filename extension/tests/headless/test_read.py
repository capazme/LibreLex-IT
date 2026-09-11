# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import tempfile
from pathlib import Path

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


def test_panel_module_imports_inside_libreoffice(soffice):
    out = run_probe(soffice, "panel_import", '''
    def probe(ctx, out):
        from librelex_ext import panel, registry
        out["urls"] = [panel.PANEL_URL, panel.XDL_URL]
        out["factory"] = type(panel.PanelFactory(ctx)).__name__
        registry.ensure_terminate_listener(ctx)
        out["pkg"] = str(panel.package_dir(ctx))
    ''')
    assert out["urls"] == ["private:resource/toolpanel/LibreLexPanelFactory/Panel",
                           "vnd.sun.star.extension://org.librelex.extension/dialogs/panel.xdl"]
    assert out["factory"] == "PanelFactory" and out["pkg"].endswith("/extension")


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
        p = panel.Panel(ctx, frame, None, panel.PANEL_URL)
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

    Uses a bare-bones stand-in for Panel.window/model (getControl/getByName only) so the
    real Panel._attach_session/registry.session_for/Session code path runs against a real
    Writer document and frame, without needing the XDL container window.
    """
    config_path = Path(tempfile.mkdtemp(prefix="librelex-cfg-")) / "config.toml"
    out = run_probe(soffice, "panel_uv_and_banner", '''
    def probe(ctx, out):
        import librelex_ext.paths as paths_mod
        from librelex_ext import panel

        paths_mod.find_uv = lambda *a, **k: None  # deterministically "uv not found"

        class FakeCtrl:
            def __init__(self):
                self.text = ""

            def getText(self):
                return self.text

            def setText(self, value):
                self.text = value

            def getSelectedItemPos(self):
                return -1

        class FakeProp:
            def __init__(self):
                self.Label = ""
                self.Enabled = True
                self.StringItemList = ()

        class FakeWindow:
            def __init__(self):
                self._controls = {}

            def getControl(self, name):
                return self._controls.setdefault(name, FakeCtrl())

        class FakeModel:
            def __init__(self):
                self._props = {}

            def getByName(self, name):
                return self._props.setdefault(name, FakeProp())

        doc = new_doc(ctx)
        frame = doc.getCurrentController().getFrame()

        p1 = panel.Panel(ctx, frame, None, panel.PANEL_URL)
        p1.window, p1.model = FakeWindow(), FakeModel()
        p1._attach_session()
        out["transcript_1"] = p1.window.getControl("Transcript").getText()

        p1.session.run_command("insert_norm", {})   # no uv: must not raise out of run_command
        out["transcript_2"] = p1.window.getControl("Transcript").getText()
        out["state_after_run"] = p1.session.state

        p2 = panel.Panel(ctx, frame, None, panel.PANEL_URL)   # panel closed and reopened
        p2.window, p2.model = FakeWindow(), FakeModel()
        p2._attach_session()
        out["transcript_after_reopen"] = p2.window.getControl("Transcript").getText()
        out["same_session"] = p1.session is p2.session

        def boom(*a, **k):                  # e.g. a config.toml the extension cannot digest
            raise ValueError("config.toml illeggibile")

        paths_mod.bridge_spec = boom
        p2.session.run_command("insert_norm", {})   # must not raise out of run_command either
        out["transcript_3"] = p2.window.getControl("Transcript").getText()
        out["state_3"] = p2.session.state

        # whole-branch m1: an event already queued when the panel is disposed must still
        # reach the session; a dropped `final` would leave it busy forever.
        p2.session.state, p2.session.request_id = "busy", "r9"
        p2.queue.put({"kind": "message", "msg": {
            "type": "final", "request_id": "r9", "text": "Fatto.", "cancelled": False,
            "usage": None, "summary": {}}})
        p2.dispose()
        out["queue_empty_after_dispose"] = p2.queue.empty()
        out["state_after_dispose"] = p1.session.state
        out["transcript_4"] = p1.session.transcript[-1]

        p1.session.shutdown()
        doc.close(False)
    ''', env={"LIBRELEX_CONFIG": str(config_path)})
    assert "LibreLex-IT pronto" in out["transcript_1"]
    assert out["state_after_run"] == "stopped"
    assert "Impossibile avviare il core" in out["transcript_2"]
    assert "uv non trovato" in out["transcript_2"]
    # the ready banner (finding 2) and the graceful uv error (finding 1) both survive
    # closing and reopening the panel, because both went through Session.transcript
    assert out["transcript_after_reopen"] == out["transcript_2"]
    assert out["transcript_after_reopen"].count("LibreLex-IT pronto") == 1
    assert out["same_session"] is True          # the real registry.session_for, not a fake
    # whole-branch I2/m2: a non-UvNotFound failure of bridge_spec also becomes a BridgeError
    assert out["state_3"] == "stopped"
    assert "Impossibile avviare il core: config.toml illeggibile" in out["transcript_3"]
    # whole-branch m1: dispose() drains the queue into the session instead of dropping it
    assert out["queue_empty_after_dispose"] is True
    assert out["state_after_dispose"] == "ready"
    assert out["transcript_4"] == "Fatto."
