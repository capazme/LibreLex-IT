# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""One Session per open document, torn down with the document or with LibreOffice (spec §4.3)."""
from __future__ import annotations

import unohelper
from com.sun.star.frame import XTerminateListener
from com.sun.star.lang import XEventListener

_sessions: dict[str, object] = {}
_terminate_registered = False


class _ModelListener(unohelper.Base, XEventListener):
    def __init__(self, doc_id: str):
        self.doc_id = doc_id

    def disposing(self, event):
        session = _sessions.pop(self.doc_id, None)
        if session is not None:
            session.shutdown()


class _TerminateListener(unohelper.Base, XTerminateListener):
    def queryTermination(self, event):
        pass

    def notifyTermination(self, event):
        shutdown_all()

    def disposing(self, event):
        pass


def session_for(model, factory):
    """Return the live session of `model`, creating it with `factory()` on first use."""
    doc_id = model.RuntimeUID
    session = _sessions.get(doc_id)
    if session is None:
        session = factory()
        _sessions[doc_id] = session
        model.addEventListener(_ModelListener(doc_id))
    return session


def shutdown_all() -> None:
    for session in list(_sessions.values()):
        try:
            session.shutdown()
        except Exception:
            pass
    _sessions.clear()


def ensure_terminate_listener(ctx) -> None:
    global _terminate_registered
    if _terminate_registered:
        return
    desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    desktop.addTerminateListener(_TerminateListener())
    _terminate_registered = True
