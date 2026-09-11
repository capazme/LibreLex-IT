# -*- coding: utf-8 -*-
# Derived from LibreThinker (https://github.com/mihailthebuilder/librethinker-extension), MPL-2.0.
# This file stays under the Mozilla Public License 2.0.
"""Sidebar panel: XUIElement built on an XDL container window, controls added to the
container's own model (spec §5.1), bridge events delivered through AsyncCallback."""
import queue
from pathlib import Path

import uno
import unohelper
from com.sun.star.awt import XActionListener, XCallback, XItemListener
from com.sun.star.lang import XComponent
from com.sun.star.ui import LayoutSize, XSidebarPanel, XToolPanel, XUIElement, XUIElementFactory
from com.sun.star.ui.UIElementType import TOOLPANEL

from librelex_ext import EXTENSION_ID, layout, paths, registry
from librelex_ext.bridge import Bridge, BridgeError
from librelex_ext.document import DocumentAdapter, has_markdown_filter, lo_version
from librelex_ext.session import Session

PANEL_URL = "private:resource/toolpanel/LibreLexPanelFactory/Panel"
XDL_URL = f"vnd.sun.star.extension://{EXTENSION_ID}/dialogs/panel.xdl"
MAX_TRANSCRIPT = 40_000


def package_dir(ctx) -> Path:
    """Install directory of the .oxt, else the source checkout (development)."""
    try:
        pip = ctx.getValueByName("/singletons/com.sun.star.deployment.PackageInformationProvider")
        url = pip.getPackageLocation(EXTENSION_ID)
        if url:
            return Path(uno.fileUrlToSystemPath(url))
    except Exception:
        pass
    return Path(__file__).resolve().parents[1]


class PanelFactory(unohelper.Base, XUIElementFactory):
    def __init__(self, ctx):
        self.ctx = ctx

    def createUIElement(self, url, args):
        frame = parent = None
        for a in args:
            if a.Name == "Frame":
                frame = a.Value
            elif a.Name == "ParentWindow":
                parent = a.Value
        registry.ensure_terminate_listener(self.ctx)
        panel = Panel(self.ctx, frame, parent, url)
        panel.getRealInterface()
        panel.Window.Visible = True
        return panel


