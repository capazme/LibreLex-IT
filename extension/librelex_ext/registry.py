# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""One Session per open document, torn down with the document or with LibreOffice (spec §4.3).

The deck shows three panels (Azioni, Citazioni, Risposte) over that single session: the
``PanelSet`` owns what they share, i.e. the composite view they attach to and the queue that
carries bridge events from the reader thread to the UI thread (spec §5.1).
"""
from __future__ import annotations

import queue

import unohelper
from com.sun.star.awt import XCallback
from com.sun.star.document import XEventListener
from com.sun.star.frame import XTerminateListener

from librelex_ext.views import CompositeView

_sessions: dict[str, object] = {}
_panel_sets: dict[str, PanelSet] = {}
_terminate_registered = False


class _ModelListener(unohelper.Base, XEventListener):
    """``com.sun.star.document.XEventListener``, *not* the ``lang`` one.

    On a ``com.sun.star.text.TextDocument`` pyuno resolves ``addEventListener`` to
    ``XEventBroadcaster::addEventListener``, whose parameter is the document listener;
    passing a ``lang.XEventListener`` raises ``CannotConvertException``. The document is
    unloaded before it is disposed, so ``OnUnload`` is what actually fires on close.
    """

    def __init__(self, doc_id: str):
        self.doc_id = doc_id

    def notifyEvent(self, event):
        if event.EventName == "OnUnload":
            self._shutdown()

    def disposing(self, event):
        self._shutdown()

    def _shutdown(self):
        session = _sessions.pop(self.doc_id, None)      # idempotent: OnUnload then disposing
        _panel_sets.pop(self.doc_id, None)              # nothing left to deliver events to
        if session is not None:
            try:
                session.shutdown()
            except Exception:
                pass


class _TerminateListener(unohelper.Base, XTerminateListener):
    def queryTermination(self, event):
        pass

    def notifyTermination(self, event):
        shutdown_all()

    def disposing(self, event):
        pass


class PanelSet(unohelper.Base, XCallback):
    """What the panels of one document share: its session and the route to the UI thread.

    The bridge reader thread calls ``post`` from outside the UI thread, so it only queues the
    event and asks ``AsyncCallback`` to call ``notify`` on the UI thread, where every UNO call
    has to happen (spec §5.1). The set outlives the individual panels: events keep reaching
    the session while a panel is collapsed or closed, and a reopened one replays the state
    the session kept for it.
    """

    def __init__(self, ctx, session):
        self.session = session
        self.composite = CompositeView()
        self.queue: queue.Queue = queue.Queue()
        self.async_cb = ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.awt.AsyncCallback", ctx)

    def post(self, event):                       # any thread
        self.queue.put(event)
        self.async_cb.addCallback(self, None)

    def notify(self, data):                      # XCallback, UI thread
        while True:
            try:
                ev = self.queue.get_nowait()
            except queue.Empty:
                return
            self.session.handle_event(ev)


def session_for(model, factory):
    """Return the live session of `model`, creating it with `factory()` on first use."""
    doc_id = model.RuntimeUID
    session = _sessions.get(doc_id)
    if session is None:
        session = factory()
        _sessions[doc_id] = session
        try:
            model.addEventListener(_ModelListener(doc_id))
        except Exception:
            # Losing the per-document teardown costs one idle core process until LibreOffice
            # terminates (the XTerminateListener still reaps it); never break the panel for it.
            pass
    return session


def panel_set_for(ctx, model, make_session) -> PanelSet:
    """The PanelSet of `model`, creating it (and binding its session to it) on first use."""
    session = session_for(model, make_session)
    doc_id = model.RuntimeUID
    panel_set = _panel_sets.get(doc_id)
    if panel_set is None or panel_set.session is not session:
        panel_set = PanelSet(ctx, session)
        _panel_sets[doc_id] = panel_set
        session.bind(panel_set.composite, panel_set.post)
    return panel_set


def shutdown_all() -> None:
    for session in list(_sessions.values()):
        try:
            session.shutdown()
        except Exception:
            pass
    _sessions.clear()
    _panel_sets.clear()


def ensure_terminate_listener(ctx) -> None:
    global _terminate_registered
    if _terminate_registered:
        return
    desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    desktop.addTerminateListener(_TerminateListener())
    _terminate_registered = True
