# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""The drafting workbench end to end through the real Writer sidebar, in a visible LibreOffice.

Headless soffice cannot host this test: it disposes every sidebar panel as soon as a modal
loop runs and never builds them again, so a probe keeps driving dead objects (clicks ignored,
then SIGSEGV on the stale ``XPanel`` peers). A visible LibreOffice keeps the deck alive, which
is also the only place the 0.7.0 field crash (sidebar API entered while the deck was being
built) can be reproduced. The test opens windows, so it runs only when
``LIBRELEX_GUI_TESTS=1``.

How it runs: the .oxt is installed headless into a private profile, then a visible
LibreOffice on that profile runs the probe macro. The macro writes its evidence after every
stage, so a hang still says where it stopped; pytest ends LibreOffice itself once the
evidence says ``done`` (a script asking LibreOffice to terminate from inside its own startup
dispatch is not reliable).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from tests.headless.llm_stub import StubLLM, chunk, tool_call_response, usage

pytestmark = [
    pytest.mark.headless,
    pytest.mark.gui,
    pytest.mark.skipif(os.environ.get("LIBRELEX_GUI_TESTS") != "1",
                       reason="opens LibreOffice windows: set LIBRELEX_GUI_TESTS=1"),
]

REPO = Path(__file__).resolve().parents[3]
CORE = REPO / "core"
INSTALL_MACRO = REPO / "scripts" / "lo_install.py"