class Panel(unohelper.Base, XUIElement, XToolPanel, XSidebarPanel, XComponent,
            XActionListener, XItemListener, XCallback):
    def __init__(self, ctx, frame, parent, url):
        self.ctx, self.frame, self.parent, self.url = ctx, frame, parent, url
        self.window = None
        self.model = None
        self.queue: queue.Queue = queue.Queue()
        self.async_cb = ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.awt.AsyncCallback", ctx)
        self.session = None
        self._height = 0

    # --- XUIElement ------------------------------------------------------------
    def getRealInterface(self):
        if self.window is None:
            provider = self.ctx.ServiceManager.createInstanceWithContext(
                "com.sun.star.awt.ContainerWindowProvider", self.ctx)
            self.window = provider.createContainerWindow(XDL_URL, "", self.parent, None)
            self.model = self.window.getModel()          # never setModel (spec §5.1)
            self._build_controls()
            self._height = self.window.getPosSize().Height
            self._attach_session()
        return self

    @property
    def Frame(self):
        return self.frame

    @property
    def ResourceURL(self):
        return self.url

    @property
    def Type(self):
        return TOOLPANEL

    # --- XToolPanel / XSidebarPanel --------------------------------------------
    @property
    def Window(self):
        return self.window

    def createAccessible(self, parent):
        return self

    def getHeightForWidth(self, width):
        h = self._height or 700
        return LayoutSize(h, -1, h)

    def getMinimalWidth(self):
        return 240

    # --- XComponent -------------------------------------------------------------
    def dispose(self):
        if self.session is not None:
            self.session.unbind()
            self.session = None

    def addEventListener(self, listener):
        pass

    def removeEventListener(self, listener):
        pass

    def disposing(self, event):
        pass

    # --- construction -----------------------------------------------------------
    def _build_controls(self):
        for c in layout.CONTROLS:
            m = self.model.createInstance(f"com.sun.star.awt.UnoControl{c.kind}Model")
            m.Name = c.name
            m.PositionX, m.PositionY, m.Width, m.Height = c.x, c.y, c.w, c.h
            for k, v in c.props.items():
                m.setPropertyValue(k, v)
            self.model.insertByName(c.name, m)
        for name, command in layout.ACTIONS.items():
            ctrl = self.window.getControl(name)
            ctrl.setActionCommand(command)
            ctrl.addActionListener(self)
        self.window.getControl("Problems").addItemListener(self)

    def _attach_session(self):
        model = self.frame.getController().getModel()
        ctx = self.ctx

        def make_session():
            adapter = DocumentAdapter(ctx, model)
            config = paths.read_config()

            def bridge_factory(on_event):
                try:
                    spec = paths.bridge_spec(package_dir(ctx), config)
                except paths.UvNotFound as e:
                    raise BridgeError(str(e)) from e
                return Bridge(spec, on_event)

            return Session(adapter, bridge_factory, doc_id=model.RuntimeUID,
                           lo_version=lo_version(ctx), has_markdown_filter=has_markdown_filter(ctx),
                           config_path=str(paths.config_path()))

        self.session = registry.session_for(model, make_session)
        self.session.bind(self, self._post)
        if not self.session.transcript:
            created = paths.write_template_if_missing()
            self.session.note(f"LibreLex-IT pronto. Configurazione: {paths.config_path()}"
                              + (" (creata ora con i valori predefiniti)" if created else ""))
            if not self.session.has_markdown_filter:
                self.session.note(
                    "Attenzione: questa versione di LibreOffice non ha il filtro Markdown "
                    "(serve 26.2 o successiva): l'inserimento di testo non funzionerà.")

    # --- bridge events: reader thread → UI thread ----------------------------------
    def _post(self, event):
        self.queue.put(event)
        self.async_cb.addCallback(self, None)

    def notify(self, data):                      # XCallback, UI thread
        if self.session is None:
            return
        while True:
            try:
                ev = self.queue.get_nowait()
            except queue.Empty:
                return
            self.session.handle_event(ev)

    # --- user actions -----------------------------------------------------------------
    def actionPerformed(self, event):           # XActionListener, UI thread
        if self.session is None:
            return
        cmd = event.ActionCommand
        if cmd == "verify_document":
            self.session.run_command("verify_citations", {"scope": "document"})
        elif cmd == "verify_selection":
            if not self.session.adapter.read_selection()["text"]:
                self.set_status("Seleziona prima il testo da verificare")
                return
            self.session.run_command("verify_citations", {"scope": "selection"})
        elif cmd == "insert_norm":
            reference = self.window.getControl("Input").getText().strip()
            self.session.run_command("insert_norm", {"reference": reference} if reference else {})
        elif cmd == "cancel":
            self.session.cancel()
        elif cmd == "settings":
            created = paths.write_template_if_missing()
            self.session.note(f"File di configurazione: {paths.config_path()}"
                              + (" (creato ora)" if created else "")
                              + f"\nLog del core: {paths.config_path().parent / 'core-stderr.log'}"
                              "\nModifica il file con un editor di testo e riavvia LibreOffice.")

    def itemStateChanged(self, event):          # XItemListener: problem selected
        if self.session is not None:
            self.session.goto_problem(self.window.getControl("Problems").getSelectedItemPos())

    # --- View protocol (session → controls) ---------------------------------------------
    def append(self, text):
        ctrl = self.window.getControl("Transcript")
        current = ctrl.getText()
        new = (current + ("\n" if current else "") + text)[-MAX_TRANSCRIPT:]
        ctrl.setText(new)

    def set_transcript(self, text):
        self.window.getControl("Transcript").setText(text[-MAX_TRANSCRIPT:])

    def set_status(self, text):
        self.model.getByName("Status").Label = text

    def set_busy(self, busy):
        for name in layout.BUSY_DISABLED:
            self.model.getByName(name).Enabled = not busy
        self.model.getByName("Cancel").Enabled = bool(busy)

    def set_problems(self, labels):
        self.model.getByName("Problems").StringItemList = tuple(labels)
