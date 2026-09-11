# -*- coding: utf-8 -*-
# Derived from LibreThinker (https://github.com/mihailthebuilder/librethinker-extension), MPL-2.0.
# This file stays under the Mozilla Public License 2.0.
"""Sidebar panel: XUIElement built on an XDL container window, controls added to the
container's own model (spec §5.1), bridge events delivered through AsyncCallback."""
import queue
from pathlib import Path

import uno
import unohelper
from com.sun.star.awt import Size, XActionListener, XCallback, XItemListener
from com.sun.star.lang import XComponent
from com.sun.star.ui import LayoutSize, XSidebarPanel, XToolPanel, XUIElement, XUIElementFactory
from com.sun.star.ui.UIElementType import TOOLPANEL
from com.sun.star.util.MeasureUnit import APPFONT

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
        self._width_du = layout.WIDTH
        self._controls = layout.CONTROLS

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
        """Re-flow the controls for the sidebar's current width and answer in pixels.

        The container window implements XUnitConversion, the only way to go from the pixels
        the sidebar speaks to the dialog units the control models use. Any failure there
        (no peer yet, an unsupported unit) falls back to the fixed 190-unit layout and the
        height the window was created with, which is what the panel did before.
        """
        try:
            du = max(layout.MIN_WIDTH,
                     self.window.convertSizeToLogic(Size(width, 0), APPFONT).Width)
            if du != self._width_du:
                self._width_du = du
                self._controls = layout.build(du)
                self._apply_layout(self._controls)
            h = self.window.convertSizeToPixel(
                Size(0, layout.total_height(self._controls)), APPFONT).Height
        except Exception:
            h = self._height or 700
        return LayoutSize(h, -1, h)

    def getMinimalWidth(self):
        return 240

    # --- XComponent -------------------------------------------------------------
    def dispose(self):
        if self.session is not None:
            session, self.session = self.session, None
            # Unbind first (our controls may already be half-disposed), then drain: events
            # queued before the panel went away must still reach the session, otherwise a
            # queued `final` would leave it busy until the user presses Annulla or the panel
            # is rebound. They land on the session's NullView, transcript and state, which is
            # exactly what a reopened panel replays.
            session.unbind()
            self._drain(session)

    def addEventListener(self, listener):
        pass

    def removeEventListener(self, listener):
        pass

    def disposing(self, event):
        pass

    # --- construction -----------------------------------------------------------
    def _build_controls(self):
        self._controls = layout.build(self._width_du)
        for c in self._controls:
            m = self.model.createInstance(f"com.sun.star.awt.UnoControl{c.kind}Model")
            m.Name = c.name
            m.PositionX, m.PositionY, m.Width, m.Height = c.x, c.y, c.w, c.h
            for k, v in c.props.items():
                if k != "Visible":       # not a model property: see _set_visible
                    m.setPropertyValue(k, v)
            self.model.insertByName(c.name, m)
        for c in self._controls:
            if "Visible" in c.props:
                self._set_visible(c.name, c.props["Visible"])
        for name, command in layout.ACTIONS.items():
            ctrl = self.window.getControl(name)
            ctrl.setActionCommand(command)
            ctrl.addActionListener(self)
        self.window.getControl("Citations").addItemListener(self)

    def _apply_layout(self, controls):
        """Move and resize the existing models after a width change.

        Geometry only: the progress bar's visibility belongs to set_progress.
        """
        for c in controls:
            m = self.model.getByName(c.name)
            m.PositionX, m.PositionY, m.Width, m.Height = c.x, c.y, c.w, c.h

    def _set_visible(self, name, visible):
        """Show or hide a control. The model has no `Visible` property (it is spelled
        `EnableVisible`), so go through the control's XWindow, as the panel window does."""
        self.window.getControl(name).setVisible(bool(visible))

    def _attach_session(self):
        model = self.frame.getController().getModel()
        ctx = self.ctx

        def make_session():
            adapter = DocumentAdapter(ctx, model)
            config = paths.read_config()

            def bridge_factory(on_event):
                try:
                    spec = paths.bridge_spec(package_dir(ctx), config)
                except Exception as e:
                    # UvNotFound carries a ready-made Italian message; anything else (a
                    # malformed config.toml, an unreadable path) must still reach the panel
                    # as a BridgeError rather than escape into the UNO listener.
                    raise BridgeError(str(e) or type(e).__name__) from e
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
        if self.session is not None:
            self._drain(self.session)

    def _drain(self, session):
        while True:
            try:
                ev = self.queue.get_nowait()
            except queue.Empty:
                return
            session.handle_event(ev)

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
        elif cmd == "show_text":
            # no reference typed: the core reads the selection (spec §7.3), so refuse early
            # when there is nothing to read rather than sending an empty request
            reference = self.window.getControl("Input").getText().strip()
            if not reference and not self.session.adapter.read_selection()["text"]:
                self.set_status("Scrivi un riferimento o seleziona un testo")
                return
            self.session.run_command("show_text", {"reference": reference} if reference else {})
        elif cmd == "list_citations":
            self.session.run_command("list_citations", {"scope": "document"})
        elif cmd == "cancel":
            self.session.cancel()
        elif cmd == "clear":
            self.session.clear_transcript()
        elif cmd == "settings":
            created = paths.write_template_if_missing()
            self.session.note(f"File di configurazione: {paths.config_path()}"
                              + (" (creato ora)" if created else "")
                              + f"\nLog del core: {paths.config_path().parent / 'core-stderr.log'}"
                              "\nModifica il file con un editor di testo e riavvia LibreOffice.")

    def itemStateChanged(self, event):          # XItemListener: citation selected
        if self.session is not None:
            self.session.select_citation(self.window.getControl("Citations").getSelectedItemPos())

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

    def set_citations(self, labels):
        self.model.getByName("Citations").StringItemList = tuple(labels)
        self.model.getByName("CitationsLabel").Label = f"Citazioni ({len(labels)})"

    def set_progress(self, done, total):
        """Show the bar at done/total; ``total`` None (or zero) hides it again."""
        if not total:
            self._set_visible("Progress", False)
            return
        m = self.model.getByName("Progress")
        m.ProgressValueMax = total
        m.ProgressValue = max(0, min(done, total))
        self._set_visible("Progress", True)
