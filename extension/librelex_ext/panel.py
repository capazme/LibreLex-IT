# -*- coding: utf-8 -*-
# Derived from LibreThinker (https://github.com/mihailthebuilder/librethinker-extension), MPL-2.0.
# This file stays under the Mozilla Public License 2.0.
"""Sidebar panels: one XUIElement per deck panel (Azioni, Redazione, Citazioni, Risposte), each
built on an XDL container window whose own model holds the controls of its kind (spec §5.1).
The panels of a document share one Session through the registry's PanelSet, which also
delivers the bridge events to the UI thread through AsyncCallback."""
from __future__ import annotations

import os
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote

import uno
import unohelper
from com.sun.star.awt import Size, XActionListener, XCallback, XItemListener, XWindowListener
from com.sun.star.datatransfer.dnd import XDropTargetListener
from com.sun.star.lang import XComponent
from com.sun.star.ui import LayoutSize, XSidebarPanel, XToolPanel, XUIElement, XUIElementFactory
from com.sun.star.ui.dialogs.TemplateDescription import FILEOPEN_SIMPLE
from com.sun.star.ui.UIElementType import TOOLPANEL
from com.sun.star.util.MeasureUnit import APPFONT

from librelex_ext import EXTENSION_ID, layout, letterheads, paths, registry, views
from librelex_ext.bridge import Bridge, BridgeError
from librelex_ext.document import (
    DocumentActionError,
    DocumentAdapter,
    has_markdown_filter,
    lo_version,
    make_letterhead,
    read_document,
)
from librelex_ext.render import (
    render_consent,
    render_draft_consent_status,
    render_field_label,
    render_question_label,
    render_questions_hint,
    render_template_notes,
)
from librelex_ext.session import Session, drop_role

XDL_URL = f"vnd.sun.star.extension://{EXTENSION_ID}/dialogs/panel.xdl"
MAX_TRANSCRIPT = 40_000

# the similar-case file: what the picker offers and what a drop has to carry (design §5.2)
REFERENCE_FILTER = ("Atti (odt, docx, rtf, txt)", "*.odt;*.docx;*.rtf;*.txt")
# case documents (design §4) and letterhead sources (design §5.2): the other two file pickers
# the Redazione panel offers, besides the similar-case one above
ATTACHMENT_FILTER = ("Documenti del caso (pdf, odt, docx, doc, rtf, txt)",
                    "*.pdf;*.odt;*.docx;*.doc;*.rtf;*.txt")
LETTERHEAD_FILTER = ("Carta intestata (odt, docx, doc)", "*.odt;*.docx;*.doc")
URI_LIST = "text/uri-list"
DROP_UNAVAILABLE = "Trascinamento non disponibile su questo LibreOffice: usa Sfoglia…"
DROP_REFUSED = "Trascina un file locale (pdf, odt, docx, doc, rtf, txt)"
DROP_ONE_AT_A_TIME = "Un file alla volta: preso il primo, trascina gli altri dopo"
EXTRA_FIELDS = "Altri campi (scrivili nelle note): "


def collect_fields(names: list[str], values: list[str]) -> dict[str, str]:
    """Pair the field/question names of the visible rows with what was typed in them.

    Empty rows are left out rather than sent as "": the core tells a field it was not given
    from a field the lawyer deliberately emptied only by its absence.
    """
    out: dict[str, str] = {}
    for name, value in zip(names, values, strict=False):
        text = (value or "").strip()
        if text:
            out[name] = text
    return out


def file_uris(data) -> list[str]:
    """Every ``file://`` line of a dropped ``text/uri-list`` payload, in order.

    The payload is a UTF-8 byte sequence (pyuno hands it over as ``uno.ByteSequence``, whose
    ``value`` is bytes) on most platforms and a plain string on some; anything else, and any
    line that names no local file (a dragged web link), is left out.
    """
    if not isinstance(data, str):
        data = getattr(data, "value", data)          # uno.ByteSequence -> bytes
        if not isinstance(data, (bytes, bytearray)):
            return []
        try:
            data = bytes(data).decode("utf-8")
        except UnicodeDecodeError:
            return []
    return [line.strip() for line in data.splitlines() if line.strip().startswith("file://")]


def assign_tab_order(model, controls) -> None:
    """Set TabIndex/Tabstop on the models of ``controls``, already inserted into ``model``
    under their own names (design review §5 item 10): table order becomes tab order, a label
    or a bar is never a tab stop, and no control is ever a DefaultButton.

    ``UnoControlFixedLineModel`` and ``UnoControlProgressBarModel`` have no ``Tabstop``
    property at all (a UNO probe: ``getPropertySetInfo().hasPropertyByName("Tabstop")`` is
    False), so it is left untouched for them rather than assigned and made to raise
    ``AttributeError``; ``suppress(Exception)`` is a belt in case another kind turns out the
    same way.
    """
    for i, c in enumerate(controls):
        m = model.getByName(c.name)
        m.TabIndex = i
        if c.kind in ("FixedLine", "ProgressBar"):
            continue
        with suppress(Exception):
            m.Tabstop = c.kind != "FixedText"


