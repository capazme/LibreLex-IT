# -*- coding: utf-8 -*-
# Derived from LibreThinker (https://github.com/mihailthebuilder/librethinker-extension), MPL-2.0.
# This file stays under the Mozilla Public License 2.0.
"""Sidebar panels: one XUIElement per deck panel (Azioni, Citazioni, Risposte), each built on
an XDL container window whose own model holds the controls of its kind (spec §5.1). The three
panels of a document share one Session through the registry's PanelSet, which also delivers
the bridge events to the UI thread through AsyncCallback."""
from pathlib import Path

import uno
import unohelper
from com.sun.star.awt import Size, XActionListener, XItemListener, XWindowListener
from com.sun.star.lang import XComponent
from com.sun.star.ui import LayoutSize, XSidebarPanel, XToolPanel, XUIElement, XUIElementFactory
from com.sun.star.ui.UIElementType import TOOLPANEL
from com.sun.star.util.MeasureUnit import APPFONT

from librelex_ext import EXTENSION_ID, layout, paths, registry, views
from librelex_ext.bridge import Bridge, BridgeError
from librelex_ext.document import DocumentAdapter, has_markdown_filter, lo_version
from librelex_ext.render import render_consent
from librelex_ext.session import Session

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


def make_session_factory(ctx, model):
    """The zero-argument factory the registry calls to create this document's Session.

    The first-run banner is written here, right after the Session: it belongs to the document,
    not to a panel, so it is emitted once whichever of the three panels opens first and it
    survives every panel being closed (it lives in ``Session.transcript``).
    """

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

        session = Session(adapter, bridge_factory, doc_id=model.RuntimeUID,
                          lo_version=lo_version(ctx), has_markdown_filter=has_markdown_filter(ctx),
                          config_path=str(paths.config_path()))
        created = paths.write_template_if_missing()
        session.note(f"LibreLex-IT pronto. Configurazione: {paths.config_path()}"
                     + (" (creata ora con i valori predefiniti)" if created else ""))
        if not session.has_markdown_filter:
            session.note(
                "Attenzione: questa versione di LibreOffice non ha il filtro Markdown "
                "(serve 26.2 o successiva): l'inserimento di testo non funzionerà.")
        return session

    return make_session


class PanelFactory(unohelper.Base, XUIElementFactory):
    def __init__(self, ctx):
        self.ctx = ctx

    def createUIElement(self, url, args):
        kind = views.panel_kind(url)     # raises: the sidebar only asks for the three URLs
        frame = parent = None
        for a in args:
            if a.Name == "Frame":
                frame = a.Value
            elif a.Name == "ParentWindow":
                parent = a.Value
        registry.ensure_terminate_listener(self.ctx)
        panel = Panel(self.ctx, frame, parent, url, kind)
        panel.getRealInterface()
        panel.Window.Visible = True
        return panel