# Runs inside the visible LibreOffice. The local fake MCP server and the scripted localhost
# model make this a real .oxt → panel → Session → Bridge → core → Writer test without any
# external service. Probe steps are delivered through the panel's own AsyncCallback; the
# Panel and PanelSet callbacks are dispatched by LibreOffice's main loop, never called here.
PROBE_MACRO = """
import json, os, threading, time, traceback, uno, unohelper
from com.sun.star.beans import PropertyValue

DECK = "LibreLexDeck"


def _write(out):
    path = os.environ["LIBRELEX_CHECK_RESULT"]
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    os.replace(tmp, path)


class _Action:
    def __init__(self, command):
        self.ActionCommand = command


class _ItemSource:
    def __init__(self, name):
        self.Name = name

    def getModel(self):
        return self


class _ItemEvent:
    def __init__(self, name):
        self.Source = _ItemSource(name)


class _Probe:
    def __init__(self, monitor, out, doc, sidebar, session, panel_set, panel):
        self.monitor, self.out, self.doc, self.sidebar = monitor, out, doc, sidebar
        self.session, self.panel_set, self.panel = session, panel_set, panel
        self.async_cb = panel._async_cb
        self.stage = "restored"
        self.deadline = None
        self.ticks = 0
        self.pending = False
        self.finished = False
        self.timer = None

    def on_panel(self, panel_id, fn):
        # Looked up on every use (a panel kept across main-loop turns may belong to a deck
        # LibreOffice has since rebuilt), with the deck and its panel collection held in
        # locals until ``fn`` returns: SfxUnoPanels keeps no reference to its deck, so a
        # chained ``getByName(DECK).getPanels().getByName(...)`` crashes in hasByName.
        decks = self.sidebar.getDecks()
        deck = decks.getByName(DECK)
        panels = deck.getPanels()
        result = fn(panels.getByName(panel_id))
        del panels, deck, decks
        return result

    def title(self):
        return self.on_panel("LibreLexRedazionePanel", lambda p: p.getTitle())

    def collapsed(self, panel_id):
        return self.on_panel(panel_id, lambda p: not p.isExpanded())

    def start(self):
        self.original_notify = self.panel.notify

        def panel_notify(data):
            self.original_notify(data)
            if self.pending and not self.finished:
                self.pending = False
                self.ticks += 1
                try:
                    self.run_stage()
                except Exception:
                    self.out["traceback"] = traceback.format_exc()
                    self.finish()

        self.panel.notify = panel_notify
        self.schedule()

    def schedule(self):
        if self.finished or self.pending:
            return
        self.pending = True
        self.timer = threading.Timer(0.01, self._post)
        self.timer.daemon = True
        self.timer.start()

    def _post(self):
        if self.pending and not self.finished:
            self.async_cb.addCallback(self.panel, None)

    def wait_for(self, predicate, label, next_stage, timeout=180):
        if predicate():
            self.stage = next_stage
            self.deadline = None
            self.schedule()
            return
        if self.deadline is None:
            self.deadline = time.monotonic() + timeout
        if time.monotonic() >= self.deadline:
            raise TimeoutError(f"timed out waiting for {label}: state={self.session.state} "
                               f"step={self.session.draft_view['step']} "
                               f"transcript={self.session.transcript[-5:]}")
        self.schedule()

    def run_stage(self):
        self.out["stage"], self.out["state"] = self.stage, self.session.state
        _write(self.out)

        if self.stage == "restored":
            if self.panel._sidebar_ops:
                self.schedule()
                return
            # The deck was built with a drafting already at step 3: its replay queued the
            # title and the collapse; both have run by now, in their own callbacks.
            self.out["restored_step"] = self.panel._step
            self.out["restored_title"] = self.title()
            self.out["restored_actions_collapsed"] = self.collapsed("LibreLexActionsPanel")
            self.out["restored_citations_collapsed"] = self.collapsed("LibreLexCitationsPanel")
            self.out["restored_callback_drained"] = not self.panel._sidebar_ops
            self.session.new_drafting()
            # Starting a drafting collapses the other panels only on the way from step 1 to
            # step 3, so expand them again to see the start collapse them.
            self.on_panel("LibreLexActionsPanel", lambda p: p.expand(False))
            self.on_panel("LibreLexCitationsPanel", lambda p: p.expand(False))
            self.stage = "reset_ui"
            self.schedule()
            return

        if self.stage == "reset_ui":
            self.out["fresh_title"] = self.title()
            self.out["start_actions_expanded_before"] = not self.collapsed("LibreLexActionsPanel")
            self.out["start_citations_expanded_before"] = not self.collapsed(
                "LibreLexCitationsPanel")
            self.panel.actionPerformed(_Action("template_search"))
            self.stage = "wait_catalogue"
            self.schedule()
            return

        if self.stage == "wait_catalogue":
            self.wait_for(lambda: self.session.state == "ready"
                          and bool(self.session.draft_view["templates"]),
                          "template catalogue", "select_template")
            return

        if self.stage == "select_template":
            models = self.session.draft_view["templates"]
            index = next(i for i, item in enumerate(models)
                         if item["tipo_atto"] == "decreto_ingiuntivo_ordinario")
            self.out["selected_type"] = models[index]["tipo_atto"]
            self.panel._quiet_items = True
            self.panel.window.getControl("Template").selectItemPos(index, True)
            self.panel._quiet_items = False
            self.panel.itemStateChanged(_ItemEvent("Template"))
            self.stage = "wait_template_info"
            self.schedule()
            return

        if self.stage == "wait_template_info":
            self.wait_for(lambda: self.session.state == "ready"
                          and self.session.draft_view.get("template", {}).get("tipo_atto")
                          == "decreto_ingiuntivo_ordinario",
                          "selected template", "start_draft")
            return

        if self.stage == "start_draft":
            fields = {"creditore": "Alfa S.r.l.", "debitore": "Beta S.p.A.", "importo": "12000"}
            for row, name in enumerate(fields, 1):
                self.panel.window.getControl(f"Field{row}").setText(fields[name])
            self.panel.window.getControl("Notes").setText("Prova end-to-end della sidebar")
            self.out["start_enabled"] = self.panel.model.getByName("Start").Enabled
            self.panel.actionPerformed(_Action("draft_start"))
            self.out["start_step"] = self.session.draft_view["step"]
            self.out["start_submitted"] = self.session.state in ("starting", "busy")
            self.stage = "start_ui"
            self.schedule()
            return

        if self.stage == "start_ui":
            if self.panel._sidebar_ops:          # title, then collapse: one callback each
                self.schedule()
                return
            self.out["title_after_start"] = self.title()
            self.out["actions_collapsed_after_start"] = self.collapsed("LibreLexActionsPanel")
            self.out["citations_collapsed_after_start"] = self.collapsed(
                "LibreLexCitationsPanel")
            self.stage = "wait_question"
            self.schedule()
            return

        if self.stage == "wait_question":
            self.wait_for(lambda: self.session.state == "ready"
                          and self.session.draft_view["step"] == 2
                          and bool(self.session.draft_view["questions"]),
                          "step-2 question", "question_ui")
            return

        if self.stage == "question_ui":
            if self.panel._sidebar_ops:
                self.schedule()
                return
            self.out["question"] = self.session.draft_view["questions"][0]["domanda"]
            self.out["title_after_question"] = self.title()
            self.panel.window.getControl("Answer1").setText("Milano")
            self.panel.actionPerformed(_Action("draft_answer"))
            self.out["answer_step"] = self.session.draft_view["step"]
            self.stage = "wait_finished"
            self.schedule()
            return

        if self.stage == "wait_finished":
            self.wait_for(lambda: self.session.state == "ready"
                          and self.session.draft_view["step"] == 4
                          and self.session.draft_view["done"]
                          and not self.panel._sidebar_ops,
                          "completed drafting", "finished_ui")
            return

        if self.stage == "finished_ui":
            self.out["finished_title"] = self.title()
            self.out["draft_done"] = self.session.draft_view["done"]
            self.out["questions_remaining"] = self.session.draft_view["questions"]
            self.out["partitions"] = [p["titolo"] for p in self.session.draft_view["partitions"]]
            self.out["document_text"] = self.doc.Text.getString()
            self.out["core_state"] = self.session.state
            self.finish()
            return

        raise AssertionError(f"unknown probe stage: {self.stage}")

    def finish(self):
        if self.finished:
            return
        self.finished = True
        if self.timer is not None:
            self.timer.cancel()
        self.panel.notify = self.original_notify
        self.out["async_callback_ticks"] = self.ticks
        self.out["stage"] = "shutdown"
        _write(self.out)
        started = time.monotonic()
        try:
            self.session.shutdown()
        except Exception:
            self.out["shutdown_error"] = traceback.format_exc()
        self.out["shutdown_seconds"] = round(time.monotonic() - started, 2)
        self.out["done"] = True
        _write(self.out)
        self.monitor.endExecute()


def _monitor_dialog(ctx):
    # An off-screen modal dialog: its nested main loop dispatches the queued UNO callbacks
    # while the macro keeps its objects alive.
    smgr = ctx.ServiceManager
    model = smgr.createInstanceWithContext("com.sun.star.awt.UnoControlDialogModel", ctx)
    model.Width, model.Height = 1, 1
    model.PositionX, model.PositionY = -1000, -1000
    dialog = smgr.createInstanceWithContext("com.sun.star.awt.UnoControlDialog", ctx)
    dialog.setModel(model)
    dialog.createPeer(smgr.createInstanceWithContext("com.sun.star.awt.Toolkit", ctx), None)
    return dialog


def main(*args):
    global _probe
    ctx = uno.getComponentContext()
    desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    out = {"stage": "setup"}
    try:
        # Loading the component puts the installed package on sys.path.
        out["factory"] = ctx.ServiceManager.createInstanceWithContext(
            "org.librelex.extension.PanelFactory", ctx) is not None
        import librelex_ext.panel as panel_module
        import librelex_ext.registry as registry

        doc = desktop.loadComponentFromURL("private:factory/swriter", "_blank", 0, ())
        model = doc.getCurrentController().getModel()
        panel_set = registry.panel_set_for(
            ctx, model, panel_module.make_session_factory(ctx, model))
        session = panel_set.session
        # A drafting already in progress when the deck is first built: the panel's replay
        # must queue its sidebar calls instead of entering the deck under construction.
        session.draft_view.update(step=3, started=True)
        sidebar = doc.getCurrentController().getSidebar()
        sidebar.setVisible(True)
        decks = sidebar.getDecks()
        decks.getByName(DECK).activate(True)
        del decks
        decks = sidebar.getDecks()
        deck = decks.getByName(DECK)
        panels = deck.getPanels()
        out["live_panel"] = panels.getByName("LibreLexRedazionePanel").getId()
        del panels, deck, decks
        panel = panel_set.composite.panels["Drafting"]
        monitor = _monitor_dialog(ctx)
        _probe = _Probe(monitor, out, doc, sidebar, session, panel_set, panel)
        _probe.start()
        monitor.execute()
        monitor.dispose()
    except Exception:
        out["traceback"] = traceback.format_exc()
        out["done"] = True
        _write(out)


g_exportedScripts = (main,)
"""