def _default_label(kind: str, name: str) -> str:
    """The Label the layout table gives a control, so the panel can put the same copy back
    without owning a second copy of it."""
    for c in layout.CONTROLS[kind]:
        if c.name == name:
            return str(c.props.get("Label", ""))
    return ""


QUESTIONS_HINT = _default_label("Drafting", "QuestionsHint")

# the panel title per step (design review §5 item 6), and the control each step focuses when
# it becomes current (item 10); shared by set_step and the consent-modal override of item 8
_STEP_TITLES = {1: "Redazione · 1/4 Atto e dati", 2: "Redazione · 2/4 Domande",
                3: "Redazione · 3/4 In corso", 4: "Redazione · 4/4 Fine"}
_STEP_FOCUS = {1: "TemplateSearch", 2: "Answer1", 3: "DraftCancel", 4: "ResumeInput"}

# rows whose Visible is owned by set_template/set_questions, never by the blanket per-step
# show/hide of _apply_drafting_state (design review §5, the step switch): forcing them all
# visible on entering a step would undo what those two just hid for the rows with no content
_DYNAMIC_ROWS = frozenset(
    [f"FieldLabel{n}" for n in range(1, layout.FIELD_ROWS + 1)]
    + [f"Field{n}" for n in range(1, layout.FIELD_ROWS + 1)]
    + [f"QuestionLabel{n}" for n in range(1, layout.FIELD_ROWS + 1)]
    + [f"Answer{n}" for n in range(1, layout.FIELD_ROWS + 1)])


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
            XActionListener, XItemListener, XWindowListener, XDropTargetListener,
            XCallback):
    """One panel of the deck. Its ``kind`` decides which controls it builds, which listeners
    it registers and which of the View methods actually do something: each one is a no-op
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
        # names of the rows currently shown, in row order: what collect_fields keys the
        # typed text with when Avvia redazione / Continua is pressed
        self._field_names: list[str] = []
        self._question_fields: list[str] = []
        # True while the panel itself is rewriting a list box, so the selection change that
        # follows is not mistaken for a click and sent to the session
        self._quiet_items = False
        # the two flags Avvia redazione / Rimuovi depend on, besides the busy state
        self._template_set = False
        self._reference_present = False
        self._busy = False
        # the drafting workbench (design §3, §4): which of the four steps is current, whether
        # a Redazione-side consent is pending (design review §5 item 8), and how many
        # attachment rows are shown. ``_letterhead_entries`` is reserved for a future task:
        # the View protocol's ``set_letterheads`` only ever hands the panel rendered labels
        # and a selected index (session.py owns the raw entries), never the entries themselves.
        self._step = 1
        self._consent_pending = False
        self._attachment_count = 0
        self._letterhead_entries: list[dict] = []
        # what the last set_draft_status call actually said: the label under a pending
        # consent, which set_draft_status must not overwrite (item 8); restored once the
        # consent is answered or cleared
        self._draft_status_text = ""
        self._draft_status_started = False
        # sidebar API calls (setTitle, collapse) queued until the sidebar callback that
        # triggered them has returned: see _sidebar_later
        self._sidebar_ops = []
        self._async_cb = None

    # --- XUIElement ------------------------------------------------------------
    def getRealInterface(self):
        if self.window is None:
            provider = self.ctx.ServiceManager.createInstanceWithContext(
                "com.sun.star.awt.ContainerWindowProvider", self.ctx)
            self.window = provider.createContainerWindow(XDL_URL, "", self.parent, None)
            self.model = self.window.getModel()          # never setModel (spec §5.1)
            self._build_controls()
            self._height = self.window.getPosSize().Height
            self._log_metrics()
            if self.kind == "Answers":
                # the transcript is the only control that grows with the deck: follow the
                # height the sidebar gives us (see windowResized)
                self.window.addWindowListener(self)
            self._attach_panel_set()
            if self.kind == "Drafting":
                # after the session: a fresh disk scan of the letterhead folder, so templates
                # another lawyer (or a previous run of this one) registered show up without
                # waiting for the next add/remove; a bad or missing folder must not break the
                # panel, hence the one suppress around the whole thing
                with suppress(Exception):
                    self.session.set_letterheads(letterheads.list_letterheads())
                # a LibreOffice without a drop target says so in the transcript, which only
                # exists once the panel set is attached
                self._install_drop_target()
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
        if self.session is not None:
            # What the lawyer typed and has not sent is state too (design §6.2): hand it to
            # the session before the controls go away, so the panel the sidebar builds next
            # gets it back through replay_drafting. Never let a failure here (a control
            # already torn down by the toolkit) stop the detach below.
            with suppress(Exception):
                self._store_typed_values()
        if self.panel_set is not None:
            self.panel_set.composite.detach(self.kind)
        self.panel_set = None
        self.session = None
        self._sidebar_ops = []

    def _store_typed_values(self):
        """Push the Redazione panel's rows into the session's drafting state (fields, notes
        and answers: the same panel now holds every step, so all three go together); no-op
        for the other kinds."""
        if self.kind != "Drafting":
            return
        draft = self.session.draft_view
        draft["fields"] = collect_fields(self._field_names,
                                         self._row_texts("Field", self._field_names))
        draft["notes"] = self.window.getControl("Notes").getText()
        draft["answers_draft"] = collect_fields(
            self._question_fields, self._row_texts("Answer", self._question_fields))

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
        # Keyboard (design review §5 item 10): table order becomes tab order, applied once
        # every model is inserted (assign_tab_order only looks each up by name).
        assign_tab_order(self.model, self._controls)
        for c in self._controls:
            if "Visible" in c.props:
                self._set_visible(c.name, c.props["Visible"])
        for name, command in layout.ACTIONS.items():
            if not self.model.hasByName(name):
                continue                 # a button of another panel of the deck
            ctrl = self.window.getControl(name)
            ctrl.setActionCommand(command)
            ctrl.addActionListener(self)
        for name in ("Citations", "Template", "Partitions", "Expected", "Attachments",
                    "Letterhead"):
            if self.model.hasByName(name):
                self.window.getControl(name).addItemListener(self)

    def _log_metrics(self):
        """One line of ``panel-metrics.log`` per panel creation, best effort (design review
        §5 item 13): the field test's diagnostic of how the sidebar sized this panel."""
        with suppress(Exception):
            path = paths.config_path().parent / "panel-metrics.log"
            paths.ensure_private(path)
            du436 = self.window.convertSizeToPixel(Size(0, 436), APPFONT).Height
            deck_px = self.window.getPosSize().Height
            line = (f"{self.kind} {datetime.now(UTC).isoformat()} "
                    f"du436px={du436} deck_px={deck_px} width_du={self._width_du}\n")
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                f.write(line)
            paths.ensure_private(path)

    def _install_drop_target(self):
        """Let the Redazione panel take a similar-case file dropped on it (design §5.2).

        The toolkit's drop target is optional: where it is missing (or the peer has none
        yet), the panel keeps working and the transcript points at the Sfoglia… button.
        """
        try:
            toolkit = self.ctx.ServiceManager.createInstanceWithContext(
                "com.sun.star.awt.Toolkit", self.ctx)
            target = toolkit.getDropTarget(self.window.getPeer())
            target.addDropTargetListener(self)
            target.setActive(True)
        except Exception:
            if self.session is not None:
                self.session.note(DROP_UNAVAILABLE)

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
        # F6: the loop above put Continue back at its table position, undoing what
        # set_questions had moved it to (design review §5 item 12); only a resize runs this
        # method, so the number of visible question rows never changed under it.
        if self.model.hasByName("Continue"):
            self.model.getByName("Continue").PositionY = layout.continue_y(
                len(self._question_fields))

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
        elif self.kind == "Drafting":
            # exactly what Session.bind replays, through the session's one replay path: the
            # calls this panel has no controls for are no-ops (see the View methods below)
            session.replay_drafting(self)
            # after the state calls: _apply_enabled then settles Start and Rimuovi from both
            # the replayed state and the busy flag, whichever order they arrived in
            self.set_busy(session.state in ("starting", "busy"))
            # F4: set_consent is a broadcast (views.CompositeView.BROADCAST), so a consent
            # that landed before this panel attached never reached it; a Redazione panel
            # rebuilt while one pends (design review §5 item 8) has to come back modal too.
            self.set_consent(session.consent_summary)
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
        elif cmd == "template_search":
            self.session.templates(self.window.getControl("TemplateSearch").getText())
        elif cmd == "reference_browse":
            url = self._pick_file(REFERENCE_FILTER)
            if url:
                self._load_reference(url)
        elif cmd == "reference_clear":
            self.session.clear_reference()
        elif cmd == "attachment_add":
            url = self._pick_file(ATTACHMENT_FILTER)
            if url:
                self._load_attachment(url)
        elif cmd == "attachment_remove":
            index = self._selected_index("Attachments")
            if index is not None:
                self.session.remove_attachment(index)
        elif cmd == "letterhead_add":
            url = self._pick_file(LETTERHEAD_FILTER)
            if url:
                self._add_letterhead(url)
        elif cmd == "draft_new":
            self.session.new_drafting()
        elif cmd == "draft_start":
            template = self.session.draft_view.get("template") or {}
            fields = collect_fields(self._field_names, self._row_texts("Field",
                                                                       self._field_names))
            self.session.draft_start(template.get("tipo_atto", ""), fields,
                                     self.window.getControl("Notes").getText().strip())
        elif cmd == "draft_answer":
            answers = collect_fields(self._question_fields,
                                     self._row_texts("Answer", self._question_fields))
            self.session.draft_answer(answers)
        elif cmd == "draft_resume":
            ctrl = self.window.getControl("ResumeInput")
            message = ctrl.getText().strip()
            # same rule as "send": clear only what the session actually took (a drafting
            # that never started, a busy core and a core that could not start all keep it)
            taken = (self.session.draft_view["started"] and self.session.state != "busy")
            self.session.draft_continue(message)
            if taken and self.session.state != "stopped":
                ctrl.setText("")
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

    def itemStateChanged(self, event):          # XItemListener: a list box row was picked
        """Citations, Template, Partitions, Expected, Attachments and Letterhead share this
        listener; the model name of the control that fired says which list the selection came
        from, with Citations (the one panel with a single list box) as the fallback when the
        source cannot be identified."""
        if self.session is None or self._quiet_items:
            return
        name = ""
        try:
            name = event.Source.getModel().Name
        except Exception:
            pass
        if not self.model.hasByName(name):
            if not self.model.hasByName("Citations"):
                return
            name = "Citations"
        if name == "Attachments":
            # no jump, no session call: only Rimuovi's enabled state depends on the selection
            self._apply_enabled()
            return
        try:
            index = self.window.getControl(name).getSelectedItemPos()
        except Exception:
            return
        if name == "Citations":
            self.session.select_citation(index)
        elif name == "Partitions":
            self.session.goto_partition(index)
        elif name == "Expected":
            # Partition lists unified (design review §5 item 11): Expected jumps to the
            # partition that matches the expected section, not to its own row index (F2:
            # Expected and Partitions do not share numbering), only when nothing is inserting
            # (a jump mid-turn would move the insertion point from under the model); the row
            # highlight is not kept either way, since it names an expected section, not a
            # position the lawyer chose.
            if not self._busy:
                self.session.goto_expected(index)
            self._clear_selection("Expected")
        elif name == "Template":
            templates = self.session.draft_view["templates"]
            if 0 <= index < len(templates):
                self.session.template(templates[index]["tipo_atto"])
        elif name == "Letterhead":
            if index >= 0:
                self.session.choose_letterhead(index)

    def _clear_selection(self, name):
        if not self.model.hasByName(name):
            return
        self._quiet_items = True
        try:
            self.model.getByName(name).SelectedItems = ()
        finally:
            self._quiet_items = False

    def _selected_index(self, name):
        """Row index currently selected in list box ``name``, or None (nothing selected, or
        the control cannot answer)."""
        try:
            index = self.window.getControl(name).getSelectedItemPos()
        except Exception:
            return None
        return index if index >= 0 else None

    def _row_texts(self, prefix, names):
        """What was typed in the rows currently shown, in row order."""
        return [self.window.getControl(f"{prefix}{n}").getText()
                for n in range(1, len(names) + 1)]

    def _pick_file(self, filt):
        """Ask for a file through ``filt`` and answer its URL, or None when nothing was
        chosen; generalises the one-off reference picker to the attachment and letterhead
        pickers, which differ only in the filter offered."""
        try:
            picker = self.ctx.ServiceManager.createInstanceWithContext(
                "com.sun.star.ui.dialogs.FilePicker", self.ctx)
            picker.initialize((FILEOPEN_SIMPLE,))
            picker.appendFilter(*filt)
            if picker.execute() != 1:       # ExecutableDialogResults.OK
                return None
            try:
                files = picker.getSelectedFiles()
            except Exception:               # older FilePicker without XFilePicker3
                files = picker.getFiles()
            return files[0] if files else None
        except Exception as e:
            self.session.note(f"Selezione del file non riuscita: {e}")
            return None

    def _load_reference(self, url):
        """Read the chosen act and hand it to the session, which forwards it to the core.

        The panel never keeps the text: it reads the file, passes it on and forgets it.
        """
        try:
            ref = read_document(self.ctx, url)
        except DocumentActionError as e:
            self.session.note(f"Caso simile non caricato: {e}")
            return
        except Exception as e:              # anything UNO raises under the adapter
            self.session.note(f"Caso simile non caricato: {type(e).__name__}: {e}")
            return
        self.session.set_reference(ref["name"], ref["text"])

    def _load_attachment(self, url):
        """Read a case document and hand it to the session (design §4); same shape as
        ``_load_reference``, its own prefix on a read failure."""
        try:
            doc = read_document(self.ctx, url)
        except DocumentActionError as e:
            self.session.note(f"Allegato non caricato: {e}")
            return
        except Exception as e:
            self.session.note(f"Allegato non caricato: {type(e).__name__}: {e}")
            return
        self.session.add_attachment(doc["name"], doc["text"], doc["kind"])

    def _add_letterhead(self, url):
        """Build a letterhead template from a chosen file and register it (design §5.2).

        The template name comes from the source file's own name, not asked separately: one
        picker, one template, no naming dialog. ``make_letterhead`` refuses to overwrite an
        existing file, which surfaces here as the same note a read failure would.
        """
        name = Path(unquote(url)).stem
        out = letterheads.template_path(name)
        try:
            make_letterhead(self.ctx, url, str(out))
        except Exception as e:
            self.session.note(f"Carta intestata non creata: {e}")
            return
        # The file is on disk from here on: a failure below (the index, the disk rescan) is
        # reported as a registration failure, not repeated as "non creata" over a file that
        # in fact exists.
        try:
            letterheads.register_letterhead(name, out.name)
            self.session.set_letterheads(letterheads.list_letterheads())
            self.session.note(f"Carta intestata aggiunta: {name} ({out})")
        except Exception as e:
            self.session.note(f"Carta intestata creata ma non registrata: {e}")

    # --- XDropTargetListener (Redazione only) --------------------------------------------
    def drop(self, dtde):
        """Take the dropped local files: the first goes to the similar-case slot or the
        attachments set, whichever ``drop_role`` (session, pure) says (design §3.1); every
        file after it is left for a later drop, one at a time."""
        uris: list[str] = []
        owed = False                    # acceptDrop called: a dropComplete is now owed
        try:
            transferable = dtde.getTransferable()
            flavor = next((f for f in transferable.getTransferDataFlavors()
                           if f.MimeType.startswith(URI_LIST)), None)
            if flavor is None:
                dtde.rejectDrop()
            else:
                dtde.acceptDrop(dtde.DropAction)
                owed = True
                uris = file_uris(transferable.getTransferData(flavor))
                dtde.dropComplete(bool(uris))
                owed = False
        except Exception:
            uris = []
            with suppress(Exception):
                # an accepted drop is ours to finish: only dropComplete ends it, and
                # rejectDrop after acceptDrop would leave the source hanging
                if owed:
                    dtde.dropComplete(False)
                else:
                    dtde.rejectDrop()
        if self.session is None:
            return
        if not uris:
            self.session.note(DROP_REFUSED)
            return
        first = uris[0]
        name = Path(unquote(first)).name
        if drop_role(name, self._reference_present) == "reference":
            self._load_reference(first)
        else:
            self._load_attachment(first)
        if len(uris) > 1:
            self.session.note(DROP_ONE_AT_A_TIME)

    def dragEnter(self, dtde):
        with suppress(Exception):
            dtde.acceptDrag(dtde.DropAction)

    def dragOver(self, dtde):
        pass

    def dragExit(self, dte):
        pass

    def dropActionChanged(self, dtde):
        pass

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
        self._busy = bool(busy)
        for name in layout.BUSY_DISABLED:
            if self.model.hasByName(name):
                self.model.getByName(name).Enabled = not busy
        if self.model.hasByName("Cancel"):
            self.model.getByName("Cancel").Enabled = bool(busy)
        self._apply_enabled()           # last: the two state-driven buttons win over the loop

    def _apply_enabled(self):
        """Avvia redazione, Rimuovi, Togli (allegato) and Annulla (Redazione) are all
        state-driven *and* busy-driven.

        Invariant: ``Start`` is enabled only while a template is chosen and no request is
        running, ``ReferenceClear`` only while a reference act is loaded and no request is
        running, ``AttachmentRemove`` only while a row is selected, at least one attachment
        exists and no request is running, ``DraftCancel`` only while a request runs and no
        consent is pending (design review §5 item 8: the consent buttons are the only thing
        the lawyer can press while it is). The generic ``BUSY_DISABLED`` loop of ``set_busy``
        knows nothing of any of this, so every writer that can change one of these four
        conditions (``set_template``, ``set_reference``, ``set_attachments``, ``set_busy``,
        ``itemStateChanged`` on Attachments, ``_apply_drafting_state``) recomputes all four
        here instead of writing ``Enabled`` itself: otherwise an idle ``set_busy(False)`` on a
        rebuilt panel would re-enable controls their own state does not justify yet.
        """
        if self.model is None:
            return
        if self.model.hasByName("Start"):
            self.model.getByName("Start").Enabled = self._template_set and not self._busy
        if self.model.hasByName("ReferenceClear"):
            self.model.getByName("ReferenceClear").Enabled = (self._reference_present
                                                              and not self._busy)
        if self.model.hasByName("AttachmentRemove"):
            self.model.getByName("AttachmentRemove").Enabled = (
                self._selected_index("Attachments") is not None and not self._busy
                and self._attachment_count > 0)
        if self.model.hasByName("DraftCancel"):
            modal = self._consent_pending and self._step in (2, 3)
            self.model.getByName("DraftCancel").Enabled = self._busy and not modal

    def set_citations(self, labels):
        if self.model.hasByName("Citations"):
            self.model.getByName("Citations").StringItemList = tuple(labels)

    def set_usage(self, text):
        if self.model.hasByName("Usage"):
            self.model.getByName("Usage").Label = text

    def set_consent(self, summary):
        """Show the consent block for ``summary``, or hide it again when it is None: on the
        Actions panel as always (the four controls keep their slot in the layout table
        either way, spec §8.2, so the question appears and disappears without moving the
        rest of the panel); on the Drafting panel this additionally makes the wait modal
        (design review §5 item 8), since a consent request can land mid-turn with no
        further ``set_step`` call to react to it.
        """
        if self.model.hasByName("ConsentText"):
            if summary is not None:
                self.model.getByName("ConsentText").Label = render_consent(summary)
            self._set_visible("ConsentText", summary is not None)
            for name in layout.CONSENT_BUTTONS:
                self._set_visible(name, summary is not None)
        if self.model.hasByName("DraftConsentText"):
            was_pending = self._consent_pending
            was_pending = self._consent_pending
            self._consent_pending = summary is not None
            if summary is not None:
                self.model.getByName("DraftConsentText").Label = render_consent(summary)
            self._apply_drafting_state()
            if self._consent_pending and not was_pending:
                with suppress(Exception):
                    self.window.getControl("DraftConsentDocument").setFocus()

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

    # --- View protocol: guided drafting, steps 1-2 (Redazione) --------------------------
    def set_templates(self, labels, selected=None):
        """Fill the catalogue list box; ``selected`` preselects a row, None leaves the list
        with no row selected.

        Reassigning ``StringItemList`` clears the visible selection, so after a new search
        the list shows no highlighted row. What survives is the chosen template itself: the
        session keeps it in ``draft_view["template"]``, and with it the field rows,
        ``_field_names`` and the Avvia redazione button, which only ``set_template`` writes.
        """
        if not self.model.hasByName("Template"):
            return
        m = self.model.getByName("Template")
        self._quiet_items = True
        try:
            m.StringItemList = tuple(labels)
            if selected is not None:
                m.SelectedItems = (int(selected),)
        finally:
            self._quiet_items = False

    def set_template(self, info):
        """Show the chosen template: the routing line, one row per declared field.

        The rows are pre-allocated (``layout.FIELD_ROWS``), so this only fills and shows the
        ones the template declares and hides the rest; a template with more fields than rows
        keeps the extra names in the notes line, where the lawyer can write them by hand.
        """
        if not self.model.hasByName("TemplateNotes"):
            return
        campi = (info or {}).get("campi") or []
        shown = campi[:layout.FIELD_ROWS]
        notes = render_template_notes(info) if info else ""
        extra = [c["nome"] for c in campi[layout.FIELD_ROWS:]]
        if extra:
            notes += ("\n" if notes else "") + EXTRA_FIELDS + ", ".join(extra)
        self.model.getByName("TemplateNotes").Label = notes
        self._field_names = [c["nome"] for c in shown]
        for n in range(1, layout.FIELD_ROWS + 1):
            campo = shown[n - 1] if n <= len(shown) else None
            self.model.getByName(f"FieldLabel{n}").Label = (render_field_label(campo)
                                                            if campo else "")
            # another act, other values: never carry a previous template's text over
            self.window.getControl(f"Field{n}").setText("")
            self._set_visible(f"FieldLabel{n}", campo is not None)
            self._set_visible(f"Field{n}", campo is not None)
        if self.model.hasByName("FieldsLabel"):
            self.model.getByName("FieldsLabel").Label = (
                layout.FIELDS_LABEL_CHOSEN if info else layout.FIELDS_LABEL_EMPTY)
        self._template_set = info is not None
        self._apply_enabled()

    def set_field_values(self, fields, notes):
        """Write typed field values and notes back into the rows (after a rebuild, I5).

        Always paired with ``set_template``, which clears the rows and decides which field
        names they carry: a name with no stored value is written back as empty, so a fresh
        template (the session stores nothing for it) leaves the rows blank.
        """
        if not self.model.hasByName("Notes"):
            return
        values = fields or {}
        for n, name in enumerate(self._field_names, start=1):
            self.window.getControl(f"Field{n}").setText(values.get(name, ""))
        self.window.getControl("Notes").setText(notes or "")

    def set_answer_values(self, answers):
        """Write typed answers back into the rows (after a rebuild, I5); pairs with
        ``set_questions``, exactly as ``set_field_values`` pairs with ``set_template``."""
        if not self.model.hasByName("QuestionsHint"):
            return
        values = answers or {}
        for n, name in enumerate(self._question_fields, start=1):
            self.window.getControl(f"Answer{n}").setText(values.get(name, ""))

    def set_reference(self, text, present):
        if not self.model.hasByName("ReferenceInfo"):
            return
        self.model.getByName("ReferenceInfo").Label = text
        self._reference_present = bool(present)
        self._apply_enabled()

    def set_partitions(self, labels):
        if not self.model.hasByName("Partitions"):
            return
        self._quiet_items = True
        try:
            self.model.getByName("Partitions").StringItemList = tuple(labels)
        finally:
            self._quiet_items = False

    def set_draft_status(self, text, started):
        """The status line. ``ResumeInput``/``Resume`` no longer toggle here (design review
        §5 item 6): they belong to step 4 now and follow ``set_step`` like every other
        control of their step, not the ``started`` flag. While a Redazione-side consent is
        pending (item 8) the label stays the modal one ``_apply_drafting_state`` wrote, but
        ``text`` is still kept so the normal line comes straight back once it clears.
        """
        if not self.model.hasByName("DraftStatus"):
            return
        self._draft_status_text, self._draft_status_started = text, bool(started)
        if not (self._consent_pending and self._step in (2, 3)):
            self.model.getByName("DraftStatus").Label = text

    def set_questions(self, questions):
        """Show the model's open questions, one row each (the core sends at most
        ``FIELD_ROWS``), and empty the answers of the previous round.

        ``Continue`` stays part of step 2's always-shown controls (the session only ever
        moves to step 2 when there is at least one question), but its position follows the
        last visible row (design review §5 item 12, ``layout.continue_y``).
        """
        if not self.model.hasByName("QuestionsHint"):
            return
        questions = list(questions or [])
        shown = questions[:layout.FIELD_ROWS]
        self._question_fields = [q["campo"] for q in shown]
        for n in range(1, layout.FIELD_ROWS + 1):
            q = shown[n - 1] if n <= len(shown) else None
            self.model.getByName(f"QuestionLabel{n}").Label = (render_question_label(q)
                                                               if q else "")
            self.window.getControl(f"Answer{n}").setText("")
            self._set_visible(f"QuestionLabel{n}", q is not None)
            self._set_visible(f"Answer{n}", q is not None)
        if self.model.hasByName("Continue"):
            self.model.getByName("Continue").PositionY = layout.continue_y(len(shown))
        self.model.getByName("QuestionsHint").Label = (render_questions_hint(len(questions))
                                                       if questions else QUESTIONS_HINT)

    # --- View protocol: drafting workbench, steps 3-4 (design §3, §4, §5.2) ------------
    def set_step(self, step):
        """Show the controls of step ``step`` and hide those of the other three (spec §3);
        moving from step 1 to step 3 collapses the Azioni and Citazioni panels (design §3.5,
        best effort), the one signal that a drafting has actually started."""
        if not self.model.hasByName("DraftStatus"):
            return
        previous, self._step = self._step, step
        self._apply_drafting_state()
        if previous != step:
            focus = _STEP_FOCUS.get(step)
            if focus and self.model.hasByName(focus):
                with suppress(Exception):
                    self.window.getControl(focus).setFocus()
        title = _STEP_TITLES.get(step, "")
        collapse = previous == 1 and step == 3

        def update_title():
            with suppress(Exception):
                self._panel_by_id("LibreLexRedazionePanel").setTitle(title)
            if collapse:
                # Collapsing another panel can cause LibreOffice to rebuild the deck. Give
                # the title callback its own completed main-loop turn first; doing both in
                # one callback can still re-enter CreatePanels while it registers the deck.
                self._sidebar_later(self._collapse_other_panels)

        self._sidebar_later(update_title)

    def _apply_drafting_state(self):
        """What ``set_step`` and ``set_consent`` share on the Drafting panel: which step's
        controls show, the shared consent block, the modal override of design review §5 item
        8 (Continue hidden, DraftCancel disabled, a shorter status line, focus on the first
        consent button) and, the rest of the time, the step's own focus and panel title
        (item 6, item 10). A no-op on every other panel kind (no ``DraftStatus`` there).
        """
        if not self.model.hasByName("DraftStatus"):
            return
        step = self._step
        for s, names in layout.DRAFT_STEPS.items():
            for name in names:
                if name in layout.DRAFT_CONSENT or not self.model.hasByName(name):
                    continue
                if s == step:
                    if (name not in _DYNAMIC_ROWS
                            or (name.startswith("Field")
                                and int("".join(c for c in name if c.isdigit())) <= len(
                                    self._field_names))
                            or ((name.startswith("Question") or name.startswith("Answer"))
                                and int("".join(c for c in name if c.isdigit())) <= len(
                                    self._question_fields))):
                        self._set_visible(name, True)
                else:
                    self._set_visible(name, False)
        modal = self._consent_pending and step in (2, 3)
        for name in layout.DRAFT_CONSENT:
            if self.model.hasByName(name):
                self._set_visible(name, modal)
        if modal and self.model.hasByName("Continue"):
            self._set_visible("Continue", False)
        self._apply_enabled()
        if modal:
            summary = self.session.consent_summary if self.session is not None else None
            self.model.getByName("DraftStatus").Label = render_draft_consent_status(summary or {})
        else:
            self.model.getByName("DraftStatus").Label = self._draft_status_text

    def _sidebar_later(self, fn):
        """Run ``fn`` on the UI thread once the sidebar callback we are in has returned.

        The sidebar's own UNO API (XDecks/XPanels) must never be entered while LibreOffice
        is still building this deck: ``SfxUnoPanel``'s constructor calls
        ``SidebarController::CreateDeck``, which re-runs ``CreatePanels``, and every panel
        not yet registered in the deck (registration happens only after the whole loop) is
        created again, recursively, until the process aborts (Signal 6). An ``AsyncCallback``
        lands after ``CreatePanels`` has finished, where the same calls are harmless.
        """
        self._sidebar_ops.append(fn)
        if self._async_cb is None:
            self._async_cb = self.ctx.ServiceManager.createInstanceWithContext(
                "com.sun.star.awt.AsyncCallback", self.ctx)
        self._async_cb.addCallback(self, None)

    def notify(self, data):                     # XCallback, UI thread
        ops, self._sidebar_ops = self._sidebar_ops, []
        for fn in ops:
            with suppress(Exception):
                fn()

    def _panel_by_id(self, panel_id):
        """The live sidebar panel named ``panel_id``, may raise (every caller wraps it in its
        own ``suppress(Exception)``: no sidebar under the headless field test, and a panel
        the lawyer already closed both answer the same way, by raising)."""
        sidebar = self.frame.getController().getSidebar()
        deck = sidebar.getDecks().getByName("LibreLexDeck")
        return deck.getPanels().getByName(panel_id)

    def _collapse_other_panels(self):
        """Collapse Azioni and Citazioni when a drafting starts (design §3.5): best effort,
        never re-expanded by this panel, and a no-op wherever the sidebar API disagrees
        (headless LibreOffice, an already-collapsed panel)."""
        for panel_id in ("LibreLexActionsPanel", "LibreLexCitationsPanel"):
            with suppress(Exception):
                self._panel_by_id(panel_id).collapse()

    def set_log(self, lines):
        if self.model.hasByName("Log"):
            self.window.getControl("Log").setText("\n".join(lines))

    def append_log(self, line):
        """Append one line to the log and keep it scrolled to the end."""
        if not self.model.hasByName("Log"):
            return
        ctrl = self.window.getControl("Log")
        current = ctrl.getText()
        text = current + ("\n" if current else "") + line
        ctrl.setText(text)
        with suppress(Exception):
            selection = uno.createUnoStruct("com.sun.star.awt.Selection")
            selection.Min = selection.Max = len(text)
            ctrl.setSelection(selection)

    def set_expected_partitions(self, labels):
        if not self.model.hasByName("Expected"):
            return
        self._quiet_items = True
        try:
            self.model.getByName("Expected").StringItemList = tuple(labels)
        finally:
            self._quiet_items = False

    def set_attachments(self, labels):
        if not self.model.hasByName("Attachments"):
            return
        self._quiet_items = True
        try:
            self.model.getByName("Attachments").StringItemList = tuple(labels)
        finally:
            self._quiet_items = False
        self._attachment_count = len(labels)
        self._apply_enabled()

    def set_letterheads(self, labels, selected):
        if not self.model.hasByName("Letterhead"):
            return
        self._quiet_items = True
        try:
            self.model.getByName("Letterhead").StringItemList = tuple(labels)
            self.model.getByName("Letterhead").SelectedItems = (int(selected),)
        finally:
            self._quiet_items = False

    def set_summary(self, text):
        if self.model.hasByName("Summary"):
            self.window.getControl("Summary").setText(text)