class Panel(unohelper.Base, XUIElement, XToolPanel, XSidebarPanel, XComponent,
            XActionListener, XItemListener, XWindowListener):
    """One panel of the deck. Its ``kind`` decides which controls it builds, which listeners
    it registers and which of the nine View methods actually do something: each one is a no-op
    when its control belongs to another panel, so a misrouted call can never raise inside a
    UNO listener."""

    def __init__(self, ctx, frame, parent, url, kind):
        self.ctx, self.frame, self.parent, self.url = ctx, frame, parent, url
        self.kind = kind
        self.window = None
        self.model = None
        self.panel_set = None
        self.session = None
        self._height = 0
        self._width_du = layout.WIDTH
        self._controls = layout.CONTROLS[kind]

    # --- XUIElement ------------------------------------------------------------
    def getRealInterface(self):
        if self.window is None:
            provider = self.ctx.ServiceManager.createInstanceWithContext(
                "com.sun.star.awt.ContainerWindowProvider", self.ctx)
            self.window = provider.createContainerWindow(XDL_URL, "", self.parent, None)
            self.model = self.window.getModel()          # never setModel (spec §5.1)
            self._build_controls()
            self._height = self.window.getPosSize().Height
            if self.kind == "Answers":
                # the transcript is the only control that grows with the deck: follow the
                # height the sidebar gives us (see windowResized)
                self.window.addWindowListener(self)
            self._attach_panel_set()
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
        (no peer yet, an unsupported unit) falls back to the height the window was created
        with, which is what the panel did before.

        Azioni and Citazioni are as tall as their controls and no taller; Risposte asks for a
        minimum and a preferred height with no maximum (``-1``), so the sidebar gives it
        whatever is left of the deck.
        """
        try:
            du = max(layout.MIN_WIDTH,
                     self.window.convertSizeToLogic(Size(width, 0), APPFONT).Width)
            if du != self._width_du:
                self._width_du = du
                self._controls = layout.build(self.kind, du)
                self._apply_layout(self._controls)
            if self.kind == "Answers":
                fixed = layout.SMALL_BUTTON_H + 3 * layout.MARGIN   # Svuota + the two margins
                return LayoutSize(self._pixels(layout.TRANSCRIPT_MIN_H + fixed), -1,
                                  self._pixels(layout.TRANSCRIPT_H + fixed))
            h = self._pixels(layout.total_height(self._controls))
        except Exception:
            h = self._height or 700
            if self.kind == "Answers":
                return LayoutSize(h, -1, h)
        return LayoutSize(h, h, h)

    def getMinimalWidth(self):
        """Narrowest deck the panel can live in, in pixels: the layout's own minimum.

        ``layout.build`` clamps at ``MIN_WIDTH`` dialog units and never re-flows below it,
        so answering less would let the sidebar clip the right-hand button column. Same
        conversion caveat as ``getHeightForWidth``: without a peer there is no unit
        conversion, and the fallback is MIN_WIDTH at a typical 8x16 appfont.
        """
        try:
            return self.window.convertSizeToPixel(Size(layout.MIN_WIDTH, 0), APPFONT).Width
        except Exception:
            return 280

    # --- XWindowListener (Risposte only) ----------------------------------------
    def windowResized(self, event):
        """Stretch the transcript to whatever height the sidebar just gave the panel."""
        if self.window is None or self.model is None or not self.model.hasByName("Transcript"):
            return
        try:
            du = self.window.convertSizeToLogic(
                Size(0, self.window.getPosSize().Height), APPFONT).Height
        except Exception:
            return                       # no peer: keep the height the layout table gave it
        top = layout.MARGIN + layout.SMALL_BUTTON_H + layout.GAP
        self.model.getByName("Transcript").Height = max(layout.TRANSCRIPT_MIN_H,
                                                        du - top - layout.MARGIN)

    def windowMoved(self, event):
        pass

    def windowShown(self, event):
        pass

    def windowHidden(self, event):
        pass

    # --- XComponent -------------------------------------------------------------
    def dispose(self):
        """The panel is gone; the PanelSet is not: it keeps delivering events to the session
        (a queued `final` still lands on the transcript a reopened panel replays)."""
        if self.panel_set is not None:
            self.panel_set.composite.detach(self.kind)
        self.panel_set = None
        self.session = None

    def addEventListener(self, listener):
        pass

    def removeEventListener(self, listener):
        pass

    def disposing(self, event):
        pass

    # --- construction -----------------------------------------------------------
    def _build_controls(self):
        self._controls = layout.build(self.kind, self._width_du)
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
            if not self.model.hasByName(name):
                continue                 # a button of another panel of the deck
            ctrl = self.window.getControl(name)
            ctrl.setActionCommand(command)
            ctrl.addActionListener(self)
        if self.model.hasByName("Citations"):
            self.window.getControl("Citations").addItemListener(self)

    def _apply_layout(self, controls):
        """Move and resize the existing models after a width change.

        Geometry only: the progress bar's visibility belongs to set_progress, and the
        transcript's height to windowResized.
        """
        for c in controls:
            m = self.model.getByName(c.name)
            m.PositionX, m.PositionY, m.Width = c.x, c.y, c.w
            if c.name != "Transcript":
                m.Height = c.h

    def _set_visible(self, name, visible):
        """Show or hide a control. The model has no `Visible` property (it is spelled
        `EnableVisible`), so go through the control's XWindow, as the panel window does."""
        self.window.getControl(name).setVisible(bool(visible))

    def _pixels(self, du):
        return self.window.convertSizeToPixel(Size(0, du), APPFONT).Height

    def _attach_panel_set(self):
        model = self.frame.getController().getModel()
        self.panel_set = registry.panel_set_for(self.ctx, model,
                                                make_session_factory(self.ctx, model))
        self.session = self.panel_set.session
        self.panel_set.composite.attach(self.kind, self)
        self._replay(self.session)

    def _replay(self, session):
        """Show the state the session kept while this panel was closed (spec §5.1)."""
        if self.kind == "Answers":
            self.set_transcript("\n".join(session.transcript))
        elif self.kind == "Citations":
            self.set_citations([label for label, _, _ in session.citations])
        else:
            busy = session.state in ("starting", "busy")
            self.set_busy(busy)
            if busy:                        # else the layout default "Pronto" would lie
                self.set_status("Richiesta in corso...")
            # a panel rebuilt mid-turn (deck switch, collapse/expand) is created empty: the
            # question the core is still waiting on and the last usage line have to come back
            self.set_consent(session.consent_summary)
            self.set_usage(session.usage_text)

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
        elif cmd == "send":
            ctrl = self.window.getControl("Input")
            message = ctrl.getText().strip()
            busy = self.session.state == "busy"     # chat() would refuse a second request
            self.session.chat(message)
            # Clear only what the session took: a blank message, a refused one and a core
            # that could not even start (state back to "stopped") all keep the typed text.
            if message and not busy and self.session.state != "stopped":
                ctrl.setText("")
        elif cmd == "research":
            self.session.research(self.window.getControl("Input").getText().strip())
        elif cmd == "draft":
            ctrl = self.window.getControl("Input")
            message = ctrl.getText().strip()
            busy = self.session.state == "busy"
            self.session.draft(message)
            if message and not busy and self.session.state != "stopped":
                ctrl.setText("")            # same rule as "send": clear only what was taken
        elif cmd.startswith("consent_"):        # consent_document/consent_once/consent_deny
            self.session.answer_consent(cmd[len("consent_"):])
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
        elif cmd == "clear":                    # the Svuota button of the Risposte panel
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
        if not self.model.hasByName("Transcript"):
            return
        ctrl = self.window.getControl("Transcript")
        current = ctrl.getText()
        new = (current + ("\n" if current else "") + text)[-MAX_TRANSCRIPT:]
        ctrl.setText(new)

    def set_transcript(self, text):
        if self.model.hasByName("Transcript"):
            self.window.getControl("Transcript").setText(text[-MAX_TRANSCRIPT:])

    def append_stream(self, text):
        """Append a streamed chunk with no separator: the core sends a continuous text."""
        if not self.model.hasByName("Transcript"):
            return
        ctrl = self.window.getControl("Transcript")
        ctrl.setText((ctrl.getText() + text)[-MAX_TRANSCRIPT:])

    def set_status(self, text):
        if self.model.hasByName("Status"):
            self.model.getByName("Status").Label = text

    def set_busy(self, busy):
        for name in layout.BUSY_DISABLED:
            if self.model.hasByName(name):
                self.model.getByName(name).Enabled = not busy
        if self.model.hasByName("Cancel"):
            self.model.getByName("Cancel").Enabled = bool(busy)

    def set_citations(self, labels):
        if self.model.hasByName("Citations"):
            self.model.getByName("Citations").StringItemList = tuple(labels)

    def set_usage(self, text):
        if self.model.hasByName("Usage"):
            self.model.getByName("Usage").Label = text

    def set_consent(self, summary):
        """Show the consent block for ``summary``, or hide it again when it is None.

        The four controls keep their slot in the layout table either way (spec §8.2), so the
        question appears and disappears without moving the rest of the panel.
        """
        if not self.model.hasByName("ConsentText"):
            return
        if summary is not None:
            self.model.getByName("ConsentText").Label = render_consent(summary)
        self._set_visible("ConsentText", summary is not None)
        for name in layout.CONSENT_BUTTONS:
            self._set_visible(name, summary is not None)

    def set_progress(self, done, total):
        """Show the bar at done/total; ``total`` None (or zero) hides it again."""
        if not self.model.hasByName("Progress"):
            return
        if not total:
            self._set_visible("Progress", False)
            return
        m = self.model.getByName("Progress")
        m.ProgressValueMax = total
        m.ProgressValue = max(0, min(done, total))
        self._set_visible("Progress", True)