def _install(soffice: str, profile: Path, oxt: str, result: Path) -> str:
    """Install (or, with ``oxt=""``, remove) the extension through a headless LibreOffice."""
    proc = subprocess.run(
        [soffice, f"-env:UserInstallation={profile.as_uri()}", "--headless", "--norestore",
         "--nologo", "vnd.sun.star.script:librelex_install.py$main?language=Python&location=user"],
        env={**os.environ, "LIBRELEX_OXT": oxt, "LIBRELEX_INSTALL_RESULT": str(result)},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
    assert result.exists(), f"install macro wrote nothing (exit code {proc.returncode})"
    return result.read_text(encoding="utf-8")


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _run_visible(soffice: str, profile: Path, env: dict, evidence: Path, timeout=300) -> dict:
    """Run the probe in a visible LibreOffice until its evidence says ``done``, then end it."""
    log_path = profile / "probe.log"
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [soffice, f"-env:UserInstallation={profile.as_uri()}", "--norestore", "--nologo",
             "vnd.sun.star.script:librelex_probe.py$main?language=Python&location=user"],
            env={**os.environ, **env}, stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + timeout
        try:
            while True:
                data = _read(evidence)
                if data.get("done"):
                    return data
                if proc.poll() is not None:
                    pytest.fail(f"LibreOffice exited {proc.returncode} at stage "
                                f"{data.get('stage')!r}: {data}\n"
                                f"{log_path.read_text(encoding='utf-8')[-20000:]}")
                if time.monotonic() > deadline:
                    pytest.fail(f"probe stuck at stage {data.get('stage')!r} after {timeout}s: "
                                f"{data}")
                time.sleep(0.5)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(15)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


def _scripted_turn(name: str, args: dict, call_id: str) -> list[dict]:
    return [*tool_call_response(name, args, call_id), chunk(usage=usage(900, 30))]


def test_drafting_through_the_real_sidebar(soffice, tmp_path):
    stub = StubLLM([
        _scripted_turn("chiedi_dati", {"domande": [{"campo": "sede",
                        "domanda": "Sede del tribunale?", "esempio": "Milano"}]}, "call_ask"),
        _scripted_turn("replace_text", {"query": "[SEDE]", "replacement": "MILANO"},
                       "call_sede"),
        _scripted_turn("redazione_completata", {"riepilogo": "Atto completato dal test."},
                       "call_done"),
    ])
    stub.start()
    profile = Path(tempfile.mkdtemp(prefix="librelex-gui-"))
    try:
        build = [sys.executable, str(REPO / "scripts" / "build_oxt.py"), "--out", str(tmp_path)]
        output = subprocess.run(build, capture_output=True, text=True, check=True).stdout
        oxt = Path(output.strip().splitlines()[-1])
        scripts = profile / "user" / "Scripts" / "python"
        scripts.mkdir(parents=True)
        shutil.copy(INSTALL_MACRO, scripts / "librelex_install.py")
        text = _install(soffice, profile, str(oxt), profile / "install.txt")
        assert text.splitlines()[0] == "OK", text

        uv = shutil.which("uv")
        assert uv, "uv is required to run the real bundled core in this test"
        config = profile / "config.toml"
        config.write_text(
            "[llm]\n"
            'preset = "custom"\n'
            f"base_url = {json.dumps(stub.base_url)}\n"
            'api_key = "test"\nmodel = "stub"\n\n'
            "[mcp_legal_it]\n"
            'mode = "local"\n'
            f"command = [{json.dumps(uv)}, \"run\", \"--project\", "
            f"{json.dumps(str(CORE))}, \"python\", "
            f"{json.dumps(str(CORE / 'tests/fake_legal_server.py'))}]\n\n"
            "[extension]\n"
            f"uv = {json.dumps(uv)}\n",
            encoding="utf-8")
        (scripts / "librelex_probe.py").write_text(PROBE_MACRO, encoding="utf-8")
        evidence = profile / "probe.json"
        data = _run_visible(soffice, profile, {"LIBRELEX_CHECK_RESULT": str(evidence),
                                               "LIBRELEX_CONFIG": str(config)}, evidence)

        assert "traceback" not in data, data["traceback"]
        assert data["live_panel"] == "LibreLexRedazionePanel"
        # reopening a drafting in progress: the replay reached the deck only afterwards
        assert data["restored_step"] == 3
        assert data["restored_callback_drained"] is True
        assert data["restored_title"] == "Redazione · 3/4 In corso"
        assert data["fresh_title"] == "Redazione · 1/4 Atto e dati"
        assert data["start_actions_expanded_before"] is True
        assert data["start_citations_expanded_before"] is True
        # step 1 → 3: title and collapse, each in its own later callback
        assert data["start_enabled"] is True
        assert data["start_submitted"] is True and data["start_step"] == 3
        assert data["title_after_start"] == "Redazione · 3/4 In corso"
        assert data["actions_collapsed_after_start"] is True
        assert data["citations_collapsed_after_start"] is True
        # the model asks, the lawyer answers, the act is completed in the document
        assert data["question"] == "Sede del tribunale?"
        assert data["title_after_question"] == "Redazione · 2/4 Domande"
        assert data["answer_step"] == 3
        assert data["finished_title"] == "Redazione · 4/4 Fine"
        assert data["draft_done"] is True and data["questions_remaining"] == []
        assert any("Base:" in title for title in data["partitions"])
        assert "MILANO" in data["document_text"] and "[SEDE]" not in data["document_text"]
        assert data["core_state"] == "ready"
        assert "shutdown_error" not in data, data["shutdown_error"]
        assert data["shutdown_seconds"] < 10
        assert len(stub.requests) == 3, [r["messages"][-1] for r in stub.requests]
    finally:
        stub.stop()
        shutil.rmtree(profile, ignore_errors=True)
